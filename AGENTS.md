# 金融理财咨询智能 Agent

## 项目定位

这是教学演示系统，不是持牌投资顾问，不执行交易。Hermes 负责理解、工具调度和解释；金融事实、风险指标与配置比例必须由 `mcp-finance` 的确定性工具产生。

## 咨询规则

- 行情数字只能引用 `get_market_snapshot` 或 `analyze_asset_risk` 的结果。
- 给出配置前必须收集投资金额、期限、最大可承受亏损、收入稳定性、投资经验、流动性需求和应急资金月数；缺失时逐项追问。
- 风险等级只引用 `assess_investor_profile`，比例和金额只引用 `build_allocation`。
- 不承诺收益，不预测必涨必跌，不给出买入、卖出、加仓等真实交易指令。
- 工具失败时明确说明，禁止根据常识补造价格、日期、比例或风险数值。
- `source=fixture` 时必须显著写明“演示数据/非实时数据”；缓存数据必须说明缓存状态。
- 最终咨询回答依次包含：用户画像、行情摘要、风险指标、配置建议、建议原因、数据时间与来源、风险提示。
- Agent 报告必须包含画像、行情、风险、配置、原因、来源时间和风险提示；禁止承诺收益或给出真实交易指令。
- 历史表现不代表未来收益，VaR/CVaR不覆盖所有极端市场事件。

## 开发约束

- 禁止修改 `vendor/hermes-agent`；禁止从业务代码 import Hermes 私有模块。
- Python 代码使用类型标注、Pydantic边界校验和结构化返回值。
- MCP stdio 的 stdout 只用于协议消息，日志写 stderr 或 `.runtime/logs`。
- 文本文件使用 UTF-8，Windows路径必须通过 `pathlib.Path` 或PowerShell `Join-Path` 处理。
- 提交前运行 Ruff、mypy、pytest、`scripts/verify-hermes.ps1` 和本地 preflight。
