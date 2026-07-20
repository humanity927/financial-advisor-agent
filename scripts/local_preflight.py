from __future__ import annotations

from pathlib import Path

from finance_advisor.allocation.service import build_portfolio_allocation
from finance_advisor.market.fixture_provider import FixtureProvider
from finance_advisor.market.symbols import normalize_symbol
from finance_advisor.risk.metrics import calculate_risk_metrics
from finance_advisor.risk.profile import assess_profile
from finance_advisor.schemas import InvestorProfileInput


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture = FixtureProvider(root / "data" / "fixtures" / "market_data.json")
    series = fixture.fetch_history(normalize_symbol("510300"), 252)
    metrics = calculate_risk_metrics(series.bars)
    profile = InvestorProfileInput(
        amount_cny=50_000,
        horizon_months=12,
        max_loss_pct=10,
        income_stability="stable",
        experience="basic",
        liquidity_need="medium",
        emergency_fund_months=6,
    )
    assessment = assess_profile(profile)
    allocation = build_portfolio_allocation(profile)
    assert metrics.observation_count >= 60
    assert assessment.risk_level == "稳健型"
    assert sum(allocation["allocation_pct"].values()) == 100.0  # type: ignore[union-attr]
    print("Local financial core preflight passed with fixture data")


if __name__ == "__main__":
    main()
