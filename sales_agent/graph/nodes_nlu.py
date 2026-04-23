"""NLU nodes: extract free-text Vietnamese input, resolve brand to SKU."""

from __future__ import annotations

import logging

from ..db.pg import session_scope
from ..llm.extractor import extract_intent_and_payload
from ..tools.catalog_resolver import resolve_prescription_items
from .state import AgentState

logger = logging.getLogger(__name__)


def nlu_extract(state: AgentState) -> AgentState:
    """If raw_text is provided, run LLM NLU and seed state.

    Idempotent: skips if state already has prescription_items or symptoms_vi.
    HTTP request patient fields always beat LLM overrides.
    """
    raw = (state.get("raw_text") or "").strip()
    if not raw:
        return state
    if state.get("prescription_items") or state.get("symptoms_vi"):
        # Caller already provided structured payload; NLU is a no-op.
        return state

    nlu = extract_intent_and_payload(raw)
    state["parsed"] = nlu.model_dump()
    state["flow"] = nlu.intent

    # Patient merge: only fill fields the request did not already set.
    overrides = nlu.patient_overrides
    if state.get("patient_age_years") in (None, 0) and overrides.age_years is not None:
        state["patient_age_years"] = float(overrides.age_years)
    if state.get("patient_pregnancy") is None and overrides.pregnancy is not None:
        state["patient_pregnancy"] = bool(overrides.pregnancy)
    existing_allergies = list(state.get("patient_allergies") or [])
    if overrides.allergies:
        merged = list(dict.fromkeys([*existing_allergies, *overrides.allergies]))
        state["patient_allergies"] = merged
    else:
        state["patient_allergies"] = existing_allergies

    if nlu.intent == "prescription":
        state["nlu_extracted_items"] = [
            it.model_dump() for it in (nlu.prescription_items or [])
        ]
        # Placeholder so intent_router routes to prescription subgraph;
        # resolve_catalog will populate the real items from the resolver.
        state["prescription_items"] = []
    else:
        state["symptoms_vi"] = list(nlu.symptoms_vi or [])
        state["duration_days"] = nlu.duration_days

    return state


def resolve_catalog(state: AgentState) -> AgentState:
    """Run the catalog resolver on NLU-extracted items (prescription flow only)."""
    if state.get("flow") != "prescription":
        return state
    extracted_dicts = state.get("nlu_extracted_items")
    if not extracted_dicts:
        # No NLU step ran (legacy /prescriptions/check passed items directly).
        return state
    # Rehydrate to pydantic models for the resolver.
    from ..api.schemas import NluPrescriptionItem

    extracted = [NluPrescriptionItem.model_validate(d) for d in extracted_dicts]
    with session_scope() as sess:
        resolved = resolve_prescription_items(sess, extracted)
    state["prescription_items"] = [r["item"] for r in resolved]
    # Keep resolution metadata in parsed for transparency.
    parsed = state.get("parsed") or {}
    parsed["resolutions"] = [
        {"sku": r.get("matched_sku"), "name_vi": r.get("matched_name_vi"), "resolution": r.get("resolution")}
        for r in resolved
    ]
    state["parsed"] = parsed
    return state
