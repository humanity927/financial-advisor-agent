from __future__ import annotations

from finance_advisor.allocation.service import build_portfolio_allocation
from finance_advisor.schemas import InvestorProfileInput


def _aggressive_profile(**overrides: object) -> InvestorProfileInput:
    values: dict[str, object] = {
        "amount_cny": 50_000,
        "horizon_months": 60,
        "max_loss_pct": 30,
        "income_stability": "very_stable",
        "experience": "expert",
        "liquidity_need": "low",
        "emergency_fund_months": 12,
    }
    values.update(overrides)
    return InvestorProfileInput.model_validate(values)


def test_base_aggressive_allocation_and_amounts_sum() -> None:
    result = build_portfolio_allocation(_aggressive_profile())

    assert result["effective_risk_level"] == "进取型"
    assert result["allocation_pct"] == {"现金": 5.0, "债券": 15.0, "股票": 70.0, "黄金": 10.0}
    assert sum(result["allocation_pct"].values()) == 100.0  # type: ignore[union-attr]
    assert sum(result["allocation_amount_cny"].values()) == 50_000  # type: ignore[union-attr]


def test_max_loss_hard_cap_forces_conservative() -> None:
    result = build_portfolio_allocation(_aggressive_profile(max_loss_pct=5))

    assert result["scored_risk_level"] != "保守型"
    assert result["effective_risk_level"] == "保守型"
    assert result["allocation_pct"] == {"现金": 40.0, "债券": 45.0, "股票": 5.0, "黄金": 10.0}


def test_short_horizon_caps_equity_and_splits_removed_weight() -> None:
    result = build_portfolio_allocation(_aggressive_profile(horizon_months=3))

    assert result["effective_risk_level"] == "进取型"
    assert result["allocation_pct"] == {"现金": 35.0, "债券": 45.0, "股票": 10.0, "黄金": 10.0}


def test_emergency_fund_sets_cash_floor_without_reducing_gold() -> None:
    result = build_portfolio_allocation(_aggressive_profile(emergency_fund_months=1))

    percentages = result["allocation_pct"]
    assert percentages == {"现金": 40.0, "债券": 15.0, "股票": 35.0, "黄金": 10.0}
    assert sum(percentages.values()) == 100.0  # type: ignore[union-attr]


def test_amount_rounding_residual_goes_to_cash() -> None:
    result = build_portfolio_allocation(_aggressive_profile(amount_cny=100.01))
    amounts = result["allocation_amount_cny"]
    assert sum(amounts.values()) == 100.01  # type: ignore[union-attr]
