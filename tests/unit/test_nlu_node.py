"""Unit tests for sales_agent.graph.nodes_nlu (mocked extractor + resolver)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from sales_agent.api.schemas import NluOutput, NluPrescriptionItem, PatientOverrides
from sales_agent.graph import nodes_nlu


@contextmanager
def _fake_session():
    yield object()


def _nlu_prescription() -> NluOutput:
    return NluOutput(
        intent="prescription",
        patient_overrides=PatientOverrides(age_years=34, pregnancy=None, allergies=[]),
        prescription_items=[
            NluPrescriptionItem(
                brand="Panadol 500mg",
                active_ingredient="paracetamol",
                strength="500mg",
                dosage_form="viên nén",
                quantity=15,
                dosage_instruction="1 viên x 3 lần/ngày x 5 ngày",
            )
        ],
        symptoms_vi=None,
        duration_days=None,
    )


def _nlu_symptom() -> NluOutput:
    return NluOutput(
        intent="symptom",
        patient_overrides=PatientOverrides(
            age_years=28, pregnancy=True, allergies=["penicillin"]
        ),
        prescription_items=None,
        symptoms_vi=["sốt nhẹ", "sổ mũi"],
        duration_days=2,
    )


def test_nlu_extract_skips_when_raw_text_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    def _should_not_call(raw):
        called["count"] += 1
        raise AssertionError("extractor should not be called")

    monkeypatch.setattr(nodes_nlu, "extract_intent_and_payload", _should_not_call)
    state: dict[str, Any] = {"patient_age_years": 30}
    out = nodes_nlu.nlu_extract(state)
    assert out == state
    assert called["count"] == 0


def test_nlu_extract_seeds_prescription_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nodes_nlu, "extract_intent_and_payload", lambda raw: _nlu_prescription()
    )
    state: dict[str, Any] = {"raw_text": "Panadol 500mg, 1 viên x 3/ng"}
    out = nodes_nlu.nlu_extract(state)
    assert out["flow"] == "prescription"
    assert out["parsed"]["intent"] == "prescription"
    assert out["nlu_extracted_items"][0]["brand"] == "Panadol 500mg"
    # Placeholder list, resolver will fill later.
    assert out["prescription_items"] == []
    # Patient age was empty -> filled from LLM.
    assert out["patient_age_years"] == 34


def test_nlu_extract_seeds_symptom_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nodes_nlu, "extract_intent_and_payload", lambda raw: _nlu_symptom()
    )
    state: dict[str, Any] = {"raw_text": "Khách 28 tuổi bị sốt nhẹ sổ mũi 2 ngày"}
    out = nodes_nlu.nlu_extract(state)
    assert out["flow"] == "symptom"
    assert out["symptoms_vi"] == ["sốt nhẹ", "sổ mũi"]
    assert out["duration_days"] == 2
    assert out["patient_age_years"] == 28
    assert out["patient_pregnancy"] is True
    assert out["patient_allergies"] == ["penicillin"]


def test_nlu_extract_request_age_beats_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nodes_nlu, "extract_intent_and_payload", lambda raw: _nlu_symptom()
    )
    state: dict[str, Any] = {"raw_text": "...", "patient_age_years": 10}
    out = nodes_nlu.nlu_extract(state)
    # LLM suggested 28 but request (state pre-seed) said 10 -> keep 10.
    assert out["patient_age_years"] == 10


def test_resolve_catalog_only_runs_for_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"count": 0}

    def fake_resolve(sess, extracted):
        called["count"] += 1
        return [
            {
                "item": {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 15,
                    "dosage_instruction": None,
                },
                "matched_sku": "SKU-001",
                "matched_name_vi": "Panadol 500mg",
                "resolution": "brand_exact",
            }
        ]

    monkeypatch.setattr(nodes_nlu, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_nlu, "resolve_prescription_items", fake_resolve)

    # Symptom flow -> no-op.
    state_sym = {"flow": "symptom", "nlu_extracted_items": [{"brand": "x"}]}
    out_sym = nodes_nlu.resolve_catalog(dict(state_sym))
    assert called["count"] == 0
    assert "prescription_items" not in out_sym

    # Prescription flow -> runs resolver.
    state_rx = {
        "flow": "prescription",
        "nlu_extracted_items": [
            {
                "brand": "Panadol 500mg",
                "active_ingredient": "paracetamol",
                "strength": "500mg",
                "dosage_form": "viên nén",
                "quantity": 15,
                "dosage_instruction": None,
            }
        ],
        "parsed": {"intent": "prescription"},
    }
    out_rx = nodes_nlu.resolve_catalog(dict(state_rx))
    assert called["count"] == 1
    assert out_rx["prescription_items"][0]["drug_name"] == "Panadol 500mg"
    assert out_rx["parsed"]["resolutions"][0]["resolution"] == "brand_exact"
