"""Shared nodes: intent_router, audit_log."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text

from ..config import get_settings
from ..db.pg import session_scope
from .state import AgentState

logger = logging.getLogger(__name__)


def intent_router(state: AgentState) -> AgentState:
    """Decide the flow based on which input is present."""
    if state.get("prescription_items"):
        state["flow"] = "prescription"
    elif state.get("symptoms_vi"):
        state["flow"] = "symptom"
    else:
        raise ValueError("Neither prescription_items nor symptoms_vi provided.")
    return state


def _patient_hash(state: AgentState) -> str:
    s = get_settings()
    parts: list[str] = [str(state.get("patient_age_years", ""))]
    if state.get("flow") == "prescription":
        names = sorted(
            (it.get("drug_name") or it.get("active_ingredient") or "")
            for it in state.get("prescription_items") or []
        )
        parts.extend(names)
    else:
        parts.extend(sorted(state.get("symptoms_vi") or []))
    payload = f"{s.audit_salt}|" + "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_log(state: AgentState, *, latency_ms: int | None = None) -> AgentState:
    """Best-effort insert into agent_audit_log. Never raises."""
    try:
        request_payload: dict[str, Any] = {
            "flow": state.get("flow"),
            "prescription_items": state.get("prescription_items"),
            "symptoms_vi": state.get("symptoms_vi"),
            "patient_age_years": state.get("patient_age_years"),
            "patient_pregnancy": state.get("patient_pregnancy"),
            "patient_allergies": state.get("patient_allergies"),
            "duration_days": state.get("duration_days"),
        }
        response_payload = state.get("final_response") or {}
        with session_scope() as sess:
            sess.execute(
                text(
                    """
                    INSERT INTO agent_audit_log
                      (flow, patient_hash, request_json, response_json,
                       llm_model, latency_ms, red_flags)
                    VALUES
                      (:flow, :ph, CAST(:req AS jsonb), CAST(:resp AS jsonb),
                       :model, :lat, :flags)
                    """
                ),
                {
                    "flow": state["flow"],
                    "ph": _patient_hash(state),
                    "req": json.dumps(request_payload, ensure_ascii=False),
                    "resp": json.dumps(response_payload, ensure_ascii=False),
                    "model": get_settings().llm_model,
                    "lat": latency_ms,
                    "flags": state.get("red_flags") or None,
                },
            )
    except Exception:
        logger.exception("audit_log failed")
    return state
