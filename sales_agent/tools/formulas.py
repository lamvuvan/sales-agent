"""Vector search for OTC formulas (pgvector cosine)."""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session


class FormulaItemOut(TypedDict):
    active_ingredient: str
    strength_hint: str | None
    dose_per_take_vi: str
    frequency_per_day: int
    duration_days: int
    age_rule_vi: str | None
    role: str


class FormulaSuggestion(TypedDict):
    formula_id: str
    code: str
    name_vi: str
    score: float
    min_age_years: float
    max_age_years: float | None
    pregnancy_safe: bool
    notes_vi: str | None
    items: list[FormulaItemOut]


SEARCH_SQL = text(
    """
    SELECT f.id::text AS formula_id,
           f.code,
           f.name_vi,
           f.min_age_years,
           f.max_age_years,
           f.pregnancy_safe,
           f.notes_vi,
           1 - (f.embedding <=> CAST(:q AS vector)) AS score
    FROM otc_formulas f
    WHERE f.embedding IS NOT NULL
      AND f.min_age_years <= :age
      AND (f.max_age_years IS NULL OR f.max_age_years >= :age)
      AND (:pregnancy = FALSE OR f.pregnancy_safe = TRUE)
    ORDER BY f.embedding <=> CAST(:q AS vector)
    LIMIT :k
    """
)

ITEMS_SQL = text(
    """
    SELECT active_ingredient, strength_hint, dose_per_take_vi,
           frequency_per_day, duration_days, age_rule_vi, role
    FROM formula_items
    WHERE formula_id = :fid
    ORDER BY role DESC, active_ingredient
    """
)


def search_otc_formulas(
    session: Session,
    *,
    query_embedding: list[float],
    age_years: float,
    pregnancy: bool = False,
    top_k: int = 5,
) -> list[FormulaSuggestion]:
    rows = session.execute(
        SEARCH_SQL,
        {
            "q": query_embedding,
            "age": age_years,
            "pregnancy": pregnancy,
            "k": top_k,
        },
    ).mappings().all()

    out: list[FormulaSuggestion] = []
    for r in rows:
        items = session.execute(ITEMS_SQL, {"fid": r["formula_id"]}).mappings().all()
        out.append(
            FormulaSuggestion(
                formula_id=r["formula_id"],
                code=r["code"],
                name_vi=r["name_vi"],
                score=float(r["score"]),
                min_age_years=float(r["min_age_years"]),
                max_age_years=float(r["max_age_years"]) if r["max_age_years"] is not None else None,
                pregnancy_safe=bool(r["pregnancy_safe"]),
                notes_vi=r["notes_vi"],
                items=[
                    FormulaItemOut(
                        active_ingredient=it["active_ingredient"],
                        strength_hint=it["strength_hint"],
                        dose_per_take_vi=it["dose_per_take_vi"],
                        frequency_per_day=int(it["frequency_per_day"]),
                        duration_days=int(it["duration_days"]),
                        age_rule_vi=it["age_rule_vi"],
                        role=it["role"],
                    )
                    for it in items
                ],
            )
        )
    return out
