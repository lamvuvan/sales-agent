"""Neo4j driver singleton + Cypher helpers."""

from __future__ import annotations

from typing import Any

from neo4j import Driver, GraphDatabase

from ..config import get_settings

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT drug_name IF NOT EXISTS FOR (d:Drug) REQUIRE d.name_vi IS UNIQUE",
    "CREATE CONSTRAINT inn_unique IF NOT EXISTS FOR (a:ActiveIngredient) REQUIRE a.inn IS UNIQUE",
    "CREATE CONSTRAINT atc_code IF NOT EXISTS FOR (c:ATCClass) REQUIRE c.code IS UNIQUE",
    "CREATE INDEX drug_inn_form IF NOT EXISTS FOR (d:Drug) ON (d.inn, d.strength, d.dosage_form)",
]


def ensure_schema() -> None:
    with get_driver().session() as sess:
        for stmt in CREATE_CONSTRAINTS:
            sess.run(stmt)


GENERIC_EQUIVALENTS = """
MATCH (alt:Drug)
WHERE alt.inn = $inn
  AND alt.strength = $strength
  AND alt.dosage_form = $form
  AND alt.name_vi <> $src_name
RETURN alt.name_vi AS name,
       alt.inn AS inn,
       alt.strength AS strength,
       alt.dosage_form AS form,
       alt.rx_only AS rx_only,
       'generic' AS kind,
       1.0 AS confidence
"""

THERAPEUTIC_EQUIVALENTS = """
MATCH (src:Drug {inn:$inn})-[:CONTAINS]->(:ActiveIngredient)-[:BELONGS_TO_ATC]->(atc:ATCClass)
WHERE atc.level = 4
MATCH (atc)<-[:BELONGS_TO_ATC]-(ai:ActiveIngredient)<-[:CONTAINS]-(alt:Drug)
WHERE alt.inn <> src.inn AND alt.rx_only = $rx_only
RETURN DISTINCT alt.name_vi AS name,
       alt.inn AS inn,
       alt.strength AS strength,
       alt.dosage_form AS form,
       alt.rx_only AS rx_only,
       'therapeutic' AS kind,
       0.6 AS confidence
LIMIT 10
"""

CONTRAINDICATIONS = """
MATCH (d:Drug {name_vi:$name})-[:CONTRAINDICATED_WITH]->(c:Condition)
RETURN collect(c.name_vi) AS conditions
"""


def run_query(cypher: str, **params: Any) -> list[dict[str, Any]]:
    with get_driver().session() as sess:
        result = sess.run(cypher, **params)
        return [dict(r) for r in result]
