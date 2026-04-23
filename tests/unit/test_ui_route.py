"""Smoke tests for the static test-UI page."""

from __future__ import annotations

from starlette.testclient import TestClient

from sales_agent.api.main import create_app


def test_ui_page_served() -> None:
    client = TestClient(create_app())
    r = client.get("/ui")
    assert r.status_code == 200
    body = r.text
    assert "Pharmacy Sales Agent" in body
    assert "/prescriptions/check" in body
    assert "/symptoms/advise" in body
    assert "<textarea id=\"rx-request\"" in body
    assert "<textarea id=\"sym-request\"" in body


def test_ui_has_chat_tab() -> None:
    """Chat NLU tab with raw_text input, patient overrides, and render logic."""
    client = TestClient(create_app())
    body = client.get("/ui").text
    assert "/chat" in body
    assert 'id="chat-raw"' in body
    assert 'id="chat-age"' in body
    assert 'id="chat-preg"' in body
    assert 'id="chat-allergies"' in body
    assert 'id="chat-submit"' in body
    assert "submitChat" in body
    assert "renderChat" in body
    assert "parsed-box" in body


def test_root_redirects_to_ui() -> None:
    client = TestClient(create_app())
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)
    assert r.headers["location"] == "/ui"
