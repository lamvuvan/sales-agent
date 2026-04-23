"""Unit tests for check_inventory node (brand-first matching)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from sales_agent.graph import nodes_prescription


@contextmanager
def _fake_session():
    yield object()


def _item(drug_name: str = "Panadol 500mg") -> dict:
    return {
        "drug_name": drug_name,
        "active_ingredient": "paracetamol",
        "strength": "500mg",
        "dosage_form": "viên nén",
        "quantity": 20,
        "dosage_instruction": "1 viên x 3 lần/ngày",
    }


def _stock(status: str, **overrides) -> dict:
    base = {
        "status": status,
        "product_id": "p-001",
        "sku": "SKU-001",
        "name_vi": "Panadol 500mg",
        "qty_on_hand": 0 if status == "out_of_stock" else 100,
        "rx_only": False,
    }
    if status == "not_carried":
        base.update(product_id=None, sku=None, name_vi=None, qty_on_hand=0)
    base.update(overrides)
    return base


def test_brand_out_of_stock_reports_out_of_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Panadol 500mg qty=0 in catalog -> status=out_of_stock, matched_product=Panadol."""
    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock_by_name",
        lambda sess, name: _stock("out_of_stock"),
    )
    # Must not be called when brand is found in catalog.
    called = {"inn_lookup": 0}

    def _should_not_be_called(*a, **k):
        called["inn_lookup"] += 1
        return _stock("in_stock", name_vi="Hapacol 500", qty_on_hand=80)

    monkeypatch.setattr(nodes_prescription, "check_stock", _should_not_be_called)

    state = {"prescription_items": [_item("Panadol 500mg")]}
    out = nodes_prescription.check_inventory(state)
    r = out["inventory_results"][0]
    assert r["status"] == "out_of_stock"
    assert r["qty_on_hand"] == 0
    assert r["matched_product"]["name_vi"] == "Panadol 500mg"
    assert called["inn_lookup"] == 0  # brand-name lookup was enough


def test_brand_in_stock_reports_in_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock_by_name",
        lambda sess, name: _stock("in_stock", qty_on_hand=120),
    )
    monkeypatch.setattr(nodes_prescription, "check_stock", lambda *a, **k: _stock("not_carried"))

    state = {"prescription_items": [_item("Panadol 500mg")]}
    out = nodes_prescription.check_inventory(state)
    r = out["inventory_results"][0]
    assert r["status"] == "in_stock"
    assert r["qty_on_hand"] == 120


def test_unknown_brand_falls_back_and_stays_not_carried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brand not in catalog, but a generic INN match has stock -> report not_carried
    so the substitute flow still runs (Panadol XYZ brand doesn't exist; Hapacol does).

    The prescribed brand's row must report qty_on_hand=0 — the matched SKU's
    stock count belongs on the substitute row, not on the 'not_carried' line.
    """
    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock_by_name",
        lambda sess, name: _stock("not_carried"),
    )
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock",
        lambda *a, **k: _stock("in_stock", name_vi="Hapacol 500", sku="SKU-002", qty_on_hand=80),
    )

    state = {"prescription_items": [_item("Panadol XYZ 500mg")]}
    out = nodes_prescription.check_inventory(state)
    r = out["inventory_results"][0]
    assert r["status"] == "not_carried"
    # qty_on_hand reset to 0 so the UI doesn't misreport the equivalent SKU's stock.
    assert r["qty_on_hand"] == 0
    # matched_product kept for downstream (substitute lookup, contraindication check).
    assert r["matched_product"]["name_vi"] == "Hapacol 500"
    assert r["matched_product"]["sku"] == "SKU-002"


def test_unknown_brand_no_generic_is_not_carried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nodes_prescription, "session_scope", _fake_session)
    monkeypatch.setattr(
        nodes_prescription,
        "check_stock_by_name",
        lambda sess, name: _stock("not_carried"),
    )
    monkeypatch.setattr(
        nodes_prescription, "check_stock", lambda *a, **k: _stock("not_carried")
    )

    state = {"prescription_items": [_item("Cefixime 200mg")]}
    out = nodes_prescription.check_inventory(state)
    r = out["inventory_results"][0]
    assert r["status"] == "not_carried"
    assert r["matched_product"] is None
