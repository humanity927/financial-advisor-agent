from __future__ import annotations

import pytest

from finance_advisor.allocation.service import build_portfolio_allocation, build_portfolio_plan
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


def test_portfolio_plan_calculates_deviation_without_changing_suggestion() -> None:
    result = build_portfolio_plan(
        _aggressive_profile(),
        {"现金": 20.0, "债券": 40.0, "股票": 30.0, "黄金": 10.0},
    )

    assert result["allocation_pct"] == {"现金": 5.0, "债券": 15.0, "股票": 70.0, "黄金": 10.0}
    assert result["current_allocation_pct"] == {
        "现金": 20.0,
        "债券": 40.0,
        "股票": 30.0,
        "黄金": 10.0,
    }
    assert result["allocation_deviation_pct"] == {
        "现金": -15.0,
        "债券": -25.0,
        "股票": 40.0,
        "黄金": 0.0,
    }
    assert result["current_allocation_amount_cny"] == {
        "现金": 10_000.0,
        "债券": 20_000.0,
        "股票": 15_000.0,
        "黄金": 5_000.0,
    }
    assert result["allocation_deviation_amount_cny"] == {
        "现金": -7_500.0,
        "债券": -12_500.0,
        "股票": 20_000.0,
        "黄金": 0.0,
    }
    assert sum(result["allocation_deviation_pct"].values()) == 0.0  # type: ignore[union-attr]
    assert sum(result["allocation_deviation_amount_cny"].values()) == 0.0  # type: ignore[union-attr]
    assert result["adjustment_steps"][-1] == "将建议比例与当前比例逐项比较，生成配置偏离"
    assert result["rationale"]


def test_portfolio_plan_allows_missing_current_allocation() -> None:
    result = build_portfolio_plan(_aggressive_profile(max_loss_pct=5))

    assert result["current_allocation_pct"] is None
    assert result["current_allocation_amount_cny"] is None
    assert result["allocation_deviation_pct"] is None
    assert result["allocation_deviation_amount_cny"] is None
    assert result["effective_risk_level"] == "保守型"
    assert "应用硬约束：最大可承受亏损不超过5%，风险等级上限为保守型" in result["adjustment_steps"]  # type: ignore[operator]


def test_portfolio_plan_rejects_invalid_current_allocation_total() -> None:
    with pytest.raises(ValueError, match="合计必须为100.0%"):
        build_portfolio_plan(
            _aggressive_profile(),
            {"现金": 20.0, "债券": 40.0, "股票": 20.0, "黄金": 10.0},
        )


@pytest.mark.parametrize("invalid_value", [True, "25", float("nan"), float("inf")])
def test_portfolio_plan_rejects_non_numeric_or_non_finite_allocation(
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError, match="配置比例必须"):
        build_portfolio_plan(
            _aggressive_profile(),
            {
                "现金": invalid_value,  # type: ignore[dict-item]
                "债券": 40.0,
                "股票": 40.0,
                "黄金": 20.0,
            },
        )
