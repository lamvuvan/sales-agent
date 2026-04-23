"""POST /chat — free-text Vietnamese NLU with multi-turn clarification."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..graph.builder import build_graph
from ..graph.clarification import apply_reply, detect_pending
from ..graph.nodes_common import audit_log
from ..graph.nodes_prescription import (
    check_inventory,
    find_substitutes_for_missing,
    format_prescription_reply,
    safety_check,
)
from ..session import get_session_store, new_session_id
from .schemas import ChatRequest, ChatResponse, Clarification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _build_complete_response(state: dict) -> ChatResponse:
    final = state.get("final_response") or {}
    return ChatResponse.model_validate(
        {
            "status": "complete",
            "flow": state.get("flow"),
            "parsed": state.get("parsed"),
            "items": final.get("items"),
            "red_flags": final.get("red_flags"),
            "suggestions": final.get("suggestions"),
            "summary_vi": final.get("summary_vi", ""),
            "disclaimer": final.get("disclaimer", ""),
        }
    )


def _build_clarify_response(state: dict, session_id: str) -> ChatResponse:
    pending_dict = state.get("pending_clarification") or {}
    return ChatResponse.model_validate(
        {
            "status": "awaiting_clarification",
            "session_id": session_id,
            "flow": state.get("flow"),
            "parsed": state.get("parsed"),
            "clarification": pending_dict,
            "summary_vi": pending_dict.get("question_vi", ""),
            "disclaimer": "",
        }
    )


def _finish_prescription(state: dict) -> dict:
    """Run the post-clarification tail of the prescription flow."""
    state = check_inventory(state)
    state = find_substitutes_for_missing(state)
    state = safety_check(state)
    state = format_prescription_reply(state)
    state = audit_log(state)
    return state


def _seed_state(req: ChatRequest) -> dict:
    seed: dict = {"raw_text": req.raw_text}
    if req.patient is not None:
        if req.patient.age_years is not None:
            seed["patient_age_years"] = req.patient.age_years
        seed["patient_pregnancy"] = req.patient.pregnancy
        seed["patient_allergies"] = list(req.patient.allergies)
    return seed


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    store = get_session_store()

    # Replay path: continue a session that ended in clarification.
    if req.session_id:
        state = store.get(req.session_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail="Session không tồn tại hoặc đã hết hạn.",
            )
        pending_dict = state.get("pending_clarification")
        if not pending_dict:
            raise HTTPException(
                status_code=409,
                detail="Session không ở trạng thái chờ trả lời.",
            )
        pending = Clarification.model_validate(pending_dict)
        apply_reply(state, req.raw_text, pending)
        state["pending_clarification"] = None

        # Check if more clarifications are needed.
        next_pending = detect_pending(state)
        if next_pending is not None:
            state["pending_clarification"] = next_pending.model_dump()
            store.set(req.session_id, state)
            return _build_clarify_response(state, req.session_id)

        # All resolved -> complete the prescription flow.
        state = _finish_prescription(state)
        store.delete(req.session_id)
        return _build_complete_response(state)

    # Fresh path: run the full graph.
    graph = build_graph()
    state = graph.invoke(_seed_state(req))

    # The graph halts at format_clarification_reply when pending is set.
    if state.get("pending_clarification"):
        session_id = new_session_id()
        store.set(session_id, dict(state))
        return _build_clarify_response(state, session_id)

    return _build_complete_response(state)
