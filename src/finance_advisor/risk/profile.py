from __future__ import annotations

from finance_advisor.schemas import (
    IncomeStability,
    InvestmentExperience,
    InvestorProfileInput,
    LiquidityNeed,
    RiskAssessment,
)

RISK_LEVELS = ("保守型", "稳健型", "平衡型", "进取型")
PROFILE_DIMENSION_MAX_SCORES = {
    "投资期限": 20,
    "最大可承受亏损": 30,
    "投资经验": 15,
    "收入稳定性": 15,
    "流动性需求": 15,
    "应急资金": 5,
}


def _horizon_score(months: int) -> int:
    if months < 6:
        return 0
    if months <= 12:
        return 8
    if months <= 36:
        return 15
    return 20


def _loss_score(max_loss_pct: float) -> int:
    if max_loss_pct <= 5:
        return 0
    if max_loss_pct <= 10:
        return 10
    if max_loss_pct <= 20:
        return 20
    return 30


def _emergency_score(months: int) -> int:
    if months < 3:
        return 0
    if months < 6:
        return 3
    return 5


def risk_level_for_score(score: int) -> str:
    if score <= 25:
        return "保守型"
    if score <= 50:
        return "稳健型"
    if score <= 75:
        return "平衡型"
    return "进取型"


def assess_profile(profile: InvestorProfileInput) -> RiskAssessment:
    breakdown = {
        "投资期限": _horizon_score(profile.horizon_months),
        "最大可承受亏损": _loss_score(profile.max_loss_pct),
        "投资经验": {
            InvestmentExperience.NONE: 0,
            InvestmentExperience.BASIC: 7,
            InvestmentExperience.REGULAR: 12,
            InvestmentExperience.EXPERT: 15,
        }[profile.experience],
        "收入稳定性": {
            IncomeStability.UNSTABLE: 0,
            IncomeStability.STABLE: 8,
            IncomeStability.VERY_STABLE: 15,
        }[profile.income_stability],
        "流动性需求": {
            LiquidityNeed.HIGH: 0,
            LiquidityNeed.MEDIUM: 8,
            LiquidityNeed.LOW: 15,
        }[profile.liquidity_need],
        "应急资金": _emergency_score(profile.emergency_fund_months),
    }
    score = sum(breakdown.values())
    hard_limits: list[str] = []
    if profile.max_loss_pct <= 5:
        hard_limits.append("最大可承受亏损不超过5%，风险等级上限为保守型")
    if profile.horizon_months < 6:
        hard_limits.append("投资期限不足6个月，股票比例上限为10%")
    if profile.emergency_fund_months < 3:
        hard_limits.append("应急资金不足3个月，现金比例下限为40%")
    if profile.liquidity_need is LiquidityNeed.HIGH:
        hard_limits.append("流动性需求高，现金比例下限为30%")
    return RiskAssessment(
        score=score,
        risk_level=risk_level_for_score(score),
        score_breakdown=breakdown,
        hard_limits=hard_limits,
    )


def profile_chart_data(assessment: RiskAssessment) -> list[dict[str, int | str]]:
    """Return the unchanged profile score as six chart-ready dimensions."""
    return [
        {
            "dimension": dimension,
            "score": assessment.score_breakdown[dimension],
            "max_score": max_score,
        }
        for dimension, max_score in PROFILE_DIMENSION_MAX_SCORES.items()
    ]
