"""Unit tests for tools.catalog_resolver (mocked Session.execute)."""

from __future__ import annotations

from typing import Any

import pytest

from sales_agent.api.schemas import NluPrescriptionItem
from sales_agent.tools import catalog_resolver


class _Result:
    """Supports either .first() (single row) or .all() (list).

    If ``value`` is a list, .first() returns the first element; .all() returns the list.
    If ``value`` is a dict or None, .first() returns it; .all() wraps it.
    """

    def __init__(self, value):
        self._value = value

    def mappings(self) -> "_Result":
        return self

    def first(self):
        if isinstance(self._value, list):
            return self._value[0] if self._value else None
        return self._value

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value else []


class _FakeSession:
    """Feed SQL calls with canned responses in sequence.

    Each response is either a dict (single row), a list (for .all()), or None.
    Call order follows resolve_prescription_items: exact -> fuzzy -> inn_form
    -> (if ambiguous lookup) all_by_inn_form.
    """

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[Any, dict]] = []

    def execute(self, stmt, params):
        self.calls.append((stmt, params))
        value = self._responses.pop(0) if self._responses else None
        return _Result(value)


def _row(
    *,
    sku: str = "SKU-001",
    name_vi: str = "Panadol 500mg",
    inn: str = "paracetamol",
    strength: str = "500mg",
    form: str = "viên nén",
    rx_only: bool = False,
    sim: float | None = None,
) -> dict:
    base = {
        "product_id": "p-" + sku,
        "sku": sku,
        "name_vi": name_vi,
        "active_ingredient": inn,
        "strength": strength,
        "dosage_form": form,
        "rx_only": rx_only,
    }
    if sim is not None:
        base["sim"] = sim
    return base


def test_brand_exact_match() -> None:
    sess = _FakeSession([_row()])
    extracted = [
        NluPrescriptionItem(
            brand="Panadol 500mg",
            active_ingredient=None,
            strength=None,
            dosage_form=None,
            quantity=15,
            dosage_instruction="1 viên x 3 lần/ngày",
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert len(out) == 1
    assert out[0]["resolution"] == "brand_exact"
    assert out[0]["item"]["drug_name"] == "Panadol 500mg"
    assert out[0]["item"]["active_ingredient"] == "paracetamol"
    assert out[0]["item"]["strength"] == "500mg"
    assert out[0]["item"]["dosage_form"] == "viên nén"
    assert out[0]["matched_sku"] == "SKU-001"
    # Exactly one query (exact match hit on first call).
    assert len(sess.calls) == 1


def test_brand_fuzzy_match_above_threshold() -> None:
    # Exact miss -> fuzzy returns a close match with sim=0.7.
    sess = _FakeSession([None, _row(name_vi="Panadol 500mg", sim=0.7)])
    extracted = [
        NluPrescriptionItem(
            brand="Panadol",  # not exact
            active_ingredient=None,
            strength=None,
            dosage_form=None,
            quantity=10,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "brand_fuzzy"
    # drug_name kept as the brand user wrote.
    assert out[0]["item"]["drug_name"] == "Panadol"
    # Fields filled from matched row.
    assert out[0]["item"]["active_ingredient"] == "paracetamol"
    assert out[0]["matched_name_vi"] == "Panadol 500mg"


def test_brand_fuzzy_below_threshold_falls_back_to_inn() -> None:
    # With >= threshold filter in SQL, DB returns None when sim < threshold.
    # Then INN lookup finds a match.
    sess = _FakeSession(
        [
            None,  # exact miss
            None,  # fuzzy miss (below threshold)
            _row(name_vi="Panadol 500mg"),  # inn+form hit
        ]
    )
    extracted = [
        NluPrescriptionItem(
            brand="xyz",
            active_ingredient="paracetamol",
            strength="500mg",
            dosage_form="viên nén",
            quantity=10,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "inn_form"
    assert out[0]["item"]["active_ingredient"] == "paracetamol"


def test_inn_only_when_no_brand() -> None:
    sess = _FakeSession([_row(name_vi="Hapacol 500")])
    extracted = [
        NluPrescriptionItem(
            brand=None,
            active_ingredient="paracetamol",
            strength="500mg",
            dosage_form="viên nén",
            quantity=10,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    # No brand -> first SQL call is INN, not exact.
    assert out[0]["resolution"] == "inn_form"
    assert out[0]["item"]["drug_name"] == "Hapacol 500"


def test_form_inferred_when_llm_left_null() -> None:
    """LLM returns dosage_form=null; resolver fills it from the matched row."""
    sess = _FakeSession([_row(name_vi="Panadol 500mg", form="viên nén")])
    extracted = [
        NluPrescriptionItem(
            brand="Panadol 500mg",
            active_ingredient=None,
            strength=None,
            dosage_form=None,  # null
            quantity=20,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["item"]["dosage_form"] == "viên nén"


def _cand(sku: str, name_vi: str, qty_on_hand: int = 0) -> dict:
    return {
        "sku": sku,
        "name_vi": name_vi,
        "strength": "500mg",
        "dosage_form": "viên nang",
        "rx_only": True,
        "qty_on_hand": qty_on_hand,
    }


def test_inn_form_ambiguous_populates_candidates() -> None:
    """Generic 'Amoxicillin 500mg' with no brand -> inn_form match + multiple SKUs.

    candidates list is populated for the chat layer to ask a clarification.
    """
    sess = _FakeSession(
        [
            # inn_form single-row lookup (resolver picks DHG as representative).
            _row(sku="SKU-022", name_vi="Amoxicillin 500mg DHG", inn="amoxicillin",
                 strength="500mg", form="viên nang", rx_only=True),
            # all_by_inn_form returns 2 candidates -> ambiguous.
            [
                _cand("SKU-022", "Amoxicillin 500mg DHG", qty_on_hand=50),
                _cand("SKU-023", "Amoxicillin 500 Stada", qty_on_hand=35),
            ],
        ]
    )
    extracted = [
        NluPrescriptionItem(
            brand=None,
            active_ingredient="amoxicillin",
            strength="500mg",
            dosage_form="viên nang",
            quantity=21,
            dosage_instruction="1 viên x 3 lần/ngày x 7 ngày",
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "inn_form"
    assert len(out[0]["candidates"]) == 2
    assert out[0]["candidates"][0]["sku"] == "SKU-022"
    assert out[0]["candidates"][0]["qty_on_hand"] == 50


def test_inn_form_single_sku_no_candidates() -> None:
    """Only one SKU matches INN+strength+form -> no ambiguity, no candidates field."""
    sess = _FakeSession(
        [
            _row(sku="SKU-001", name_vi="Panadol 500mg"),
            [_cand("SKU-001", "Panadol 500mg", qty_on_hand=0)],  # only one candidate
        ]
    )
    extracted = [
        NluPrescriptionItem(
            brand=None,
            active_ingredient="paracetamol",
            strength="500mg",
            dosage_form="viên nén",
            quantity=10,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "inn_form"
    assert "candidates" not in out[0]


def test_brand_exact_never_ambiguous() -> None:
    """Exact brand match skips ambiguity detection (no extra SQL call)."""
    sess = _FakeSession([_row(sku="SKU-022", name_vi="Amoxicillin 500mg DHG",
                              inn="amoxicillin", strength="500mg", form="viên nang")])
    extracted = [
        NluPrescriptionItem(
            brand="Amoxicillin 500mg DHG",
            active_ingredient=None,
            strength=None,
            dosage_form=None,
            quantity=10,
            dosage_instruction=None,
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "brand_exact"
    assert "candidates" not in out[0]
    # Exactly 1 SQL call (the exact-brand lookup).
    assert len(sess.calls) == 1


def test_unresolved_returns_with_flag() -> None:
    """No rows found at all -> unresolved but still a valid PrescriptionItem."""
    sess = _FakeSession([None, None, None])
    extracted = [
        NluPrescriptionItem(
            brand="Thuoc la",
            active_ingredient="unknown_inn",
            strength="10mg",
            dosage_form="viên nén",
            quantity=5,
            dosage_instruction="1 viên/ngày",
        )
    ]
    out = catalog_resolver.resolve_prescription_items(sess, extracted)
    assert out[0]["resolution"] == "unresolved"
    assert out[0]["item"]["drug_name"] == "Thuoc la"
    assert out[0]["item"]["active_ingredient"] == "unknown_inn"
    assert out[0]["item"]["dosage_form"] == "viên nén"
    assert out[0]["matched_sku"] is None
