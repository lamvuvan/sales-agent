"""Shared AgentState for the LangGraph state machine."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class PrescriptionItemIn(TypedDict, total=False):
    drug_name: str
    active_ingredient: str
    strength: str
    dosage_form: str
    quantity: int
    dosage_instruction: str


class InventoryResult(TypedDict, total=False):
    item: PrescriptionItemIn
    status: Literal["in_stock", "out_of_stock", "not_carried"]
    matched_product: dict[str, Any] | None
    qty_on_hand: int
    substitutes: list[dict[str, Any]]
    safety_notes: list[str]


class FormulaSuggestionOut(TypedDict, total=False):
    formula_id: str
    code: str
    name_vi: str
    score: float
    items: list[dict[str, Any]]
    warnings: list[str]


class AgentState(TypedDict, total=False):
    flow: Literal["prescription", "symptom"]

    # NLU input (chat flow)
    raw_text: str
    parsed: dict[str, Any] | None
    nlu_extracted_items: list[dict[str, Any]]

    # Prescription input
    prescription_items: list[PrescriptionItemIn]
    # Symptom input
    symptoms_vi: list[str]
    duration_days: int | None

    # Patient context (shared)
    patient_age_years: float
    patient_pregnancy: bool
    patient_allergies: list[str]

    # Intermediate
    inventory_results: list[InventoryResult]
    red_flags: list[str]
    candidate_formulas: list[FormulaSuggestionOut]

    # Output
    summary_vi: str
    final_response: dict[str, Any]
