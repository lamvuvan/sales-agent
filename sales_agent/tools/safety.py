"""Safety guardrails: Rx-only blacklist, ATC-class blocks, pediatric dosing."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.neo4j_client import CONTRAINDICATIONS, run_query

DISCLAIMER_VI = (
    "Thông tin chỉ mang tính chất tham khảo cho nhân viên bán hàng. "
    "Không thay thế chẩn đoán và tư vấn của bác sĩ/dược sĩ có chuyên môn. "
    "Khi có dấu hiệu nặng, vui lòng đến cơ sở y tế."
)

# ATC prefix blacklist for the OTC/symptom flow.
BLOCKED_ATC_PREFIXES: tuple[str, ...] = (
    "J01",   # Systemic antibiotics
    "N02A",  # Opioids
    "H02",   # Systemic corticosteroids
    "N05BA", # Benzodiazepines
    "N05CD", # Benzodiazepine hypnotics
)

# INN blacklist for the OTC flow (defense-in-depth).
BLOCKED_INNS: frozenset[str] = frozenset(
    {
        "amoxicillin",
        "ampicillin",
        "azithromycin",
        "ciprofloxacin",
        "clarithromycin",
        "erythromycin",
        "cefuroxime",
        "cefixime",
        "doxycycline",
        "levofloxacin",
        "metronidazole",
        "codeine",
        "tramadol",
        "morphine",
        "prednisolone",
        "dexamethasone",
        "methylprednisolone",
        "diazepam",
        "alprazolam",
    }
)


def is_blocked_for_otc(active_ingredient: str, *, atc_code: str | None = None) -> bool:
    if active_ingredient.lower() in BLOCKED_INNS:
        return True
    if atc_code:
        return any(atc_code.startswith(p) for p in BLOCKED_ATC_PREFIXES)
    return False


def is_rx_only_product(session: Session, name_vi: str) -> bool:
    row = session.execute(
        text("SELECT rx_only FROM products WHERE name_vi = :n LIMIT 1"),
        {"n": name_vi},
    ).first()
    return bool(row[0]) if row else False


def get_contraindications(drug_name: str) -> list[str]:
    rows = run_query(CONTRAINDICATIONS, name=drug_name)
    if not rows:
        return []
    conds = rows[0].get("conditions") or []
    return [str(c) for c in conds]


def pediatric_dose_hint(age_years: float, age_rule_vi: str | None) -> str | None:
    """Map a free-text age rule + age to a short hint. Returns None if no rule."""
    if not age_rule_vi:
        return None
    rule = age_rule_vi.lower()
    if age_years < 6 and ("người lớn" in rule and "trẻ" not in rule):
        return "Công thức dành cho người lớn — không dùng cho trẻ dưới 6 tuổi."
    return age_rule_vi
