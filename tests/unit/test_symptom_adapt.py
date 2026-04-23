"""Unit tests for rank_and_adapt_by_age (OTC filtering logic)."""

from __future__ import annotations

from sales_agent.graph.nodes_symptom import rank_and_adapt_by_age


def _fmt(primary_inn: str, adjuvant_inn: str | None = None, score: float = 0.8):
    items = [
        {
            "active_ingredient": primary_inn,
            "strength_hint": None,
            "dose_per_take_vi": "1 viên",
            "frequency_per_day": 3,
            "duration_days": 3,
            "age_rule_vi": "người lớn",
            "role": "primary",
        }
    ]
    if adjuvant_inn:
        items.append(
            {
                "active_ingredient": adjuvant_inn,
                "strength_hint": None,
                "dose_per_take_vi": "1 viên",
                "frequency_per_day": 2,
                "duration_days": 3,
                "age_rule_vi": "người lớn",
                "role": "adjuvant",
            }
        )
    return {
        "formula_id": f"id-{primary_inn}",
        "code": f"C-{primary_inn}",
        "name_vi": f"Formula {primary_inn}",
        "score": score,
        "items": items,
        "warnings": [],
    }


def test_drops_formula_when_primary_is_rx() -> None:
    state = {
        "patient_age_years": 30,
        "candidate_formulas": [_fmt("amoxicillin")],  # Rx
    }
    out = rank_and_adapt_by_age(dict(state))
    assert out["candidate_formulas"] == []


def test_drops_adjuvant_rx_but_keeps_formula() -> None:
    state = {
        "patient_age_years": 30,
        "candidate_formulas": [_fmt("paracetamol", adjuvant_inn="amoxicillin")],
    }
    out = rank_and_adapt_by_age(dict(state))
    assert len(out["candidate_formulas"]) == 1
    items = out["candidate_formulas"][0]["items"]
    assert [it["active_ingredient"] for it in items] == ["paracetamol"]
    assert out["candidate_formulas"][0]["warnings"]


def test_allergy_drops_item() -> None:
    state = {
        "patient_age_years": 30,
        "patient_allergies": ["paracetamol"],
        "candidate_formulas": [_fmt("paracetamol", adjuvant_inn="chlorpheniramine")],
    }
    out = rank_and_adapt_by_age(dict(state))
    # primary dropped by allergy: formula has no kept items -> dropped entirely
    assert out["candidate_formulas"] == []


def test_sorts_by_score_desc_limit_3() -> None:
    state = {
        "patient_age_years": 30,
        "candidate_formulas": [
            _fmt("paracetamol", score=0.3),
            _fmt("loratadine", score=0.9),
            _fmt("bromhexine", score=0.7),
            _fmt("ambroxol", score=0.8),
        ],
    }
    out = rank_and_adapt_by_age(dict(state))
    names = [f["items"][0]["active_ingredient"] for f in out["candidate_formulas"]]
    assert names == ["loratadine", "ambroxol", "bromhexine"]


def test_pediatric_hint_blocks_adult_rule() -> None:
    state = {
        "patient_age_years": 4,
        "candidate_formulas": [_fmt("paracetamol")],
    }
    out = rank_and_adapt_by_age(dict(state))
    hint = out["candidate_formulas"][0]["items"][0]["age_rule_vi"]
    assert "không dùng cho trẻ" in hint.lower()
