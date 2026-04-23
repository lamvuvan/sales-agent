"""Rule-based red-flag detection for symptom flow (OTC)."""

from __future__ import annotations

# Synonyms/keywords are matched case-insensitively as substrings.
_DYSPNEA = ["khó thở", "tím tái", "thở rút lõm", "thở gấp"]
_CHEST = ["đau ngực", "đau thắt ngực"]
_SEVERE_ABD = ["đau bụng dữ dội", "đau bụng quặn"]
_GI_BLEED = ["nôn ra máu", "phân đen", "phân có máu", "đi ngoài ra máu"]
_NEURO = ["co giật", "lơ mơ", "cứng gáy", "mất ý thức", "yếu liệt"]
_ALLERGY_SEVERE = ["phù mạch", "phát ban toàn thân", "sốc phản vệ"]
_HIGH_FEVER = ["sốt cao", "sốt 39", "sốt 40", "sốt >39", "sốt hơn 39"]
_DEHYDRATION = ["mất nước", "khô môi", "tiểu ít", "không tiểu"]


def _contains(symptom: str, needles: list[str]) -> bool:
    s = symptom.lower()
    return any(n in s for n in needles)


def _any(symptoms: list[str], needles: list[str]) -> bool:
    return any(_contains(s, needles) for s in symptoms)


def get_redflags(
    symptoms_vi: list[str],
    *,
    age_years: float,
    pregnancy: bool = False,
    duration_days: int | None = None,
) -> list[str]:
    """Return a list of red-flag codes (Vietnamese messages). Empty = safe to advise."""
    flags: list[str] = []

    if _any(symptoms_vi, _DYSPNEA):
        flags.append("khó thở / suy hô hấp — cần khám ngay")
    if _any(symptoms_vi, _CHEST):
        flags.append("đau ngực — cần loại trừ tim mạch")
    if _any(symptoms_vi, _SEVERE_ABD):
        flags.append("đau bụng dữ dội — cần khám ngoại khoa")
    if _any(symptoms_vi, _GI_BLEED):
        flags.append("xuất huyết tiêu hoá — cần khám ngay")
    if _any(symptoms_vi, _NEURO):
        flags.append("triệu chứng thần kinh — cần khám ngay")
    if _any(symptoms_vi, _ALLERGY_SEVERE):
        flags.append("phản ứng dị ứng nặng — cần cấp cứu")

    has_fever = any("sốt" in s.lower() for s in symptoms_vi)
    has_high_fever = _any(symptoms_vi, _HIGH_FEVER)

    if age_years < 0.25 and has_fever:
        flags.append("trẻ dưới 3 tháng có sốt — phải đi khám")
    if age_years < 6 and _any(symptoms_vi, _DEHYDRATION):
        flags.append("trẻ nhỏ có dấu hiệu mất nước — cần khám")
    if has_high_fever:
        flags.append("sốt cao — theo dõi sát, cân nhắc đi khám nếu kéo dài")
    if duration_days is not None and duration_days > 3 and has_fever:
        flags.append("sốt kéo dài >3 ngày — cần đi khám")
    if pregnancy:
        flags.append("phụ nữ có thai — ưu tiên tư vấn bác sĩ trước khi dùng thuốc")
    if age_years >= 65 and _any(symptoms_vi, ["khó thở", "sốt cao", "đau ngực"]):
        flags.append("người cao tuổi với triệu chứng nặng — cần khám")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out
