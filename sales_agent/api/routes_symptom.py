"""POST /symptoms/advise"""

from __future__ import annotations

from fastapi import APIRouter

from ..graph.builder import build_graph
from .schemas import SymptomRequest, SymptomResponse

router = APIRouter(prefix="/symptoms", tags=["symptoms"])


@router.post("/advise", response_model=SymptomResponse)
def advise(req: SymptomRequest) -> SymptomResponse:
    graph = build_graph()
    state = graph.invoke(
        {
            "symptoms_vi": req.symptoms_vi,
            "duration_days": req.duration_days,
            "patient_age_years": req.patient.age_years,
            "patient_pregnancy": req.patient.pregnancy,
            "patient_allergies": req.patient.allergies,
        }
    )
    return SymptomResponse.model_validate(state["final_response"])
