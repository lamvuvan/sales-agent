"""Inventory lookup against Postgres."""

from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

StockStatus = Literal["in_stock", "out_of_stock", "not_carried"]


class StockResult(TypedDict):
    status: StockStatus
    product_id: str | None
    sku: str | None
    name_vi: str | None
    qty_on_hand: int
    rx_only: bool


LOOKUP_SQL = text(
    """
    SELECT p.id::text AS product_id,
           p.sku,
           p.name_vi,
           p.rx_only,
           COALESCE(i.qty_on_hand, 0) AS qty_on_hand
    FROM products p
    LEFT JOIN inventory i ON i.product_id = p.id
    WHERE p.active_ingredient = :inn
      AND p.strength = :strength
      AND p.dosage_form = :form
    ORDER BY qty_on_hand DESC
    LIMIT 1
    """
)


def check_stock(
    session: Session,
    *,
    inn: str,
    strength: str,
    dosage_form: str,
) -> StockResult:
    """Return the best-matching SKU for (inn, strength, form) and its stock status."""
    row = session.execute(
        LOOKUP_SQL,
        {"inn": inn.lower(), "strength": strength, "form": dosage_form},
    ).mappings().first()

    if row is None:
        return StockResult(
            status="not_carried",
            product_id=None,
            sku=None,
            name_vi=None,
            qty_on_hand=0,
            rx_only=False,
        )
    qty = int(row["qty_on_hand"])
    return StockResult(
        status="in_stock" if qty > 0 else "out_of_stock",
        product_id=row["product_id"],
        sku=row["sku"],
        name_vi=row["name_vi"],
        qty_on_hand=qty,
        rx_only=bool(row["rx_only"]),
    )


STOCK_BY_NAME_SQL = text(
    """
    SELECT p.id::text AS product_id,
           p.sku,
           p.name_vi,
           p.rx_only,
           COALESCE(i.qty_on_hand, 0) AS qty_on_hand
    FROM products p
    LEFT JOIN inventory i ON i.product_id = p.id
    WHERE p.name_vi = :name
    LIMIT 1
    """
)


def check_stock_by_name(session: Session, name_vi: str) -> StockResult:
    row = session.execute(STOCK_BY_NAME_SQL, {"name": name_vi}).mappings().first()
    if row is None:
        return StockResult(
            status="not_carried",
            product_id=None,
            sku=None,
            name_vi=None,
            qty_on_hand=0,
            rx_only=False,
        )
    qty = int(row["qty_on_hand"])
    return StockResult(
        status="in_stock" if qty > 0 else "out_of_stock",
        product_id=row["product_id"],
        sku=row["sku"],
        name_vi=row["name_vi"],
        qty_on_hand=qty,
        rx_only=bool(row["rx_only"]),
    )
