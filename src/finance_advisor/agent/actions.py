from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finance_advisor.allocation.service import ASSET_CLASSES, AllocationPercentage
from finance_advisor.market.symbols import SymbolCatalog
from finance_advisor.schemas import (
    IncomeStability,
    InvestmentExperience,
    LiquidityNeed,
)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_cny: float | None = Field(default=None, gt=0, le=1_000_000_000)
    horizon_months: int | None = Field(default=None, ge=1, le=600)
    max_loss_pct: float | None = Field(default=None, ge=0, le=100)
    income_stability: IncomeStability | None = None
    experience: InvestmentExperience | None = None
    liquidity_need: LiquidityNeed | None = None
    emergency_fund_months: int | None = Field(default=None, ge=0, le=120)

    def present(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)

    def missing_fields(self) -> list[str]:
        return [name for name, value in self.model_dump().items() if value is None]


class ProfilePatchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["profile.patch"]
    payload: ProfilePatch


class SymbolActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^\d{6}$")


class MarketSymbolAddAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["market.symbol.add"]
    payload: SymbolActionPayload


class MarketSymbolRemoveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["market.symbol.remove"]
    payload: SymbolActionPayload


class RiskSymbolSelectAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["risk.symbol.select"]
    payload: SymbolActionPayload


class PortfolioInputsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProfilePatch | None = None
    current_allocation_pct: dict[str, AllocationPercentage] | None = None

    @field_validator("current_allocation_pct")
    @classmethod
    def validate_current_allocation(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None

        unknown = sorted(set(value) - set(ASSET_CLASSES))
        if unknown:
            raise ValueError(f"当前配置包含不支持的资产类别：{', '.join(unknown)}")
        missing = [asset for asset in ASSET_CLASSES if asset not in value]
        if missing:
            raise ValueError(f"当前配置缺少资产类别：{', '.join(missing)}")

        normalized = {asset: round(float(value[asset]), 1) for asset in ASSET_CLASSES}
        if any(percentage < 0 or percentage > 100 for percentage in normalized.values()):
            raise ValueError("当前配置比例必须在0到100之间")
        total = round(sum(normalized.values()), 1)
        if total != 100.0:
            raise ValueError(f"当前配置比例合计必须为100.0%，当前为{total}%")
        return normalized


class PortfolioInputsPatchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["portfolio.inputs.patch"]
    payload: PortfolioInputsPatch


UiAction = Annotated[
    ProfilePatchAction
    | MarketSymbolAddAction
    | MarketSymbolRemoveAction
    | RiskSymbolSelectAction
    | PortfolioInputsPatchAction,
    Field(discriminator="type"),
]


def _number(match: re.Match[str] | None) -> float | None:
    return float(match.group(1)) if match else None


def extract_profile_patch(text: str) -> ProfilePatch:
    amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(万元|万|元)", text)
    amount = _number(amount_match)
    if amount is not None and amount_match and amount_match.group(2) in {"万", "万元"}:
        amount *= 10_000

    emergency_match = re.search(r"(?:应急|备用金)[^\d]{0,12}(\d+)\s*(?:个)?月", text)
    horizon_match = re.search(r"(?:投资期限|期限|持有|计划投资)[^\d]{0,12}(\d+)\s*(年|个?月)", text)
    if horizon_match is None:
        horizon_match = re.search(r"(\d+)\s*年", text)
    horizon = int(horizon_match.group(1)) if horizon_match else None
    if horizon is not None and horizon_match and horizon_match.group(2) == "年":
        horizon *= 12

    loss_match = re.search(
        r"(?:最大(?:可承受)?亏损|承受亏损|最大回撤|亏损上限)[^\d]{0,12}(\d+(?:\.\d+)?)\s*%?",
        text,
    )

    income: IncomeStability | None = None
    if re.search(r"(?:收入|工作).{0,8}(?:不稳定|波动|不固定)", text):
        income = IncomeStability.UNSTABLE
    elif re.search(r"(?:收入|工作).{0,8}(?:非常稳定|很稳定|稳定)", text):
        income = (
            IncomeStability.VERY_STABLE
            if "非常稳定" in text or "很稳定" in text
            else IncomeStability.STABLE
        )

    experience: InvestmentExperience | None = None
    if re.search(r"(?:没有|无|零).{0,4}(?:投资)?经验|投资小白", text):
        experience = InvestmentExperience.NONE
    elif re.search(r"(?:专业|资深|十多年).{0,4}(?:投资)?经验", text):
        experience = InvestmentExperience.EXPERT
    elif re.search(r"(?:经常|定期|多年).{0,4}(?:投资|定投)|经验丰富", text):
        experience = InvestmentExperience.REGULAR
    elif re.search(r"(?:基础|一些|少量|初步).{0,4}(?:投资)?经验|买过基金", text):
        experience = InvestmentExperience.BASIC

    liquidity: LiquidityNeed | None = None
    if re.search(r"(?:流动性|用钱|资金).{0,8}(?:高|随时|很快|近期)", text):
        liquidity = LiquidityNeed.HIGH
    elif re.search(r"(?:流动性|用钱|资金).{0,8}(?:低|不急|长期)", text):
        liquidity = LiquidityNeed.LOW
    elif re.search(r"(?:流动性|用钱|资金).{0,8}(?:中等|一般|适中)", text):
        liquidity = LiquidityNeed.MEDIUM

    return ProfilePatch(
        amount_cny=amount,
        horizon_months=horizon,
        max_loss_pct=_number(loss_match),
        income_stability=income,
        experience=experience,
        liquidity_need=liquidity,
        emergency_fund_months=int(emergency_match.group(1)) if emergency_match else None,
    )


def extract_symbols(text: str, catalog: SymbolCatalog) -> list[str]:
    found: list[str] = []
    for symbol in re.findall(r"(?<!\d)(\d{6})(?!\d)", text):
        if catalog.get(symbol) is not None and symbol not in found:
            found.append(symbol)
    for item in catalog.all():
        if item.name in text and item.symbol not in found:
            found.append(item.symbol)
    return found[:8]
