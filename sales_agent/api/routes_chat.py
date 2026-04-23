"""POST /chat — free-text Vietnamese NLU with auto intent routing."""

from __future__ import annotations

from fastapi import APIRouter

from ..graph.builder import build_graph
from .schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    graph = build_graph()
    seed: dict = {"raw_text": req.raw_text}
    if req.patient is not None:
        if req.patient.age_years is not None:
            seed["patient_age_years"] = req.patient.age_years
        seed["patient_pregnancy"] = req.patient.pregnancy
        seed["patient_allergies"] = list(req.patient.allergies)
    state = graph.invoke(seed)
    final = state.get("final_response") or {}
    return ChatResponse.model_validate(
        {
            "flow": state["flow"],
            "parsed": state.get("parsed"),
            "items": final.get("items"),
            "red_flags": final.get("red_flags"),
            "suggestions": final.get("suggestions"),
            "summary_vi": final.get("summary_vi", ""),
            "disclaimer": final.get("disclaimer", ""),
        }
    )
