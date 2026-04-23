"""Load seed CSV files into Postgres and Neo4j (idempotent upsert)."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import text

from .neo4j_client import get_driver
from .pg import session_scope

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"


def _read_csv(name: str) -> list[dict[str, str]]:
    path = SEED_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_bool(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "y", "t")


def _nullable(s: str) -> str | None:
    return s.strip() or None


# --- Postgres ---------------------------------------------------------------

UPSERT_PRODUCT = text(
    """
    INSERT INTO products (sku, name_vi, active_ingredient, strength, dosage_form,
                          pack_size, rx_only, manufacturer, price_vnd)
    VALUES (:sku, :name_vi, :active_ingredient, :strength, :dosage_form,
            :pack_size, :rx_only, :manufacturer, :price_vnd)
    ON CONFLICT (sku) DO UPDATE SET
      name_vi = EXCLUDED.name_vi,
      active_ingredient = EXCLUDED.active_ingredient,
      strength = EXCLUDED.strength,
      dosage_form = EXCLUDED.dosage_form,
      pack_size = EXCLUDED.pack_size,
      rx_only = EXCLUDED.rx_only,
      manufacturer = EXCLUDED.manufacturer,
      price_vnd = EXCLUDED.price_vnd
    RETURNING id
    """
)

UPSERT_INVENTORY = text(
    """
    INSERT INTO inventory (product_id, qty_on_hand, reorder_point)
    SELECT id, :qty, :reorder FROM products WHERE sku = :sku
    ON CONFLICT (product_id) DO UPDATE SET
      qty_on_hand = EXCLUDED.qty_on_hand,
      reorder_point = EXCLUDED.reorder_point,
      updated_at = now()
    """
)

UPSERT_FORMULA = text(
    """
    INSERT INTO otc_formulas (code, name_vi, symptom_tags, symptom_text_vi,
                              min_age_years, max_age_years, pregnancy_safe, notes_vi)
    VALUES (:code, :name_vi, :tags, :symptom_text, :min_age, :max_age, :preg_safe, :notes)
    ON CONFLICT (code) DO UPDATE SET
      name_vi = EXCLUDED.name_vi,
      symptom_tags = EXCLUDED.symptom_tags,
      symptom_text_vi = EXCLUDED.symptom_text_vi,
      min_age_years = EXCLUDED.min_age_years,
      max_age_years = EXCLUDED.max_age_years,
      pregnancy_safe = EXCLUDED.pregnancy_safe,
      notes_vi = EXCLUDED.notes_vi
    RETURNING id
    """
)

DELETE_FORMULA_ITEMS = text("DELETE FROM formula_items WHERE formula_id = :fid")

INSERT_FORMULA_ITEM = text(
    """
    INSERT INTO formula_items (formula_id, active_ingredient, strength_hint,
                               dose_per_take_vi, frequency_per_day, duration_days,
                               age_rule_vi, role)
    VALUES (:fid, :inn, :strength, :dose, :freq, :dur, :age_rule, :role)
    """
)


def seed_postgres() -> None:
    products = _read_csv("products.csv")
    inventory = _read_csv("inventory.csv")
    formulas = _read_csv("otc_formulas.csv")
    formula_items = _read_csv("formula_items.csv")

    with session_scope() as sess:
        for row in products:
            sess.execute(
                UPSERT_PRODUCT,
                {
                    "sku": row["sku"],
                    "name_vi": row["name_vi"],
                    "active_ingredient": row["active_ingredient"].lower(),
                    "strength": row["strength"],
                    "dosage_form": row["dosage_form"],
                    "pack_size": _nullable(row.get("pack_size", "")),
                    "rx_only": _to_bool(row.get("rx_only", "false")),
                    "manufacturer": _nullable(row.get("manufacturer", "")),
                    "price_vnd": int(row["price_vnd"]) if row.get("price_vnd") else None,
                },
            )
        for row in inventory:
            sess.execute(
                UPSERT_INVENTORY,
                {
                    "sku": row["sku"],
                    "qty": int(row["qty_on_hand"]),
                    "reorder": int(row.get("reorder_point", 0) or 0),
                },
            )
        logger.info("Seeded %d products, %d inventory rows", len(products), len(inventory))

        code_to_id: dict[str, str] = {}
        for row in formulas:
            tags = [t.strip() for t in row["symptom_tags"].split("|") if t.strip()]
            fid = sess.execute(
                UPSERT_FORMULA,
                {
                    "code": row["code"],
                    "name_vi": row["name_vi"],
                    "tags": tags,
                    "symptom_text": row["symptom_text_vi"],
                    "min_age": float(row.get("min_age_years", 0) or 0),
                    "max_age": float(row["max_age_years"]) if row.get("max_age_years") else None,
                    "preg_safe": _to_bool(row.get("pregnancy_safe", "false")),
                    "notes": _nullable(row.get("notes_vi", "")),
                },
            ).scalar_one()
            code_to_id[row["code"]] = str(fid)
            sess.execute(DELETE_FORMULA_ITEMS, {"fid": fid})

        for row in formula_items:
            fid = code_to_id.get(row["formula_code"])
            if fid is None:
                logger.warning("Skip formula_item: unknown formula_code %s", row["formula_code"])
                continue
            sess.execute(
                INSERT_FORMULA_ITEM,
                {
                    "fid": fid,
                    "inn": row["active_ingredient"].lower(),
                    "strength": _nullable(row.get("strength_hint", "")),
                    "dose": row["dose_per_take_vi"],
                    "freq": int(row["frequency_per_day"]),
                    "dur": int(row["duration_days"]),
                    "age_rule": _nullable(row.get("age_rule_vi", "")),
                    "role": row["role"].strip(),
                },
            )
        logger.info(
            "Seeded %d formulas, %d formula items", len(formulas), len(formula_items)
        )


# --- Neo4j ------------------------------------------------------------------

UPSERT_AI = """
MERGE (a:ActiveIngredient {inn: $inn})
  SET a.name_vi = $name_vi
"""

UPSERT_ATC = """
MERGE (c:ATCClass {code: $code})
  SET c.name_vi = $name_vi, c.level = $level
"""

LINK_AI_ATC = """
MATCH (a:ActiveIngredient {inn: $inn})
MATCH (c:ATCClass {code: $atc_code})
MERGE (a)-[:BELONGS_TO_ATC]->(c)
"""

UPSERT_DRUG = """
MERGE (d:Drug {name_vi: $name_vi})
  SET d.inn = $inn,
      d.strength = $strength,
      d.dosage_form = $dosage_form,
      d.rx_only = $rx_only,
      d.manufacturer = $manufacturer
WITH d
MATCH (a:ActiveIngredient {inn: $inn})
MERGE (d)-[r:CONTAINS]->(a)
  SET r.strength = $strength
"""

LINK_EQUIVALENT = """
MATCH (a:Drug {name_vi: $a_name})
MATCH (b:Drug {name_vi: $b_name})
MERGE (a)-[r:EQUIVALENT_TO]->(b)
  SET r.kind = $kind, r.confidence = $confidence
"""

LINK_TREATS = """
MATCH (a:ActiveIngredient {inn: $inn})
MERGE (i:Indication {name_vi: $indication})
MERGE (a)-[:TREATS]->(i)
"""

LINK_CONTRAINDICATION = """
MATCH (d:Drug {name_vi: $drug_name})
MERGE (c:Condition {name_vi: $condition})
MERGE (d)-[:CONTRAINDICATED_WITH]->(c)
"""


def seed_neo4j() -> None:
    active_ingredients = _read_csv("active_ingredients.csv")
    atc = _read_csv("atc_classes.csv")
    products = _read_csv("products.csv")
    equivalences = _read_csv("drug_equivalences.csv")
    indications = _read_csv("indications.csv")
    contraindications = _read_csv("contraindications.csv")

    driver = get_driver()
    with driver.session() as s:
        for row in atc:
            s.run(
                UPSERT_ATC,
                code=row["code"],
                name_vi=row["name_vi"],
                level=int(row["level"]),
            )
        for row in active_ingredients:
            s.run(UPSERT_AI, inn=row["inn"].lower(), name_vi=row["name_vi"])
            if row.get("atc_code"):
                s.run(LINK_AI_ATC, inn=row["inn"].lower(), atc_code=row["atc_code"])

        for row in products:
            s.run(
                UPSERT_DRUG,
                name_vi=row["name_vi"],
                inn=row["active_ingredient"].lower(),
                strength=row["strength"],
                dosage_form=row["dosage_form"],
                rx_only=_to_bool(row.get("rx_only", "false")),
                manufacturer=row.get("manufacturer") or None,
            )

        for row in equivalences:
            s.run(
                LINK_EQUIVALENT,
                a_name=row["drug_a"],
                b_name=row["drug_b"],
                kind=row["kind"],
                confidence=float(row.get("confidence", 0.8) or 0.8),
            )
        for row in indications:
            s.run(LINK_TREATS, inn=row["inn"].lower(), indication=row["indication_vi"])
        for row in contraindications:
            s.run(
                LINK_CONTRAINDICATION,
                drug_name=row["drug_name"],
                condition=row["condition_vi"],
            )
    logger.info(
        "Neo4j seed done: %d AI, %d ATC, %d drugs, %d equiv",
        len(active_ingredients),
        len(atc),
        len(products),
        len(equivalences),
    )


def seed_all() -> None:
    seed_postgres()
    seed_neo4j()
