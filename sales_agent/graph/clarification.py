"""Detect ambiguous/unresolved prescription items and apply user replies.

Responsibilities split:
- ``detect_pending`` scans state and returns the next clarification (or None).
- ``apply_reply`` mutates state to resolve the pending clarification using
  the user's free-text reply (option number, SKU, or brand name).

These helpers are pure (no I/O) so they can be unit-tested without DB/LLM.
"""

from __future__ import annotations

from typing import Any

from ..api.schemas import Clarification, ClarificationOption


def _summarise(item: dict) -> str:
    parts = [
        item.get("drug_name"),
        item.get("active_ingredient"),
        item.get("strength"),
        item.get("dosage_form"),
    ]
    return " · ".join(p for p in parts if p)


def detect_pending(state: dict) -> Clarification | None:
    """Return the first item needing clarification, or None if all items are resolved.

    Reads state['prescription_items'] and state['parsed']['resolutions'] (added by
    resolve_catalog) plus state['nlu_candidates'] keyed by item index.
    """
    items = state.get("prescription_items") or []
    resolutions = ((state.get("parsed") or {}).get("resolutions") or [])
    candidates_map = state.get("nlu_candidates") or {}

    for idx, item in enumerate(items):
        res = resolutions[idx] if idx < len(resolutions) else {}
        resolution_kind = res.get("resolution")

        if resolution_kind == "unresolved":
            return Clarification(
                kind="unresolved",
                item_index=idx,
                item_summary=_summarise(item),
                question_vi=(
                    f"Không tìm thấy thuốc '{item.get('drug_name', '')}' trong kho. "
                    f"Bạn có thể cho biết tên thương mại chính xác (hoặc SKU) không?"
                ),
                options=[],
            )

        cands = candidates_map.get(str(idx)) or candidates_map.get(idx) or []
        if cands and len(cands) > 1:
            options = [ClarificationOption.model_validate(c) for c in cands]
            return Clarification(
                kind="ambiguous",
                item_index=idx,
                item_summary=_summarise(item),
                question_vi=(
                    f"'{item.get('drug_name', '')}' có nhiều phiên bản trong kho. "
                    f"Bạn muốn chọn loại nào?"
                ),
                options=options,
            )

    return None


def apply_reply(state: dict, reply: str, pending: Clarification) -> None:
    """Resolve the pending clarification based on the user's text reply.

    Accepted answer formats for ``ambiguous``:
      - option number ("1", "2", ...)
      - SKU exact match
      - brand name substring match (case-insensitive)

    For ``unresolved``: the reply replaces drug_name; resolution is deferred
    to the next resolve_catalog pass (we mark it as 'brand_exact' optimistically;
    downstream inventory will still catch not_carried).

    Mutates ``state`` in place. Removes the resolved item's candidates entry.
    """
    idx = pending.item_index
    items = state.get("prescription_items") or []
    if idx >= len(items):
        return
    item = dict(items[idx])
    reply = reply.strip()

    if pending.kind == "ambiguous" and pending.options:
        chosen: ClarificationOption | None = None
        # Number?
        if reply.isdigit():
            n = int(reply)
            if 1 <= n <= len(pending.options):
                chosen = pending.options[n - 1]
        if chosen is None:
            lower = reply.lower()
            # SKU exact match.
            for opt in pending.options:
                if opt.sku.lower() == lower:
                    chosen = opt
                    break
        if chosen is None:
            # Brand substring match.
            lower = reply.lower()
            for opt in pending.options:
                if lower in opt.name_vi.lower():
                    chosen = opt
                    break
        if chosen is None:
            # Default: first option (keep UX forward-moving; UI can re-ask).
            chosen = pending.options[0]

        item["drug_name"] = chosen.name_vi
        item["strength"] = chosen.strength
        item["dosage_form"] = chosen.dosage_form
        _mark_resolution(state, idx, "brand_exact", sku=chosen.sku, name_vi=chosen.name_vi)
    else:  # unresolved
        item["drug_name"] = reply
        _mark_resolution(state, idx, "brand_exact", sku=None, name_vi=reply)

    items[idx] = item
    state["prescription_items"] = items

    # Remove the candidate list for this index so detect_pending no longer fires.
    cands = state.get("nlu_candidates") or {}
    cands.pop(str(idx), None)
    cands.pop(idx, None)
    state["nlu_candidates"] = cands


def _mark_resolution(state: dict, idx: int, kind: str, *, sku: str | None, name_vi: str | None) -> None:
    parsed = state.get("parsed") or {}
    resolutions: list[dict[str, Any]] = list(parsed.get("resolutions") or [])
    while len(resolutions) <= idx:
        resolutions.append({})
    resolutions[idx] = {"sku": sku, "name_vi": name_vi, "resolution": kind}
    parsed["resolutions"] = resolutions
    state["parsed"] = parsed
