"""Prescription-flow nodes."""

from __future__ import annotations

import json
import logging

from ..db.pg import session_scope
from ..llm.client import chat, load_prompt
from ..tools.equivalents import find_equivalent_drugs
from ..tools.inventory import check_stock, check_stock_by_name
from ..tools.safety import DISCLAIMER_VI, get_contraindications
from .state import AgentState, InventoryResult

logger = logging.getLogger(__name__)


def check_inventory(state: AgentState) -> AgentState:
    results: list[InventoryResult] = []
    with session_scope() as sess:
        for item in state.get("prescription_items") or []:
            # Prefer exact brand match so the prescribed SKU's stock determines status.
            # Only fall back to INN+strength+form lookup if the brand isn't in the catalog
            # (drug_name may be missing or a different brand label than we stock).
            stock = check_stock_by_name(sess, item.get("drug_name", ""))
            if stock["status"] == "not_carried":
                stock = check_stock(
                    sess,
                    inn=item["active_ingredient"],
                    strength=item["strength"],
                    dosage_form=item["dosage_form"],
                )
                # Even if a generic is found via INN, mark the prescribed brand as
                # not_carried so the substitute flow still proposes alternatives.
                if stock["status"] == "in_stock":
                    stock = {**stock, "status": "not_carried"}
            final_status = stock["status"]
            matched = None
            if stock["product_id"]:
                matched = {
                    "product_id": stock["product_id"],
                    "sku": stock["sku"],
                    "name_vi": stock["name_vi"],
                    "rx_only": stock["rx_only"],
                }
            results.append(
                InventoryResult(
                    item=item,
                    status=final_status,
                    matched_product=matched,
                    qty_on_hand=stock["qty_on_hand"],
                    substitutes=[],
                    safety_notes=[],
                )
            )
    state["inventory_results"] = results
    return state


def find_substitutes_for_missing(state: AgentState) -> AgentState:
    with session_scope() as sess:
        for r in state.get("inventory_results") or []:
            if r["status"] == "in_stock":
                continue
            item = r["item"]
            src_name = (r.get("matched_product") or {}).get("name_vi") or item.get(
                "drug_name", ""
            )
            rx_only = bool((r.get("matched_product") or {}).get("rx_only", False))
            subs = find_equivalent_drugs(
                sess,
                src_name=src_name,
                inn=item["active_ingredient"],
                strength=item["strength"],
                dosage_form=item["dosage_form"],
                rx_only=rx_only,
                only_in_stock=True,
            )
            r["substitutes"] = [dict(s) for s in subs[:5]]
    return state


def safety_check(state: AgentState) -> AgentState:
    allergies = [a.lower() for a in (state.get("patient_allergies") or [])]
    pregnancy = bool(state.get("patient_pregnancy"))
    age = float(state.get("patient_age_years") or 0)

    for r in state.get("inventory_results") or []:
        notes: list[str] = []
        inn = r["item"].get("active_ingredient", "").lower()
        if any(a in inn or inn in a for a in allergies if a):
            notes.append(f"Bệnh nhân khai dị ứng với {inn} — không bán.")
        matched = r.get("matched_product") or {}
        if matched.get("name_vi"):
            cons = get_contraindications(matched["name_vi"])
            if pregnancy and any("thai" in c.lower() for c in cons):
                notes.append("Chống chỉ định ở phụ nữ có thai.")
            if age < 12 and any("trẻ" in c.lower() for c in cons):
                notes.append("Cần thận trọng / chống chỉ định ở trẻ em.")
        r["safety_notes"] = notes
    return state


def format_prescription_reply(state: AgentState) -> AgentState:
    payload = {
        "patient": {
            "age_years": state.get("patient_age_years"),
            "pregnancy": state.get("patient_pregnancy"),
            "allergies": state.get("patient_allergies") or [],
        },
        "items": state.get("inventory_results") or [],
    }
    summary = _render_summary(payload)
    state["summary_vi"] = summary
    state["final_response"] = {
        "flow": "prescription",
        "items": state.get("inventory_results") or [],
        "summary_vi": summary,
        "disclaimer": DISCLAIMER_VI,
    }
    return state


def _render_summary(payload: dict) -> str:
    try:
        prompt = load_prompt("prescription_format").replace(
            "{data_json}", json.dumps(payload, ensure_ascii=False, default=str)
        )
        return chat(
            system="Bạn là trợ lý nhà thuốc. Trả lời bằng tiếng Việt, ngắn gọn.",
            user=prompt,
            temperature=0.1,
        )
    except Exception:
        logger.exception("LLM render failed; falling back to template")
        return _fallback_summary(payload)


def _fallback_summary(payload: dict) -> str:
    lines: list[str] = ["### Tóm tắt"]
    for r in payload.get("items") or []:
        item = r["item"]
        status = r["status"]
        name = item.get("drug_name") or item.get("active_ingredient")
        if status == "in_stock":
            lines.append(f"- {name}: có sẵn ({r['qty_on_hand']} đơn vị).")
        elif status == "out_of_stock":
            lines.append(f"- {name}: HẾT HÀNG.")
        else:
            lines.append(f"- {name}: KHÔNG KINH DOANH.")
        for s in r.get("substitutes", [])[:2]:
            lines.append(
                f"    • Gợi ý thay thế: {s['name_vi']} ({s['kind']}, còn {s['qty_on_hand']})."
            )
        for n in r.get("safety_notes", []):
            lines.append(f"    ⚠ {n}")
    return "\n".join(lines)
