"""Unit tests for sales_agent.llm.extractor (mocked OpenAI)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sales_agent.llm import extractor


_PRESCRIPTION_CANNED = {
    "intent": "prescription",
    "patient_overrides": {"age_years": None, "pregnancy": None, "allergies": []},
    "prescription_items": [
        {
            "brand": "Panadol 500mg",
            "active_ingredient": "paracetamol",
            "strength": "500mg",
            "dosage_form": "viên nén",
            "quantity": 15,
            "dosage_instruction": "1 viên x 3 lần/ngày x 5 ngày",
        },
        {
            "brand": "Loratadin 10mg",
            "active_ingredient": "loratadine",
            "strength": "10mg",
            "dosage_form": "viên nén",
            "quantity": 5,
            "dosage_instruction": "1 viên/ngày x 5 ngày",
        },
    ],
    "symptoms_vi": None,
    "duration_days": None,
}

_SYMPTOM_CANNED = {
    "intent": "symptom",
    "patient_overrides": {"age_years": 28, "pregnancy": True, "allergies": ["penicillin"]},
    "prescription_items": None,
    "symptoms_vi": ["sốt nhẹ", "sổ mũi"],
    "duration_days": 2,
}


def test_extracts_prescription_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake(system, user, *, schema_name, schema, model=None, temperature=0.0):
        captured.update(system=system, user=user, schema_name=schema_name)
        return _PRESCRIPTION_CANNED

    monkeypatch.setattr(extractor, "chat_json_schema", fake)
    out = extractor.extract_intent_and_payload(
        "Panadol 500mg, 1 viên x 3 lần/ngày x 5 ngày; Loratadin 10mg, 1 viên/ngày x 5 ngày"
    )
    assert out.intent == "prescription"
    assert out.prescription_items is not None and len(out.prescription_items) == 2
    assert out.prescription_items[0].brand == "Panadol 500mg"
    assert out.prescription_items[0].active_ingredient == "paracetamol"
    assert out.symptoms_vi is None
    assert captured["schema_name"] == "nlu_output"
    # Prompt template must have been rendered with raw_text.
    assert "Panadol 500mg" in captured["user"]


def test_extracts_symptom_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extractor, "chat_json_schema", lambda *a, **k: _SYMPTOM_CANNED)
    out = extractor.extract_intent_and_payload(
        "Khách 28 tuổi, đang mang thai, bị sốt nhẹ và sổ mũi 2 ngày nay, dị ứng penicillin"
    )
    assert out.intent == "symptom"
    assert out.symptoms_vi == ["sốt nhẹ", "sổ mũi"]
    assert out.duration_days == 2
    assert out.patient_overrides.age_years == 28
    assert out.patient_overrides.pregnancy is True
    assert out.patient_overrides.allergies == ["penicillin"]
    assert out.prescription_items is None


def test_llm_raise_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("upstream fail")

    monkeypatch.setattr(extractor, "chat_json_schema", boom)
    with pytest.raises(RuntimeError, match="upstream fail"):
        extractor.extract_intent_and_payload("x")


def test_pydantic_rejects_missing_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = {**_SYMPTOM_CANNED}
    del bad["intent"]
    monkeypatch.setattr(extractor, "chat_json_schema", lambda *a, **k: bad)
    with pytest.raises(ValidationError):
        extractor.extract_intent_and_payload("x")
