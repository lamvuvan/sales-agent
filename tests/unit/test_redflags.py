"""Unit tests for the red-flag rule set."""

from __future__ import annotations

from sales_agent.tools.redflags import get_redflags


def test_clear_case_no_flags() -> None:
    flags = get_redflags(
        ["sốt nhẹ", "sổ mũi", "đau họng"], age_years=28, pregnancy=False, duration_days=1
    )
    assert flags == []


def test_infant_fever_triggers() -> None:
    flags = get_redflags(["sốt"], age_years=0.15, pregnancy=False)
    assert any("dưới 3 tháng" in f for f in flags)


def test_dyspnea_triggers() -> None:
    flags = get_redflags(["khó thở", "sốt"], age_years=40, pregnancy=False)
    assert any("khó thở" in f for f in flags)


def test_pregnancy_adds_flag() -> None:
    flags = get_redflags(["sổ mũi"], age_years=30, pregnancy=True)
    assert any("có thai" in f for f in flags)


def test_long_fever_triggers() -> None:
    flags = get_redflags(["sốt"], age_years=30, pregnancy=False, duration_days=5)
    assert any("kéo dài" in f for f in flags)


def test_neuro_symptoms_trigger() -> None:
    flags = get_redflags(["co giật"], age_years=30, pregnancy=False)
    assert any("thần kinh" in f for f in flags)


def test_elderly_severe_respiratory() -> None:
    flags = get_redflags(["khó thở"], age_years=72, pregnancy=False)
    # Already flagged by generic dyspnea rule; verify it's at least present.
    assert any("khó thở" in f for f in flags)
