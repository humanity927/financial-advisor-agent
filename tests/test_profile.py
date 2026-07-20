from __future__ import annotations

import pytest

from finance_advisor.risk.profile import assess_profile, risk_level_for_score
from finance_advisor.schemas import InvestorProfileInput


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "保守型"),
        (25, "保守型"),
        (26, "稳健型"),
        (50, "稳健型"),
        (51, "平衡型"),
        (75, "平衡型"),
        (76, "进取型"),
        (100, "进取型"),
    ],
)
def test_risk_level_boundaries(score: int, expected: str) -> None:
    assert risk_level_for_score(score) == expected


def test_stable_profile_score_and_limits() -> None:
    profile = InvestorProfileInput(
        amount_cny=50_000,
        horizon_months=12,
        max_loss_pct=10,
        income_stability="stable",
        experience="basic",
        liquidity_need="medium",
        emergency_fund_months=6,
    )

    result = assess_profile(profile)

    assert result.score == 46
    assert result.risk_level == "稳健型"
    assert result.hard_limits == []
    assert sum(result.score_breakdown.values()) == result.score


def test_all_hard_limits_are_reported() -> None:
    profile = InvestorProfileInput(
        amount_cny=10_000,
        horizon_months=3,
        max_loss_pct=5,
        income_stability="unstable",
        experience="none",
        liquidity_need="high",
        emergency_fund_months=1,
    )

    result = assess_profile(profile)

    assert result.risk_level == "保守型"
    assert len(result.hard_limits) == 4


@pytest.mark.parametrize(
    ("months", "expected"),
    [(1, 0), (6, 8), (12, 8), (13, 15), (36, 15), (37, 20)],
)
def test_horizon_score_boundaries(months: int, expected: int) -> None:
    profile = InvestorProfileInput(
        amount_cny=1,
        horizon_months=months,
        max_loss_pct=0,
        income_stability="unstable",
        experience="none",
        liquidity_need="high",
        emergency_fund_months=0,
    )
    assert assess_profile(profile).score_breakdown["投资期限"] == expected
