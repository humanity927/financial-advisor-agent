from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Annotated, Any, cast

from pydantic import BeforeValidator

from finance_advisor.risk.profile import RISK_LEVELS, assess_profile
from finance_advisor.schemas import InvestorProfileInput, LiquidityNeed

ASSET_CLASSES = ("现金", "债券", "股票", "黄金")


def _validate_percentage_input(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("配置比例必须使用JSON数值，不能使用布尔值或字符串")
    if not isfinite(float(value)):
        raise ValueError("配置比例必须是有限数值")
    return value


AllocationPercentage = Annotated[float, BeforeValidator(_validate_percentage_input)]

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


def _amounts_from_percentages(
    amount_cny: float,
    percentages: Mapping[str, float],
) -> dict[str, float]:
    amounts = {
        asset: round(amount_cny * float(percentages[asset]) / 100.0, 2) for asset in ASSET_CLASSES
    }
    residual = round(amount_cny - sum(amounts.values()), 2)
    amounts["现金"] = round(amounts["现金"] + residual, 2)
    return amounts


def _validate_current_allocation_pct(
    current_allocation_pct: Mapping[str, float],
) -> dict[str, float]:
    unknown_assets = sorted(set(current_allocation_pct) - set(ASSET_CLASSES))
    if unknown_assets:
        raise ValueError(f"当前配置包含不支持的资产类别：{', '.join(unknown_assets)}")

    missing_assets = [asset for asset in ASSET_CLASSES if asset not in current_allocation_pct]
    if missing_assets:
        raise ValueError(f"当前配置缺少资产类别：{', '.join(missing_assets)}")

    current: dict[str, float] = {}
    for asset in ASSET_CLASSES:
        raw_value = _validate_percentage_input(current_allocation_pct[asset])
        value = round(float(raw_value), 1)
        if value < 0 or value > 100:
            raise ValueError("当前配置比例必须在0到100之间")
        current[asset] = value

    total = round(sum(current.values()), 1)
    if total != 100.0:
        raise ValueError(f"当前配置比例合计必须为100.0%，当前为{total}%")
    return current


def _allocation_deviation_pct(
    suggested: Mapping[str, float],
    current: Mapping[str, float],
) -> dict[str, float]:
    deviation = {
        asset: round(float(suggested[asset]) - float(current[asset]), 1) for asset in ASSET_CLASSES
    }
    residual = round(0.0 - sum(deviation.values()), 1)
    deviation["现金"] = round(deviation["现金"] + residual, 1)
    return deviation


def _allocation_deviation_amount_cny(
    suggested: Mapping[str, float],
    current: Mapping[str, float],
) -> dict[str, float]:
    deviation = {
        asset: round(float(suggested[asset]) - float(current[asset]), 2) for asset in ASSET_CLASSES
    }
    residual = round(0.0 - sum(deviation.values()), 2)
    deviation["现金"] = round(deviation["现金"] + residual, 2)
    return deviation


def _adjustment_steps(
    *,
    scored_risk_level: str,
    effective_risk_level: str,
    constraints: list[str],
    has_current_allocation: bool,
) -> list[str]:
    steps = [
        f"根据用户画像评分得到基础风险等级：{scored_risk_level}",
    ]
    if effective_risk_level != scored_risk_level:
        steps.append(f"受硬约束影响，将有效风险等级调整为：{effective_risk_level}")
    else:
        steps.append(f"未触发风险等级下调，沿用有效风险等级：{effective_risk_level}")

    steps.append(f"载入{effective_risk_level}对应的四类资产基础配置模板")
    steps.extend(f"应用硬约束：{constraint}" for constraint in constraints)
    steps.append("在基础模板上按硬约束调整，并将最终比例归一化到100%")
    if has_current_allocation:
        steps.append("将建议比例与当前比例逐项比较，生成配置偏离")
    return steps


def _rationale(
    *,
    effective_risk_level: str,
    constraints: list[str],
    allocation_pct: Mapping[str, float],
) -> list[str]:
    reasons = [
        f"有效风险等级为{effective_risk_level}，因此使用对应的基础配置模板",
        "配置仅覆盖现金、债券、股票、黄金四类资产，不生成交易指令",
    ]
    if constraints:
        reasons.append("已优先满足最大亏损、投资期限、流动性和应急资金等硬约束")
    if allocation_pct["现金"] >= 30:
        reasons.append("现金比例较高，用于覆盖短期流动性和应急资金需求")
    if allocation_pct["股票"] <= 10:
        reasons.append("股票比例受到期限或最大亏损约束控制，避免过度承担波动")
    reasons.append("所有比例和金额来自确定性规则，模型只负责解释，不改写配置结果")
    return reasons


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
    amounts = _amounts_from_percentages(profile.amount_cny, percentages)

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


def build_portfolio_plan(
    profile: InvestorProfileInput,
    current_allocation_pct: Mapping[str, float] | None = None,
) -> dict[str, object]:
    allocation = build_portfolio_allocation(profile)
    suggested_pct = cast(dict[str, float], allocation["allocation_pct"])
    constraints = cast(list[str], allocation["constraints_applied"])
    current_pct = (
        _validate_current_allocation_pct(current_allocation_pct)
        if current_allocation_pct is not None
        else None
    )
    current_amounts = (
        _amounts_from_percentages(profile.amount_cny, current_pct)
        if current_pct is not None
        else None
    )
    suggested_amounts = cast(dict[str, float], allocation["allocation_amount_cny"])

    plan = dict(allocation)
    plan["adjustment_steps"] = _adjustment_steps(
        scored_risk_level=cast(str, allocation["scored_risk_level"]),
        effective_risk_level=cast(str, allocation["effective_risk_level"]),
        constraints=constraints,
        has_current_allocation=current_pct is not None,
    )
    plan["rationale"] = _rationale(
        effective_risk_level=cast(str, allocation["effective_risk_level"]),
        constraints=constraints,
        allocation_pct=suggested_pct,
    )
    plan["current_allocation_pct"] = current_pct
    plan["current_allocation_amount_cny"] = current_amounts
    plan["allocation_deviation_pct"] = (
        _allocation_deviation_pct(suggested_pct, current_pct) if current_pct is not None else None
    )
    plan["allocation_deviation_amount_cny"] = (
        _allocation_deviation_amount_cny(suggested_amounts, current_amounts)
        if current_amounts is not None
        else None
    )
    return plan
