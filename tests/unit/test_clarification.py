"""Unit tests for graph.clarification helpers + check_clarification node."""

from __future__ import annotations

from sales_agent.api.schemas import Clarification
from sales_agent.graph import nodes_nlu
from sales_agent.graph.clarification import apply_reply, detect_pending


def _item(drug_name: str = "Amoxicillin 500mg") -> dict:
    return {
        "drug_name": drug_name,
        "active_ingredient": "amoxicillin",
        "strength": "500mg",
        "dosage_form": "viên nang",
        "quantity": 21,
        "dosage_instruction": "1 viên x 3 lần/ngày x 7 ngày",
    }


def _cand(sku: str, name_vi: str, qty: int = 0) -> dict:
    return {
        "sku": sku,
        "name_vi": name_vi,
        "strength": "500mg",
        "dosage_form": "viên nang",
        "qty_on_hand": qty,
        "rx_only": True,
    }


def test_detect_pending_returns_none_when_all_resolved() -> None:
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "brand_exact"}]},
        "nlu_candidates": {},
    }
    assert detect_pending(state) is None


def test_detect_pending_flags_unresolved() -> None:
    state = {
        "prescription_items": [_item(drug_name="Thuoc la")],
        "parsed": {"resolutions": [{"resolution": "unresolved"}]},
        "nlu_candidates": {},
    }
    c = detect_pending(state)
    assert c is not None
    assert c.kind == "unresolved"
    assert c.item_index == 0
    assert "Thuoc la" in c.question_vi
    assert c.options == []


def test_detect_pending_flags_ambiguous_with_options() -> None:
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {
            "0": [
                _cand("SKU-022", "Amoxicillin 500mg DHG", qty=50),
                _cand("SKU-023", "Amoxicillin 500 Stada", qty=35),
            ]
        },
    }
    c = detect_pending(state)
    assert c is not None
    assert c.kind == "ambiguous"
    assert c.item_index == 0
    assert len(c.options) == 2
    assert c.options[0].sku == "SKU-022"
    assert c.options[0].qty_on_hand == 50


def test_detect_pending_ignores_single_candidate() -> None:
    """Single-option lists are not ambiguity."""
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {"0": [_cand("SKU-022", "Amoxicillin 500mg DHG", qty=50)]},
    }
    assert detect_pending(state) is None


def test_apply_reply_ambiguous_by_number() -> None:
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {
            "0": [
                _cand("SKU-022", "Amoxicillin 500mg DHG", qty=50),
                _cand("SKU-023", "Amoxicillin 500 Stada", qty=35),
            ]
        },
    }
    pending = detect_pending(state)
    assert pending is not None
    apply_reply(state, "2", pending)
    # Item now bound to Stada.
    assert state["prescription_items"][0]["drug_name"] == "Amoxicillin 500 Stada"
    # Resolution overwritten to brand_exact with chosen SKU.
    assert state["parsed"]["resolutions"][0] == {
        "sku": "SKU-023",
        "name_vi": "Amoxicillin 500 Stada",
        "resolution": "brand_exact",
    }
    # Candidates cleared for this index -> detect_pending finds nothing.
    assert detect_pending(state) is None


def test_apply_reply_ambiguous_by_brand_substring() -> None:
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {
            "0": [
                _cand("SKU-022", "Amoxicillin 500mg DHG"),
                _cand("SKU-023", "Amoxicillin 500 Stada"),
            ]
        },
    }
    pending = detect_pending(state)
    apply_reply(state, "stada", pending)  # case-insensitive substring
    assert state["prescription_items"][0]["drug_name"] == "Amoxicillin 500 Stada"


def test_apply_reply_ambiguous_by_sku() -> None:
    state = {
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {
            "0": [
                _cand("SKU-022", "Amoxicillin 500mg DHG"),
                _cand("SKU-023", "Amoxicillin 500 Stada"),
            ]
        },
    }
    pending = detect_pending(state)
    apply_reply(state, "SKU-023", pending)
    assert state["parsed"]["resolutions"][0]["sku"] == "SKU-023"


def test_apply_reply_unresolved_uses_free_text() -> None:
    state = {
        "prescription_items": [_item(drug_name="unknown")],
        "parsed": {"resolutions": [{"resolution": "unresolved"}]},
        "nlu_candidates": {},
    }
    pending = detect_pending(state)
    assert pending is not None
    apply_reply(state, "Panadol Extra", pending)
    assert state["prescription_items"][0]["drug_name"] == "Panadol Extra"
    assert state["parsed"]["resolutions"][0]["resolution"] == "brand_exact"


def test_check_clarification_node_sets_pending_for_prescription() -> None:
    state = {
        "flow": "prescription",
        "prescription_items": [_item()],
        "parsed": {"resolutions": [{"resolution": "inn_form"}]},
        "nlu_candidates": {
            "0": [
                _cand("SKU-022", "Amoxicillin 500mg DHG"),
                _cand("SKU-023", "Amoxicillin 500 Stada"),
            ]
        },
    }
    out = nodes_nlu.check_clarification(state)
    pending = out.get("pending_clarification")
    assert pending is not None
    assert pending["kind"] == "ambiguous"
    # Can round-trip through pydantic.
    Clarification.model_validate(pending)


def test_check_clarification_node_noop_for_symptom() -> None:
    state = {"flow": "symptom", "symptoms_vi": ["sốt"]}
    out = nodes_nlu.check_clarification(state)
    assert out.get("pending_clarification") is None


def test_format_clarification_reply_builds_final_response() -> None:
    state = {
        "pending_clarification": {
            "kind": "ambiguous",
            "item_index": 0,
            "item_summary": "Amoxicillin 500mg",
            "question_vi": "Bạn muốn chọn loại nào?",
            "options": [],
        }
    }
    out = nodes_nlu.format_clarification_reply(state)
    fr = out["final_response"]
    assert fr["status"] == "awaiting_clarification"
    assert fr["clarification"]["question_vi"] == "Bạn muốn chọn loại nào?"
