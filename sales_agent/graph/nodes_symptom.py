"""Symptom-flow nodes (OTC advisory)."""

from __future__ import annotations

import json
import logging

from ..db.pg import session_scope
from ..llm.client import chat, embed_one, load_prompt
from ..tools.formulas import search_otc_formulas
from ..tools.redflags import get_redflags
from ..tools.safety import DISCLAIMER_VI, is_blocked_for_otc, pediatric_dose_hint
from .state import AgentState, FormulaSuggestionOut

logger = logging.getLogger(__name__)


_SYMPTOM_SYNONYMS: dict[str, list[str]] = {
    "sổ mũi": ["chảy nước mũi", "ngạt mũi"],
    "sốt": ["nóng sốt"],
    "đau họng": ["rát họng", "viêm họng"],
    "ho khan": ["ho không đờm"],
    "ho có đờm": ["ho đàm", "ho có đàm"],
}


def extract_symptoms(state: AgentState) -> AgentState:
    raw = state.get("symptoms_vi") or []
    cleaned: list[str] = []
    for s in raw:
        t = s.strip().lower()
        if t:
            cleaned.append(t)
    state["symptoms_vi"] = cleaned
    return state


def redflag_check(state: AgentState) -> AgentState:
    flags = get_redflags(
        state.get("symptoms_vi") or [],
        age_years=float(state.get("patient_age_years") or 0),
        pregnancy=bool(state.get("patient_pregnancy")),
        duration_days=state.get("duration_days"),
    )
    state["red_flags"] = flags
    return state


def retrieve_formulas(state: AgentState) -> AgentState:
    if state.get("red_flags"):
        state["candidate_formulas"] = []
        return state

    query = ", ".join(state.get("symptoms_vi") or [])
    if not query:
        state["candidate_formulas"] = []
        return state

    try:
        vec = embed_one(query)
    except Exception:
        logger.exception("embedding failed; returning empty candidates")
        state["candidate_formulas"] = []
        return state

    with session_scope() as sess:
        rows = search_otc_formulas(
            sess,
            query_embedding=vec,
            age_years=float(state.get("patient_age_years") or 0),
            pregnancy=bool(state.get("patient_pregnancy")),
            top_k=5,
        )
    state["candidate_formulas"] = [
        FormulaSuggestionOut(
            formula_id=r["formula_id"],
            code=r["code"],
            name_vi=r["name_vi"],
            score=r["score"],
            items=[dict(it) for it in r["items"]],
            warnings=[],
        )
        for r in rows
    ]
    return state


def rank_and_adapt_by_age(state: AgentState) -> AgentState:
    """Drop Rx-only items/formulas and adapt dosing hints by age."""
    age = float(state.get("patient_age_years") or 0)
    allergies = [a.lower() for a in (state.get("patient_allergies") or [])]
    adapted: list[FormulaSuggestionOut] = []

    for f in state.get("candidate_formulas") or []:
        warnings: list[str] = []
        keep_items = []
        dropped_primary = False

        for it in f.get("items") or []:
            inn = it["active_ingredient"].lower()
            if is_blocked_for_otc(inn):
                if it["role"] == "primary":
                    dropped_primary = True
                    break
                warnings.append(f"Đã loại {inn} (thuộc nhóm cần kê đơn).")
                continue
            if any(a in inn or inn in a for a in allergies if a):
                if it["role"] == "primary":
                    dropped_primary = True
                    break
                warnings.append(f"Bỏ {inn} do khách khai dị ứng.")
                continue
            hint = pediatric_dose_hint(age, it.get("age_rule_vi"))
            if hint and hint != it.get("age_rule_vi"):
                it = {**it, "age_rule_vi": hint}
            keep_items.append(it)

        if dropped_primary:
            continue
        if not keep_items:
            continue

        adapted.append(
            FormulaSuggestionOut(
                formula_id=f["formula_id"],
                code=f["code"],
                name_vi=f["name_vi"],
                score=f["score"],
                items=keep_items,
                warnings=warnings,
            )
        )

    # Sort by score desc, take top 3
    adapted.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    state["candidate_formulas"] = adapted[:3]
    return state


def format_symptom_reply(state: AgentState) -> AgentState:
    red_flags = state.get("red_flags") or []
    suggestions = state.get("candidate_formulas") or []
    payload = {
        "patient": {
            "age_years": state.get("patient_age_years"),
            "pregnancy": state.get("patient_pregnancy"),
            "allergies": state.get("patient_allergies") or [],
        },
        "symptoms": state.get("symptoms_vi") or [],
        "duration_days": state.get("duration_days"),
        "red_flags": red_flags,
        "suggestions": suggestions,
    }
    summary = _render_summary(payload, refer_to_doctor=bool(red_flags))
    state["summary_vi"] = summary
    state["final_response"] = {
        "flow": "symptom",
        "red_flags": red_flags,
        "suggestions": [] if red_flags else suggestions,
        "summary_vi": summary,
        "disclaimer": DISCLAIMER_VI,
    }
    return state


def _render_summary(payload: dict, *, refer_to_doctor: bool) -> str:
    try:
        prompt = load_prompt("symptom_format").replace(
            "{data_json}", json.dumps(payload, ensure_ascii=False, default=str)
        )
        return chat(
            system="Bạn là trợ lý nhà thuốc. Trả lời bằng tiếng Việt, ngắn gọn.",
            user=prompt,
            temperature=0.1,
        )
    except Exception:
        logger.exception("LLM render failed; using template fallback")
        return _fallback(payload, refer_to_doctor=refer_to_doctor)


def _fallback(payload: dict, *, refer_to_doctor: bool) -> str:
    if refer_to_doctor:
        lines = ["### Gợi ý tư vấn", "Khách có dấu hiệu cảnh báo — khuyên đi khám bác sĩ."]
        lines.append("### Lưu ý")
        for f in payload.get("red_flags", []):
            lines.append(f"- {f}")
        return "\n".join(lines)

    lines = ["### Gợi ý tư vấn"]
    suggestions = payload.get("suggestions") or []
    if not suggestions:
        lines.append("Không tìm được công thức OTC phù hợp — đề nghị khách đi khám.")
        return "\n".join(lines)

    lines.append(f"Top {len(suggestions)} gợi ý OTC phù hợp triệu chứng.")
    lines.append("### Thuốc đề xuất")
    for s in suggestions:
        lines.append(f"- **{s['name_vi']}** (score={s['score']:.2f})")
        for it in s["items"]:
            line = (
                f"    • {it['active_ingredient']} — {it['dose_per_take_vi']} × "
                f"{it['frequency_per_day']} lần/ngày × {it['duration_days']} ngày"
            )
            if it.get("age_rule_vi"):
                line += f". ({it['age_rule_vi']})"
            lines.append(line)
    return "\n".join(lines)
