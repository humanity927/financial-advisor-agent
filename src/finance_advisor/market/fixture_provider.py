from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from finance_advisor.market.models import MarketBar, MarketProviderName, MarketSeries
from finance_advisor.market.symbols import SymbolInfo
from finance_advisor.schemas import now_iso


class FixtureProvider:
    """Generate deterministic synthetic history from a committed fixture spec."""

    name: MarketProviderName = "fixture"

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def available(self) -> bool:
        return self.fixture_path.is_file()

    def fetch_history(self, symbol: SymbolInfo, lookback_days: int) -> MarketSeries:
        if not self.available():
            raise FileNotFoundError(f"fixture不存在：{self.fixture_path}")

        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if symbol.symbol not in payload["symbols"]:
            raise KeyError(f"fixture中不存在标的：{symbol.symbol}")

        spec = payload["symbols"][symbol.symbol]
        count = max(lookback_days + 1, 261)
        dates = pd.bdate_range(end=payload["as_of"], periods=count)
        price = float(spec["base_price"])
        bars: list[MarketBar] = []
        for index, item_date in enumerate(dates):
            daily_return = (
                float(spec["daily_drift"])
                + float(spec["wave_amplitude"]) * math.sin(index * float(spec["frequency"]))
                + float(spec["wave_amplitude"]) * 0.35 * math.cos(index * 0.23)
            )
            price = max(0.01, price * (1.0 + daily_return))
            bars.append(MarketBar(date=item_date.date(), close=round(price, 4)))

        return MarketSeries(
            symbol=symbol.symbol,
            name=symbol.name,
            asset_class=symbol.asset_class,
            bars=bars[-(lookback_days + 1) :],
            source="fixture",
            provider="fixture",
            fetched_at=now_iso(),
            is_fallback=True,
            warning=f"演示数据/非实时数据，固定数据日期为 {payload['as_of']}",
        )
