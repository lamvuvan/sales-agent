"""Pydantic request / response schemas for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Patient(BaseModel):
    age_years: float = Field(ge=0, le=130)
    pregnancy: bool = False
    allergies: list[str] = Field(default_factory=list)


class PrescriptionItem(BaseModel):
    drug_name: str
    active_ingredient: str
    strength: str
    dosage_form: str
    quantity: int = Field(ge=0, default=0)
    dosage_instruction: str | None = None


class PrescriptionCheckRequest(BaseModel):
    patient: Patient
    items: list[PrescriptionItem] = Field(min_length=1)


class SubstituteOut(BaseModel):
    name_vi: str
    inn: str
    strength: str
    dosage_form: str
    kind: Literal["generic", "therapeutic"]
    confidence: float
    rx_only: bool
    qty_on_hand: int


class InventoryLineOut(BaseModel):
    item: PrescriptionItem
    status: Literal["in_stock", "out_of_stock", "not_carried"]
    matched_product: dict[str, Any] | None = None
    qty_on_hand: int
    substitutes: list[SubstituteOut] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class PrescriptionCheckResponse(BaseModel):
    flow: Literal["prescription"] = "prescription"
    items: list[InventoryLineOut]
    summary_vi: str
    disclaimer: str


class SymptomRequest(BaseModel):
    patient: Patient
    symptoms_vi: list[str] = Field(min_length=1)
    duration_days: int | None = Field(default=None, ge=0, le=365)


class FormulaItemOut(BaseModel):
    active_ingredient: str
    strength_hint: str | None = None
    dose_per_take_vi: str
    frequency_per_day: int
    duration_days: int
    age_rule_vi: str | None = None
    role: Literal["primary", "adjuvant"]


class FormulaSuggestionOut(BaseModel):
    formula_id: str
    code: str
    name_vi: str
    score: float
    items: list[FormulaItemOut]
    warnings: list[str] = Field(default_factory=list)


class SymptomResponse(BaseModel):
    flow: Literal["symptom"] = "symptom"
    red_flags: list[str]
    suggestions: list[FormulaSuggestionOut]
    summary_vi: str
    disclaimer: str


# --- NLU / Chat ---------------------------------------------------------------


class PatientOverrides(BaseModel):
    age_years: float | None = None
    pregnancy: bool | None = None
    allergies: list[str] = Field(default_factory=list)


class NluPrescriptionItem(BaseModel):
    brand: str | None = None
    active_ingredient: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    quantity: int | None = None
    dosage_instruction: str | None = None


class NluOutput(BaseModel):
    intent: Literal["prescription", "symptom"]
    patient_overrides: PatientOverrides = Field(default_factory=PatientOverrides)
    prescription_items: list[NluPrescriptionItem] | None = None
    symptoms_vi: list[str] | None = None
    duration_days: int | None = None


class ChatPatient(BaseModel):
    age_years: float | None = Field(default=None, ge=0, le=130)
    pregnancy: bool = False
    allergies: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=4000)
    patient: ChatPatient | None = None
    session_id: str | None = None  # set when replying to a clarification


class ParsedInput(BaseModel):
    intent: Literal["prescription", "symptom"]
    patient_overrides: PatientOverrides = Field(default_factory=PatientOverrides)
    prescription_items: list[NluPrescriptionItem] | None = None
    symptoms_vi: list[str] | None = None
    duration_days: int | None = None


class ClarificationOption(BaseModel):
    sku: str
    name_vi: str
    strength: str
    dosage_form: str
    qty_on_hand: int
    rx_only: bool


class Clarification(BaseModel):
    kind: Literal["ambiguous", "unresolved"]
    item_index: int
    item_summary: str  # e.g. "Amoxicillin 500mg (viên nang)"
    question_vi: str
    options: list[ClarificationOption] = Field(default_factory=list)  # empty for unresolved


class ChatResponse(BaseModel):
    status: Literal["complete", "awaiting_clarification"] = "complete"
    session_id: str | None = None
    flow: Literal["prescription", "symptom"] | None = None
    parsed: ParsedInput | None = None
    clarification: Clarification | None = None
    items: list[InventoryLineOut] | None = None
    red_flags: list[str] | None = None
    suggestions: list[FormulaSuggestionOut] | None = None
    summary_vi: str = ""
    disclaimer: str = ""
