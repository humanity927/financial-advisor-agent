from __future__ import annotations

from finance_advisor.risk.profile import RISK_LEVELS, assess_profile
from finance_advisor.schemas import InvestorProfileInput, LiquidityNeed

BASE_ALLOCATIONS: dict[str, dict[str, float]] = {
    "保守型": {"现金": 40.0, "债券": 45.0, "股票": 5.0, "黄金": 10.0},
    "稳健型": {"现金": 20.0, "债券": 45.0, "股票": 25.0, "黄金": 10.0},
    "平衡型": {"现金": 10.0, "债券": 30.0, "股票": 50.0, "黄金": 10.0},
    "进取型": {"现金": 5.0, "债券": 15.0, "股票": 70.0, "黄金": 10.0},
}


def _cap_level(level: str, maximum: str) -> str:
    return RISK_LEVELS[min(RISK_LEVELS.index(level), RISK_LEVELS.index(maximum))]


def _apply_equity_cap(allocation: dict[str, float], cap: float) -> None:
    if allocation["股票"] <= cap:
        return
    removed = allocation["股票"] - cap
    allocation["股票"] = cap
    allocation["现金"] += removed / 2.0
    allocation["债券"] += removed / 2.0


def _apply_cash_floor(allocation: dict[str, float], floor: float) -> None:
    needed = max(0.0, floor - allocation["现金"])
    if needed == 0:
        return
    from_equity = min(needed, allocation["股票"])
    allocation["股票"] -= from_equity
    allocation["现金"] += from_equity
    needed -= from_equity
    if needed > 0:
        from_bonds = min(needed, allocation["债券"])
        allocation["债券"] -= from_bonds
        allocation["现金"] += from_bonds


def _rounded_percentages(allocation: dict[str, float]) -> dict[str, float]:
    rounded = {name: round(value, 1) for name, value in allocation.items()}
    rounded["现金"] = round(rounded["现金"] + (100.0 - sum(rounded.values())), 1)
    return rounded


def build_portfolio_allocation(profile: InvestorProfileInput) -> dict[str, object]:
    assessment = assess_profile(profile)
    effective_level = assessment.risk_level
    constraints = list(assessment.hard_limits)

    if profile.max_loss_pct <= 5:
        effective_level = _cap_level(effective_level, "保守型")

    allocation = dict(BASE_ALLOCATIONS[effective_level])
    if profile.horizon_months < 6:
        _apply_equity_cap(allocation, 10.0)

    cash_floor = 0.0
    if profile.emergency_fund_months < 3:
        cash_floor = max(cash_floor, 40.0)
    if profile.liquidity_need is LiquidityNeed.HIGH:
        cash_floor = max(cash_floor, 30.0)
    _apply_cash_floor(allocation, cash_floor)

    percentages = _rounded_percentages(allocation)
    amounts = {
        name: round(profile.amount_cny * percentage / 100.0, 2)
        for name, percentage in percentages.items()
    }
    amount_residual = round(profile.amount_cny - sum(amounts.values()), 2)
    amounts["现金"] = round(amounts["现金"] + amount_residual, 2)

    return {
        "risk_score": assessment.score,
        "scored_risk_level": assessment.risk_level,
        "effective_risk_level": effective_level,
        "score_breakdown": assessment.score_breakdown,
        "constraints_applied": constraints,
        "allocation_pct": percentages,
        "allocation_amount_cny": amounts,
        "total_amount_cny": round(profile.amount_cny, 2),
        "method": "透明规则配置，不依据短期涨跌追涨杀跌",
    }
