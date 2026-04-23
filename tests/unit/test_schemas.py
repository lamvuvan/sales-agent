"""Validate pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sales_agent.api.schemas import (
    Patient,
    PrescriptionCheckRequest,
    PrescriptionItem,
    SymptomRequest,
)


def test_patient_accepts_basic() -> None:
    p = Patient(age_years=30, pregnancy=False, allergies=[])
    assert p.age_years == 30


def test_patient_rejects_negative_age() -> None:
    with pytest.raises(ValidationError):
        Patient(age_years=-1)


def test_prescription_requires_at_least_one_item() -> None:
    with pytest.raises(ValidationError):
        PrescriptionCheckRequest(patient=Patient(age_years=30), items=[])


def test_prescription_item_minimal() -> None:
    item = PrescriptionItem(
        drug_name="Panadol",
        active_ingredient="paracetamol",
        strength="500mg",
        dosage_form="viên nén",
        quantity=10,
    )
    assert item.dosage_instruction is None


def test_symptom_request_requires_symptoms() -> None:
    with pytest.raises(ValidationError):
        SymptomRequest(patient=Patient(age_years=30), symptoms_vi=[])
