"""Test find_substitutes_for_missing: Panadol 500mg out-of-stock -> paracetamol substitutes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from sales_agent.graph import nodes_prescription


@contextmanager
def _fake_session():
    yield object()  # dummy session; real tools are mocked


@pytest.fixture
def paracetamol_substitutes() -> list[dict[str, Any]]:
    """Catalog of in-stock paracetamol 500mg 'viên nén' alternatives."""
    return [
        {
            "name_vi": "Hapacol 500",
            "inn": "paracetamol",
            "strength": "500mg",
            "dosage_form": "viên nén",
            "kind": "generic",
            "confidence": 1.0,
            "rx_only": False,
            "qty_on_hand": 80,
        },
        {
            "name_vi": "Panadol Extra",
            "inn": "paracetamol",
            "strength": "500mg",
            "dosage_form": "viên nén",
            "kind": "generic",
            "confidence": 0.95,
            "rx_only": False,
            "qty_on_hand": 80,
        },
        {
            "name_vi": "Tiffy Dey",
            "inn": "paracetamol",
            "strength": "500mg",
            "dosage_form": "viên nén",
            "kind": "generic",
            "confidence": 0.9,
            "rx_only": False,
            "qty_on_hand": 40,
        },
    ]


def test_panadol_oos_returns_paracetamol_generics(
    monkeypatch: pytest.MonkeyPatch, paracetamol_substitutes: list[dict[str, Any]]
) -> None:
    captured: dict[str, Any] = {}

    def fake_find(session, *, src_name, inn, strength, dosage_form, rx_only, only_in_stock):
        captured.update(
            src_name=src_name,
            inn=inn,
            strength=strength,
            dosage_form=dosage_form,
            rx_only=rx_only,
            only_in_stock=only_in_stock,
        )
        return paracetamol_substitutes

    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_prescription, "find_equivalent_drugs", fake_find)

    state = {
        "inventory_results": [
            {
                "item": {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 20,
                },
                "status": "out_of_stock",
                "matched_product": {
                    "product_id": "xxx",
                    "sku": "SKU-001",
                    "name_vi": "Panadol 500mg",
                    "rx_only": False,
                },
                "qty_on_hand": 0,
                "substitutes": [],
                "safety_notes": [],
            }
        ]
    }

    out = nodes_prescription.find_substitutes_for_missing(state)

    # The tool was queried with the prescribed INN/strength/form, not rx-only, in-stock only.
    assert captured["inn"] == "paracetamol"
    assert captured["strength"] == "500mg"
    assert captured["dosage_form"] == "viên nén"
    assert captured["rx_only"] is False
    assert captured["only_in_stock"] is True
    # Source drug name is passed so the generic lookup excludes the prescribed SKU itself.
    assert captured["src_name"] == "Panadol 500mg"

    subs = out["inventory_results"][0]["substitutes"]
    names = [s["name_vi"] for s in subs]
    assert names == ["Hapacol 500", "Panadol Extra", "Tiffy Dey"]
    # All substitutes share the same INN (paracetamol) and dosage form.
    assert all(s["inn"] == "paracetamol" for s in subs)
    assert all(s["dosage_form"] == "viên nén" for s in subs)
    assert all(s["qty_on_hand"] > 0 for s in subs)


def test_hapacol_not_carried_returns_paracetamol_substitutes(
    monkeypatch: pytest.MonkeyPatch, paracetamol_substitutes: list[dict[str, Any]]
) -> None:
    """When the requested brand isn't on the catalog at all, still propose by INN."""
    # Hapacol 500 is in the catalog; simulate a made-up brand not carried.
    alternatives = [s for s in paracetamol_substitutes if s["name_vi"] != "Hapacol 500"]

    def fake_find(session, **kwargs):
        return alternatives

    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_prescription, "find_equivalent_drugs", fake_find)

    state = {
        "inventory_results": [
            {
                "item": {
                    "drug_name": "Paracetamol XYZ Brand",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 15,
                },
                "status": "not_carried",
                "matched_product": None,
                "qty_on_hand": 0,
                "substitutes": [],
                "safety_notes": [],
            }
        ]
    }

    out = nodes_prescription.find_substitutes_for_missing(state)
    subs = out["inventory_results"][0]["substitutes"]
    assert [s["name_vi"] for s in subs] == ["Panadol Extra", "Tiffy Dey"]


def test_in_stock_item_is_not_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: items already in stock must not trigger a KG lookup."""
    called = {"count": 0}

    def fake_find(session, **kwargs):
        called["count"] += 1
        return []

    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_prescription, "find_equivalent_drugs", fake_find)

    state = {
        "inventory_results": [
            {
                "item": {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 10,
                },
                "status": "in_stock",
                "matched_product": {
                    "product_id": "xxx",
                    "sku": "SKU-001",
                    "name_vi": "Panadol 500mg",
                    "rx_only": False,
                },
                "qty_on_hand": 120,
                "substitutes": [],
                "safety_notes": [],
            }
        ]
    }
    nodes_prescription.find_substitutes_for_missing(state)
    assert called["count"] == 0


def test_max_five_substitutes_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The node keeps at most 5 substitutes even if the KG returns more."""
    many = [
        {
            "name_vi": f"Paracetamol {i}",
            "inn": "paracetamol",
            "strength": "500mg",
            "dosage_form": "viên nén",
            "kind": "generic",
            "confidence": 1 - i * 0.01,
            "rx_only": False,
            "qty_on_hand": 10,
        }
        for i in range(10)
    ]

    def fake_find(session, **kwargs):
        return many

    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_prescription, "find_equivalent_drugs", fake_find)

    state = {
        "inventory_results": [
            {
                "item": {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 20,
                },
                "status": "out_of_stock",
                "matched_product": {
                    "product_id": "x",
                    "sku": "SKU-001",
                    "name_vi": "Panadol 500mg",
                    "rx_only": False,
                },
                "qty_on_hand": 0,
                "substitutes": [],
                "safety_notes": [],
            }
        ]
    }
    out = nodes_prescription.find_substitutes_for_missing(state)
    assert len(out["inventory_results"][0]["substitutes"]) == 5
