"""Ensure schema + seed both Postgres and Neo4j.

Usage:
    python -m scripts.seed_all
"""

from __future__ import annotations

import logging

from sales_agent.db.migrations import ensure_all
from sales_agent.db.seed import seed_all
from sales_agent.logging import configure_logging


def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("Ensuring schema...")
    ensure_all()
    logging.getLogger(__name__).info("Seeding data...")
    seed_all()
    logging.getLogger(__name__).info("Seed done.")


if __name__ == "__main__":
    main()
