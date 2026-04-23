"""Assemble the LangGraph state machine."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from .nodes_common import audit_log, intent_router
from .nodes_nlu import nlu_extract, resolve_catalog
from .nodes_prescription import (
    check_inventory,
    find_substitutes_for_missing,
    format_prescription_reply,
    safety_check,
)
from .nodes_symptom import (
    extract_symptoms,
    format_symptom_reply,
    rank_and_adapt_by_age,
    redflag_check,
    retrieve_formulas,
)
from .state import AgentState


def _route_flow(state: AgentState) -> str:
    return state.get("flow", "symptom")


def _route_after_redflag(state: AgentState) -> str:
    return "format_symptom_reply" if state.get("red_flags") else "retrieve_formulas"


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(AgentState)

    # NLU (no-op when raw_text empty)
    g.add_node("nlu_extract", nlu_extract)
    g.add_node("resolve_catalog", resolve_catalog)

    g.add_node("intent_router", intent_router)

    # Prescription subgraph
    g.add_node("check_inventory", check_inventory)
    g.add_node("find_substitutes_for_missing", find_substitutes_for_missing)
    g.add_node("safety_check", safety_check)
    g.add_node("format_prescription_reply", format_prescription_reply)

    # Symptom subgraph
    g.add_node("extract_symptoms", extract_symptoms)
    g.add_node("redflag_check", redflag_check)
    g.add_node("retrieve_formulas", retrieve_formulas)
    g.add_node("rank_and_adapt_by_age", rank_and_adapt_by_age)
    g.add_node("format_symptom_reply", format_symptom_reply)

    g.add_node("audit_log", audit_log)

    g.add_edge(START, "nlu_extract")
    g.add_edge("nlu_extract", "intent_router")
    g.add_conditional_edges(
        "intent_router",
        _route_flow,
        {
            "prescription": "resolve_catalog",
            "symptom": "extract_symptoms",
        },
    )

    g.add_edge("resolve_catalog", "check_inventory")
    g.add_edge("check_inventory", "find_substitutes_for_missing")
    g.add_edge("find_substitutes_for_missing", "safety_check")
    g.add_edge("safety_check", "format_prescription_reply")
    g.add_edge("format_prescription_reply", "audit_log")

    g.add_edge("extract_symptoms", "redflag_check")
    g.add_conditional_edges(
        "redflag_check",
        _route_after_redflag,
        {
            "retrieve_formulas": "retrieve_formulas",
            "format_symptom_reply": "format_symptom_reply",
        },
    )
    g.add_edge("retrieve_formulas", "rank_and_adapt_by_age")
    g.add_edge("rank_and_adapt_by_age", "format_symptom_reply")
    g.add_edge("format_symptom_reply", "audit_log")

    g.add_edge("audit_log", END)

    return g.compile()
