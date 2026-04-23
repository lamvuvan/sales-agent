"""POST /prescriptions/check"""

from __future__ import annotations

import time

from fastapi import APIRouter

from ..graph.builder import build_graph
from .schemas import PrescriptionCheckRequest, PrescriptionCheckResponse

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.post("/check", response_model=PrescriptionCheckResponse)
def check(req: PrescriptionCheckRequest) -> PrescriptionCheckResponse:
    graph = build_graph()
    t0 = time.perf_counter()
    state = graph.invoke(
        {
            "prescription_items": [it.model_dump() for it in req.items],
            "patient_age_years": req.patient.age_years,
            "patient_pregnancy": req.patient.pregnancy,
            "patient_allergies": req.patient.allergies,
        }
    )
    _ = int((time.perf_counter() - t0) * 1000)
    return PrescriptionCheckResponse.model_validate(state["final_response"])
