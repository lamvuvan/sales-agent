"""Unit tests for the intent router."""

from __future__ import annotations

import pytest

from sales_agent.graph.nodes_common import intent_router


def test_routes_prescription() -> None:
    state = intent_router(
        {
            "prescription_items": [
                {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 10,
                }
            ],
            "patient_age_years": 30,
        }
    )
    assert state["flow"] == "prescription"


def test_routes_symptom() -> None:
    state = intent_router(
        {"symptoms_vi": ["sốt nhẹ", "sổ mũi"], "patient_age_years": 28}
    )
    assert state["flow"] == "symptom"


def test_raises_when_empty() -> None:
    with pytest.raises(ValueError):
        intent_router({"patient_age_years": 30})
