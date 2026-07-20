from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    symbol: str
    name: str
    asset_class: str


SUPPORTED_SYMBOLS: dict[str, SymbolInfo] = {
    "510300": SymbolInfo("510300", "沪深300ETF", "股票"),
    "511010": SymbolInfo("511010", "国债ETF", "债券"),
    "518880": SymbolInfo("518880", "黄金ETF", "黄金"),
    "511880": SymbolInfo("511880", "货币ETF", "现金"),
}

SYMBOL_ALIASES: dict[str, str] = {
    "沪深300": "510300",
    "沪深300ETF": "510300",
    "国债": "511010",
    "国债ETF": "511010",
    "黄金": "518880",
    "黄金ETF": "518880",
    "货币": "511880",
    "货币ETF": "511880",
}


class SymbolValidationError(ValueError):
    """Raised when a tool receives unsupported or excessive symbols."""


def normalize_symbol(value: str) -> SymbolInfo:
    normalized = value.strip()
    symbol = SYMBOL_ALIASES.get(normalized, normalized)
    if symbol not in SUPPORTED_SYMBOLS:
        allowed = "、".join(f"{item.symbol}({item.name})" for item in SUPPORTED_SYMBOLS.values())
        raise SymbolValidationError(f"不支持标的 {value!r}；可选标的：{allowed}")
    return SUPPORTED_SYMBOLS[symbol]


def normalize_symbols(values: list[str]) -> list[SymbolInfo]:
    if not values:
        raise SymbolValidationError("symbols 至少需要一个标的")
    if len(values) > 4:
        raise SymbolValidationError("一次最多查询4个标的")

    result: list[SymbolInfo] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_symbol(value)
        if item.symbol not in seen:
            result.append(item)
            seen.add(item.symbol)
    return result
