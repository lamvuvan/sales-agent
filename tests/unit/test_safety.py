"""Unit tests for OTC safety guardrails."""

from __future__ import annotations

from sales_agent.tools.safety import (
    BLOCKED_ATC_PREFIXES,
    DISCLAIMER_VI,
    is_blocked_for_otc,
    pediatric_dose_hint,
)


def test_inn_blacklist() -> None:
    assert is_blocked_for_otc("amoxicillin")
    assert is_blocked_for_otc("Codeine")  # case-insensitive
    assert not is_blocked_for_otc("paracetamol")


def test_atc_prefix_block() -> None:
    assert is_blocked_for_otc("some-inn", atc_code="J01CA04")
    assert is_blocked_for_otc("some-inn", atc_code="N02AB03")
    assert not is_blocked_for_otc("some-inn", atc_code="N02BE01")


def test_atc_prefixes_present() -> None:
    # Sanity: known blocked classes are in the list.
    assert "J01" in BLOCKED_ATC_PREFIXES
    assert "N02A" in BLOCKED_ATC_PREFIXES


def test_disclaimer_nonempty() -> None:
    assert "bác sĩ" in DISCLAIMER_VI.lower() or "dược sĩ" in DISCLAIMER_VI.lower()


def test_pediatric_dose_hint_returns_none_if_no_rule() -> None:
    assert pediatric_dose_hint(5, None) is None


def test_pediatric_dose_hint_blocks_adult_rule_for_child() -> None:
    msg = pediatric_dose_hint(3, "người lớn")
    assert msg is not None
    assert "không dùng cho trẻ" in msg.lower()
