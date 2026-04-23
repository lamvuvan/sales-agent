"""Compute and store embeddings for all OTC formulas missing a vector.

Usage:
    python -m scripts.embed_formulas
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from sales_agent.db.pg import session_scope
from sales_agent.llm.client import embed
from sales_agent.logging import configure_logging

log = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    with session_scope() as sess:
        rows = sess.execute(
            text("SELECT id::text AS id, symptom_text_vi FROM otc_formulas")
        ).mappings().all()
        if not rows:
            log.warning("No formulas found — run seed_all first.")
            return

        texts = [r["symptom_text_vi"] for r in rows]
        vectors = embed(texts)
        for r, vec in zip(rows, vectors):
            sess.execute(
                text(
                    "UPDATE otc_formulas SET embedding = CAST(:v AS vector) WHERE id = :id"
                ),
                {"v": vec, "id": r["id"]},
            )
        log.info("Embedded %d formulas.", len(rows))


if __name__ == "__main__":
    main()
