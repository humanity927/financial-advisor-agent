from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from finance_advisor.schemas import now_iso

SYMBOL_PATTERN = re.compile(r"^\d{6}$")
VALID_MARKETS = {"SH", "SZ"}
VALID_ASSET_TYPES = {"etf", "index"}


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    symbol: str
    name: str
    asset_class: str
    market: str = "SH"
    asset_type: str = "etf"
    provider_symbol: str | None = None


# These entries are metadata only. Prices and history never come from this table.
BUILTIN_SYMBOLS: dict[str, SymbolInfo] = {
    "510300": SymbolInfo("510300", "沪深300ETF", "股票", "SH", "etf"),
    "511010": SymbolInfo("511010", "国债ETF", "债券", "SH", "etf"),
    "518880": SymbolInfo("518880", "黄金ETF", "黄金", "SH", "etf"),
    "511880": SymbolInfo("511880", "货币ETF", "现金", "SH", "etf"),
    "000001": SymbolInfo("000001", "上证指数", "股票", "SH", "index", "sh000001"),
    "000300": SymbolInfo("000300", "沪深300指数", "股票", "SH", "index", "sh000300"),
    "000905": SymbolInfo("000905", "中证500指数", "股票", "SH", "index", "sh000905"),
    "000852": SymbolInfo("000852", "中证1000指数", "股票", "SH", "index", "sh000852"),
    "399001": SymbolInfo("399001", "深证成指", "股票", "SZ", "index", "sz399001"),
    "399006": SymbolInfo("399006", "创业板指", "股票", "SZ", "index", "sz399006"),
}

# Kept as a public compatibility alias. Runtime validation uses SymbolCatalog.
SUPPORTED_SYMBOLS = BUILTIN_SYMBOLS

SYMBOL_ALIASES: dict[str, str] = {
    "沪深300": "510300",
    "沪深300ETF": "510300",
    "国债": "511010",
    "国债ETF": "511010",
    "黄金": "518880",
    "黄金ETF": "518880",
    "货币": "511880",
    "货币ETF": "511880",
    **{item.name: item.symbol for item in BUILTIN_SYMBOLS.values()},
}


class SymbolValidationError(ValueError):
    """Raised when an instrument does not pass catalog validation."""


def validate_symbol_info(item: SymbolInfo) -> SymbolInfo:
    if not SYMBOL_PATTERN.fullmatch(item.symbol):
        raise SymbolValidationError("标的代码必须为6位数字")
    name = item.name.strip()
    if not name or len(name) > 80:
        raise SymbolValidationError("标的名称不能为空且不能超过80个字符")
    if item.market not in VALID_MARKETS:
        raise SymbolValidationError("市场必须为SH或SZ")
    if item.asset_type not in VALID_ASSET_TYPES:
        raise SymbolValidationError("资产类型只支持ETF或A股指数")
    if not item.asset_class.strip() or len(item.asset_class) > 20:
        raise SymbolValidationError("资产类别无效")
    return item


def catalog_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    return Path(
        os.getenv(
            "FINANCE_CATALOG_PATH",
            project_root / ".runtime" / "market-catalog.json",
        )
    ).resolve()


class SymbolCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or catalog_path()).resolve()
        self._items = dict(BUILTIN_SYMBOLS)
        self.fetched_at: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("source") != "akshare":
                return
            loaded = [SymbolInfo(**raw) for raw in payload.get("items", [])]
            for item in loaded:
                valid = validate_symbol_info(item)
                self._items[valid.symbol] = valid
            self.fetched_at = str(payload.get("fetched_at") or "") or None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return

    def all(self) -> list[SymbolInfo]:
        return sorted(self._items.values(), key=lambda item: (item.asset_type, item.symbol))

    def get(self, symbol: str) -> SymbolInfo | None:
        return self._items.get(symbol)

    def search(self, query: str, *, limit: int = 30) -> list[SymbolInfo]:
        needle = query.strip().lower()
        values = self.all()
        if needle:
            values = [
                item
                for item in values
                if needle in item.symbol.lower() or needle in item.name.lower()
            ]
        return values[:limit]

    def register_akshare(self, items: list[SymbolInfo]) -> None:
        for item in items:
            valid = validate_symbol_info(item)
            self._items[valid.symbol] = valid
        self.fetched_at = now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {
            "source": "akshare",
            "fetched_at": self.fetched_at,
            "items": [asdict(item) for item in self.all()],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


_catalog: SymbolCatalog | None = None


def get_symbol_catalog() -> SymbolCatalog:
    global _catalog
    expected_path = catalog_path()
    if _catalog is None or _catalog.path != expected_path:
        _catalog = SymbolCatalog(expected_path)
    return _catalog


def reset_symbol_catalog_for_tests() -> None:
    global _catalog
    _catalog = None


def normalize_symbol(value: str) -> SymbolInfo:
    normalized = value.strip()
    symbol = SYMBOL_ALIASES.get(normalized, normalized)
    item = get_symbol_catalog().get(symbol)
    if item is None:
        raise SymbolValidationError(f"不支持标的 {value!r}；请先在行情中心搜索并添加A股指数或ETF")
    return item


def normalize_symbols(values: list[str]) -> list[SymbolInfo]:
    if not values:
        raise SymbolValidationError("symbols 至少需要一个标的")
    if len(values) > 8:
        raise SymbolValidationError("一次最多查询8个标的")

    result: list[SymbolInfo] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_symbol(value)
        if item.symbol not in seen:
            result.append(item)
            seen.add(item.symbol)
    return result
