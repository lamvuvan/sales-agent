"""Map NLU-extracted prescription items to Postgres catalog SKUs.

Resolution order for each extracted item:
 1. Exact match by drug_name.
 2. pg_trgm fuzzy match by brand (similarity >= TRGM_THRESHOLD).
 3. Match by (active_ingredient, strength?, dosage_form?).
 4. Fall back to the extracted item as-is with status="unresolved".

The resolver never raises: unresolved items flow through downstream where
check_inventory will classify them as not_carried / out_of_stock and the
substitute step will propose alternatives.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.schemas import NluPrescriptionItem, PrescriptionItem

TRGM_THRESHOLD: float = 0.4

Resolution = Literal["brand_exact", "brand_fuzzy", "inn_form", "unresolved"]


class ResolvedItem(TypedDict, total=False):
    item: dict  # PrescriptionItem.model_dump()
    matched_sku: str | None
    matched_name_vi: str | None
    resolution: Resolution


_EXACT_SQL = text(
    """
    SELECT p.id::text AS product_id, p.sku, p.name_vi, p.active_ingredient,
           p.strength, p.dosage_form, p.rx_only
    FROM products p
    WHERE p.name_vi = :brand
    LIMIT 1
    """
)

_FUZZY_SQL = text(
    """
    SELECT p.id::text AS product_id, p.sku, p.name_vi, p.active_ingredient,
           p.strength, p.dosage_form, p.rx_only,
           similarity(p.name_vi, :brand) AS sim
    FROM products p
    WHERE similarity(p.name_vi, :brand) >= :threshold
    ORDER BY sim DESC
    LIMIT 1
    """
)

_INN_FORM_SQL = text(
    """
    SELECT p.id::text AS product_id, p.sku, p.name_vi, p.active_ingredient,
           p.strength, p.dosage_form, p.rx_only
    FROM products p
    WHERE p.active_ingredient = :inn
      AND (CAST(:strength AS text) IS NULL OR p.strength = :strength)
      AND (CAST(:form     AS text) IS NULL OR p.dosage_form = :form)
    LIMIT 1
    """
)


def _exact_by_brand(session: Session, brand: str):
    return session.execute(_EXACT_SQL, {"brand": brand}).mappings().first()


def _fuzzy_by_brand(session: Session, brand: str):
    row = session.execute(
        _FUZZY_SQL, {"brand": brand, "threshold": TRGM_THRESHOLD}
    ).mappings().first()
    if row is None:
        return None
    return row


def _by_inn_form(
    session: Session, *, inn: str, strength: str | None, form: str | None
):
    return session.execute(
        _INN_FORM_SQL, {"inn": inn.lower(), "strength": strength, "form": form}
    ).mappings().first()


def _coerce_form(form: str | None) -> str | None:
    if form is None:
        return None
    f = form.strip().lower()
    if f == "viên":
        return "viên nén"  # most common default; INN-form lookup will still be tried
    return form


def _build_item(
    extracted: NluPrescriptionItem,
    row,
    *,
    resolution: Resolution,
) -> ResolvedItem:
    drug_name = extracted.brand or (row["name_vi"] if row else "") or (
        extracted.active_ingredient or "unknown"
    )
    inn = (row["active_ingredient"] if row else extracted.active_ingredient) or ""
    strength = (row["strength"] if row else extracted.strength) or ""
    form = (row["dosage_form"] if row else extracted.dosage_form) or "viên nén"
    payload = {
        "drug_name": drug_name,
        "active_ingredient": inn.lower(),
        "strength": strength,
        "dosage_form": form,
        "quantity": int(extracted.quantity or 0),
        "dosage_instruction": extracted.dosage_instruction,
    }
    validated = PrescriptionItem.model_validate(payload).model_dump()
    return ResolvedItem(
        item=validated,
        matched_sku=(row["sku"] if row else None),
        matched_name_vi=(row["name_vi"] if row else None),
        resolution=resolution,
    )


def resolve_prescription_items(
    session: Session,
    extracted: list[NluPrescriptionItem],
) -> list[ResolvedItem]:
    """Return resolved prescription items ready to feed into check_inventory."""
    out: list[ResolvedItem] = []
    for ex in extracted:
        row = None
        resolution: Resolution = "unresolved"

        if ex.brand:
            row = _exact_by_brand(session, ex.brand)
            if row is not None:
                resolution = "brand_exact"
            elif len(ex.brand) >= 3:
                row = _fuzzy_by_brand(session, ex.brand)
                if row is not None:
                    resolution = "brand_fuzzy"

        if row is None and ex.active_ingredient:
            row = _by_inn_form(
                session,
                inn=ex.active_ingredient,
                strength=ex.strength,
                form=_coerce_form(ex.dosage_form),
            )
            if row is not None:
                resolution = "inn_form"

        out.append(_build_item(ex, row, resolution=resolution))
    return out
