"""End-to-end smoke demo: run the 2 canonical scenarios via the compiled graph.

Usage:
    python -m scripts.smoke_demo
"""

from __future__ import annotations

import json

from sales_agent.graph.builder import build_graph
from sales_agent.logging import configure_logging


def main() -> None:
    configure_logging()
    graph = build_graph()

    rx_state = graph.invoke(
        {
            "prescription_items": [
                {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 20,
                    "dosage_instruction": "1 viên x 3 lần/ngày sau ăn",
                },
                {
                    "drug_name": "Amoxicillin 500mg",
                    "active_ingredient": "amoxicillin",
                    "strength": "500mg",
                    "dosage_form": "viên nang",
                    "quantity": 21,
                    "dosage_instruction": "1 viên x 3 lần/ngày",
                },
                {
                    "drug_name": "Bromhexin 8mg",
                    "active_ingredient": "bromhexine",
                    "strength": "8mg",
                    "dosage_form": "viên nén",
                    "quantity": 30,
                    "dosage_instruction": "1 viên x 3 lần/ngày",
                },
            ],
            "patient_age_years": 34,
            "patient_pregnancy": False,
            "patient_allergies": [],
        }
    )
    print("=== Prescription ===")
    print(json.dumps(rx_state["final_response"], ensure_ascii=False, indent=2, default=str))

    sym_state = graph.invoke(
        {
            "symptoms_vi": ["sốt nhẹ", "sổ mũi", "đau họng"],
            "duration_days": 1,
            "patient_age_years": 28,
            "patient_pregnancy": False,
            "patient_allergies": [],
        }
    )
    print("\n=== Symptom ===")
    print(json.dumps(sym_state["final_response"], ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
