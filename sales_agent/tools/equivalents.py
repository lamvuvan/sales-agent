"""Knowledge-graph lookup for equivalent drugs (Neo4j) + in-stock filter."""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy.orm import Session

from ..db.neo4j_client import GENERIC_EQUIVALENTS, THERAPEUTIC_EQUIVALENTS, run_query
from .inventory import check_stock_by_name


class Equivalent(TypedDict):
    name_vi: str
    inn: str
    strength: str
    dosage_form: str
    kind: str  # "generic" | "therapeutic"
    confidence: float
    rx_only: bool
    qty_on_hand: int


def find_equivalent_drugs(
    session: Session,
    *,
    src_name: str,
    inn: str,
    strength: str,
    dosage_form: str,
    rx_only: bool = False,
    only_in_stock: bool = True,
) -> list[Equivalent]:
    """Return equivalent drugs (generic first, then therapeutic), optionally in stock."""
    generic = run_query(
        GENERIC_EQUIVALENTS,
        src_name=src_name,
        inn=inn.lower(),
        strength=strength,
        form=dosage_form,
    )
    therapeutic = run_query(
        THERAPEUTIC_EQUIVALENTS,
        inn=inn.lower(),
        rx_only=rx_only,
    )
    seen: set[str] = set()
    out: list[Equivalent] = []
    for row in generic + therapeutic:
        name = row["name"]
        if name == src_name or name in seen:
            continue
        seen.add(name)
        stock = check_stock_by_name(session, name)
        if only_in_stock and stock["status"] != "in_stock":
            continue
        out.append(
            Equivalent(
                name_vi=name,
                inn=row["inn"],
                strength=row["strength"],
                dosage_form=row["form"],
                kind=row["kind"],
                confidence=float(row["confidence"]),
                rx_only=bool(row.get("rx_only", False)),
                qty_on_hand=stock["qty_on_hand"],
            )
        )
    return out
