from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from finance_advisor.market.models import MarketSeries
from finance_advisor.schemas import CHINA_TIMEZONE, now_iso


class CacheProvider:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_key(key: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]", "_", key)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{self._safe_key(key)}.json"

    def save(self, key: str, series: MarketSeries) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        payload = {
            "cached_at": now_iso(),
            "series": series.model_dump(mode="json"),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def load(
        self,
        key: str,
        *,
        max_age_seconds: int,
        allow_stale: bool = False,
    ) -> MarketSeries | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(payload["cached_at"])
            age_seconds = (datetime.now(CHINA_TIMEZONE) - cached_at).total_seconds()
            if age_seconds > max_age_seconds and not allow_stale:
                return None
            original = MarketSeries.model_validate(payload["series"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

        # Normal runtime cache may only contain data originally fetched from AKShare.
        if original.source != "akshare" and original.origin_source != "akshare":
            return None

        stale = age_seconds > max_age_seconds
        warning = "AKShare暂不可用，使用已过期的真实行情缓存" if stale else "使用真实行情缓存"
        return original.model_copy(
            update={
                "source": "cache",
                "origin_source": "akshare",
                "is_fallback": True,
                "warning": warning,
                "cached_at": cached_at.isoformat(timespec="seconds"),
                "cache_age_seconds": max(0, int(age_seconds)),
                "is_stale": stale,
            }
        )
