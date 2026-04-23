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


def test_root_redirects_to_ui() -> None:
    client = TestClient(create_app())
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)
    assert r.headers["location"] == "/ui"
