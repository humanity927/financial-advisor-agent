from __future__ import annotations

import os
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from finance_advisor.market.symbols import SymbolCatalog
from finance_advisor.schemas import now_iso


class WatchlistState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(default_factory=list, max_length=8)
    current_symbol: str | None = Field(default=None, pattern=r"^\d{6}$")
    comparison_symbols: list[str] = Field(default_factory=list, max_length=8)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def validate_membership(self) -> WatchlistState:
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("关注列表不能包含重复标的")
        if len(self.comparison_symbols) != len(set(self.comparison_symbols)):
            raise ValueError("对比列表不能包含重复标的")
        allowed = set(self.symbols)
        if self.current_symbol is not None and self.current_symbol not in allowed:
            raise ValueError("当前标的必须位于关注列表")
        if not set(self.comparison_symbols).issubset(allowed):
            raise ValueError("对比标的必须位于关注列表")
        return self


class WatchlistError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def watchlist_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    return Path(
        os.getenv(
            "FINANCE_WATCHLIST_PATH",
            project_root / ".runtime" / "watchlist.json",
        )
    ).resolve()


class WatchlistStore:
    def __init__(self, catalog: SymbolCatalog, path: Path | None = None) -> None:
        self.catalog = catalog
        self.path = (path or watchlist_path()).resolve()
        self._lock = threading.RLock()

    def _empty(self) -> WatchlistState:
        return WatchlistState()

    def _load(self) -> WatchlistState:
        if not self.path.is_file():
            return self._empty()
        try:
            state = WatchlistState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._empty()

        symbols = [symbol for symbol in state.symbols if self.catalog.get(symbol) is not None]
        current = (
            state.current_symbol
            if state.current_symbol in symbols
            else (symbols[0] if symbols else None)
        )
        comparison = [symbol for symbol in state.comparison_symbols if symbol in symbols]
        return WatchlistState(
            symbols=symbols,
            current_symbol=current,
            comparison_symbols=comparison,
            updated_at=state.updated_at,
        )

    def _save(self, state: WatchlistState) -> WatchlistState:
        saved = state.model_copy(update={"updated_at": now_iso()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(saved.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return saved

    def get(self) -> WatchlistState:
        with self._lock:
            return self._load()

    def add(self, symbol: str) -> WatchlistState:
        with self._lock:
            if self.catalog.get(symbol) is None:
                raise WatchlistError("invalid_symbol", "标的未通过后端目录校验")
            state = self._load()
            if symbol in state.symbols:
                raise WatchlistError("duplicate_symbol", "标的已在关注列表")
            if len(state.symbols) >= 8:
                raise WatchlistError("watchlist_limit", "关注列表最多保留8个标的")
            symbols = [*state.symbols, symbol]
            comparison = [*state.comparison_symbols, symbol]
            return self._save(
                WatchlistState(
                    symbols=symbols,
                    current_symbol=state.current_symbol or symbol,
                    comparison_symbols=comparison,
                )
            )

    def remove(self, symbol: str) -> WatchlistState:
        with self._lock:
            state = self._load()
            if symbol not in state.symbols:
                raise WatchlistError("symbol_not_watched", "标的不在关注列表")
            symbols = [item for item in state.symbols if item != symbol]
            current = state.current_symbol
            if current == symbol:
                current = symbols[0] if symbols else None
            comparison = [item for item in state.comparison_symbols if item != symbol]
            return self._save(
                WatchlistState(
                    symbols=symbols,
                    current_symbol=current,
                    comparison_symbols=comparison,
                )
            )

    def set_current(self, symbol: str) -> WatchlistState:
        with self._lock:
            state = self._load()
            if symbol not in state.symbols:
                raise WatchlistError("symbol_not_watched", "当前标的必须先加入关注列表")
            return self._save(state.model_copy(update={"current_symbol": symbol}))

    def set_comparison(self, symbols: list[str]) -> WatchlistState:
        with self._lock:
            state = self._load()
            unique = list(dict.fromkeys(symbols))
            if len(unique) != len(symbols):
                raise WatchlistError("duplicate_symbol", "对比列表不能包含重复标的")
            if not set(unique).issubset(state.symbols):
                raise WatchlistError("symbol_not_watched", "对比标的必须先加入关注列表")
            return self._save(state.model_copy(update={"comparison_symbols": unique}))


_store: WatchlistStore | None = None


def get_watchlist_store(catalog: SymbolCatalog) -> WatchlistStore:
    global _store
    expected = watchlist_path()
    if _store is None or _store.path != expected or _store.catalog.path != catalog.path:
        _store = WatchlistStore(catalog, expected)
    return _store


def reset_watchlist_store_for_tests() -> None:
    global _store
    _store = None
