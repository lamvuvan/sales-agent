"""Integration tests for POST /chat (mocked LLM + DB)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

from sales_agent.api.main import create_app
from sales_agent.api.schemas import NluOutput, NluPrescriptionItem, PatientOverrides
from sales_agent.graph import nodes_common, nodes_nlu, nodes_prescription, nodes_symptom
from sales_agent.session import InMemorySessionStore, set_session_store


@contextmanager
def _fake_session():
    yield object()


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    """Ensure each test gets a freshly compiled graph (lru_cache bust) and a
    clean in-memory session store (no Redis dependency)."""
    from sales_agent.graph import builder

    builder.build_graph.cache_clear()
    set_session_store(InMemorySessionStore())
    yield
    builder.build_graph.cache_clear()


@pytest.fixture
def mocked_graph(monkeypatch: pytest.MonkeyPatch):
    """Neutralize every external dependency for both flows."""
    # NLU node — will be overridden per test by setting extractor return.
    # DB sessions:
    monkeypatch.setattr(nodes_nlu, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_symptom, "session_scope", _fake_session)
    monkeypatch.setattr(nodes_common, "session_scope", _fake_session)

    # Prescription subgraph deps:
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock_by_name",
        lambda sess, name: {
            "status": "out_of_stock",
            "product_id": "p-001",
            "sku": "SKU-001",
            "name_vi": name,
            "qty_on_hand": 0,
            "rx_only": False,
        },
    )
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock",
        lambda *a, **k: {
            "status": "not_carried",
            "product_id": None,
            "sku": None,
            "name_vi": None,
            "qty_on_hand": 0,
            "rx_only": False,
        },
    )
    monkeypatch.setattr(
        nodes_prescription,
        "find_equivalent_drugs",
        lambda sess, **k: [
            {
                "name_vi": "Hapacol 500",
                "inn": "paracetamol",
                "strength": "500mg",
                "dosage_form": "viên nén",
                "kind": "generic",
                "confidence": 1.0,
                "rx_only": False,
                "qty_on_hand": 80,
            }
        ],
    )
    monkeypatch.setattr(nodes_prescription, "get_contraindications", lambda name: [])
    monkeypatch.setattr(nodes_prescription, "chat", lambda **k: "Tóm tắt demo.")

    # Symptom subgraph deps:
    monkeypatch.setattr(nodes_symptom, "embed_one", lambda text: [0.0] * 8)
    monkeypatch.setattr(
        nodes_symptom,
        "search_otc_formulas",
        lambda sess, **k: [
            {
                "formula_id": "f1",
                "code": "F-FLU-ADULT",
                "name_vi": "Cảm cúm người lớn",
                "score": 0.92,
                "min_age_years": 12,
                "max_age_years": None,
                "pregnancy_safe": False,
                "notes_vi": None,
                "items": [
                    {
                        "active_ingredient": "paracetamol",
                        "strength_hint": "500mg",
                        "dose_per_take_vi": "1 viên",
                        "frequency_per_day": 3,
                        "duration_days": 3,
                        "age_rule_vi": "người lớn",
                        "role": "primary",
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(nodes_symptom, "chat", lambda **k: "Tư vấn demo.")


def test_chat_prescription_flow(mocked_graph, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nodes_nlu,
        "extract_intent_and_payload",
        lambda raw: NluOutput(
            intent="prescription",
            patient_overrides=PatientOverrides(age_years=None, pregnancy=None, allergies=[]),
            prescription_items=[
                NluPrescriptionItem(
                    brand="Panadol 500mg",
                    active_ingredient="paracetamol",
                    strength="500mg",
                    dosage_form="viên nén",
                    quantity=15,
                    dosage_instruction="1 viên x 3 lần/ngày x 5 ngày",
                )
            ],
            symptoms_vi=None,
            duration_days=None,
        ),
    )
    # Resolver: pretend brand_exact hit on Panadol 500mg.
    monkeypatch.setattr(
        nodes_nlu,
        "resolve_prescription_items",
        lambda sess, extracted: [
            {
                "item": {
                    "drug_name": "Panadol 500mg",
                    "active_ingredient": "paracetamol",
                    "strength": "500mg",
                    "dosage_form": "viên nén",
                    "quantity": 15,
                    "dosage_instruction": "1 viên x 3 lần/ngày x 5 ngày",
                },
                "matched_sku": "SKU-001",
                "matched_name_vi": "Panadol 500mg",
                "resolution": "brand_exact",
            }
        ],
    )

    client = TestClient(create_app())
    r = client.post(
        "/chat",
        json={
            "raw_text": "Panadol 500mg, 1 viên x 3 lần/ngày x 5 ngày",
            "patient": {"age_years": 34},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["flow"] == "prescription"
    assert body["parsed"]["intent"] == "prescription"
    assert body["items"][0]["item"]["active_ingredient"] == "paracetamol"
    assert body["items"][0]["status"] == "out_of_stock"
    assert body["items"][0]["substitutes"][0]["name_vi"] == "Hapacol 500"


def test_chat_symptom_flow(mocked_graph, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nodes_nlu,
        "extract_intent_and_payload",
        lambda raw: NluOutput(
            intent="symptom",
            patient_overrides=PatientOverrides(age_years=28, pregnancy=False, allergies=[]),
            prescription_items=None,
            symptoms_vi=["sốt nhẹ", "sổ mũi"],
            duration_days=2,
        ),
    )
    client = TestClient(create_app())
    r = client.post(
        "/chat",
        json={
            "raw_text": "Khách 28 tuổi bị sốt nhẹ, sổ mũi 2 ngày nay",
            "patient": {"age_years": 28},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["flow"] == "symptom"
    assert body["parsed"]["symptoms_vi"] == ["sốt nhẹ", "sổ mũi"]
    assert body["suggestions"][0]["code"] == "F-FLU-ADULT"


def test_chat_rejects_empty_raw_text() -> None:
    client = TestClient(create_app())
    r = client.post("/chat", json={"raw_text": ""})
    assert r.status_code == 422


def test_chat_request_age_beats_llm(mocked_graph, monkeypatch: pytest.MonkeyPatch) -> None:
    """Request patient.age_years=10 must win over LLM-extracted 50 (safety)."""
    monkeypatch.setattr(
        nodes_nlu,
        "extract_intent_and_payload",
        lambda raw: NluOutput(
            intent="symptom",
            patient_overrides=PatientOverrides(age_years=50, pregnancy=False, allergies=[]),
            prescription_items=None,
            symptoms_vi=["sốt"],
            duration_days=1,
        ),
    )
    captured_age: dict = {}

    def capture_get_redflags(symptoms_vi, *, age_years, pregnancy=False, duration_days=None):
        captured_age["age"] = age_years
        return []

    # redflag_check reads get_redflags via module globals -> patch takes effect.
    monkeypatch.setattr(nodes_symptom, "get_redflags", capture_get_redflags)

    client = TestClient(create_app())
    r = client.post(
        "/chat",
        json={"raw_text": "Khách 50 tuổi bị sốt", "patient": {"age_years": 10}},
    )
    assert r.status_code == 200, r.text
    # LLM-extracted age still surfaced in parsed for transparency.
    assert r.json()["parsed"]["patient_overrides"]["age_years"] == 50
    # But the actual computation used the request's age (10), not LLM's 50.
    assert captured_age["age"] == 10


# -----------------------------------------------------------------------------
# Multi-turn clarification
# -----------------------------------------------------------------------------


def _mock_ambiguous_prescription(monkeypatch: pytest.MonkeyPatch) -> None:
    """NLU returns a single Amoxicillin item; resolver sees 2 SKUs (ambiguous)."""
    monkeypatch.setattr(
        nodes_nlu,
        "extract_intent_and_payload",
        lambda raw: NluOutput(
            intent="prescription",
            patient_overrides=PatientOverrides(age_years=None, pregnancy=None, allergies=[]),
            prescription_items=[
                NluPrescriptionItem(
                    brand=None,
                    active_ingredient="amoxicillin",
                    strength="500mg",
                    dosage_form="viên nang",
                    quantity=21,
                    dosage_instruction="1 viên x 3 lần/ngày x 7 ngày",
                )
            ],
            symptoms_vi=None,
            duration_days=None,
        ),
    )
    monkeypatch.setattr(
        nodes_nlu,
        "resolve_prescription_items",
        lambda sess, extracted: [
            {
                "item": {
                    "drug_name": "Amoxicillin 500mg DHG",
                    "active_ingredient": "amoxicillin",
                    "strength": "500mg",
                    "dosage_form": "viên nang",
                    "quantity": 21,
                    "dosage_instruction": "1 viên x 3 lần/ngày x 7 ngày",
                },
                "matched_sku": "SKU-022",
                "matched_name_vi": "Amoxicillin 500mg DHG",
                "resolution": "inn_form",
                "candidates": [
                    {
                        "sku": "SKU-022",
                        "name_vi": "Amoxicillin 500mg DHG",
                        "strength": "500mg",
                        "dosage_form": "viên nang",
                        "qty_on_hand": 50,
                        "rx_only": True,
                    },
                    {
                        "sku": "SKU-023",
                        "name_vi": "Amoxicillin 500 Stada",
                        "strength": "500mg",
                        "dosage_form": "viên nang",
                        "qty_on_hand": 35,
                        "rx_only": True,
                    },
                ],
            }
        ],
    )


def test_chat_ambiguous_returns_clarification(
    mocked_graph, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_ambiguous_prescription(monkeypatch)

    client = TestClient(create_app())
    r = client.post(
        "/chat",
        json={
            "raw_text": "Amoxicillin 500mg, 1 viên x 3 lần/ngày x 7 ngày",
            "patient": {"age_years": 34},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awaiting_clarification"
    assert body["session_id"]  # non-empty
    assert body["clarification"]["kind"] == "ambiguous"
    assert len(body["clarification"]["options"]) == 2
    assert body["clarification"]["options"][0]["sku"] == "SKU-022"
    # Downstream flow (check_inventory, substitutes, summary) was skipped.
    assert body["items"] is None
    assert body["summary_vi"] == body["clarification"]["question_vi"]


def test_chat_clarification_reply_completes_flow(
    mocked_graph, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_ambiguous_prescription(monkeypatch)

    client = TestClient(create_app())
    # Turn 1: get clarification.
    r1 = client.post(
        "/chat",
        json={"raw_text": "Amoxicillin 500mg", "patient": {"age_years": 34}},
    )
    sid = r1.json()["session_id"]
    assert sid

    # Turn 2: reply "2" -> pick Stada.
    r2 = client.post("/chat", json={"raw_text": "2", "session_id": sid})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "complete"
    assert body["flow"] == "prescription"
    assert body["items"] is not None
    # The picked brand flowed through to check_inventory -> its drug_name is on the line.
    assert body["items"][0]["item"]["drug_name"] == "Amoxicillin 500 Stada"


def test_chat_clarification_unknown_session_returns_404() -> None:
    client = TestClient(create_app())
    r = client.post(
        "/chat", json={"raw_text": "Stada", "session_id": "does-not-exist"}
    )
    assert r.status_code == 404


def test_chat_clarification_session_without_pending_returns_409(
    mocked_graph, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay on a session whose pending was cleared should 409."""
    from sales_agent.session import get_session_store

    store = get_session_store()
    store.set("s-1", {"prescription_items": [], "pending_clarification": None})

    client = TestClient(create_app())
    r = client.post("/chat", json={"raw_text": "hi", "session_id": "s-1"})
    assert r.status_code == 409
