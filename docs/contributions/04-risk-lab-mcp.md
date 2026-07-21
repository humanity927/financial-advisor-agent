# 4号最终交接：风险实验室与风险 MCP

> 负责人：4号成员
> 分支：`feat/risk-lab-mcp`
> 最新共同基线：`main@2b8b4a336d72accb1f857cd053f18ebf9b523f43`
> 主分支同步提交：`538c874`
> 本次最终实现提交：`dac868e` (`refactor(risk): unify web and MCP risk workflows`)
> 最后核验：2026-07-21
> 状态：4号风险核心、MCP、HTTP API、Web 页面、fixture 和测试已完成，可以提交 PR 供组长合并。

## 1. 最终交付结论

4号负责的风险部分已经形成完整闭环：

1. 用户可以提交七项画像信息，得到确定性的风险分数、风险等级、六维得分和硬约束。
2. 用户可以选择 1 到 4 个白名单 ETF，查看单资产历史收益、波动、回撤、VaR 和 CVaR。
3. 用户可以设置非负且合计 100% 的组合权重，查看组合指标、相关性、净值和回撤曲线。
4. Hermes 可以通过 finance MCP 调用相同风险能力；FastAPI 和 MCP 不再各自维护一套编排逻辑。
5. 页面明确显示 fixture、缓存、实时来源以及 fallback、partial、empty 和 error 状态。

本模块不预测未来、不执行交易、不生成买卖指令或收益承诺，仅用于课程教学和软件工程演示。

## 2. 最终架构

```text
浏览器 /risk
  -> RiskPage.tsx
  -> client.post('/risk/profile|assets|portfolio')
  -> FastAPI web/routes/risk.py
  -> risk/service.py
     -> MarketService
        -> AKShare -> cache -> fixture
     -> profile.py / metrics.py / portfolio.py
  -> ApiResponse envelope
  -> 画像、指标、曲线、来源和告警

Hermes Agent
  -> finance MCP
  -> mcp_server.py
  -> 同一个 risk/service.py
  -> 同一套确定性计算和来源语义
```

`risk/service.py` 是风险业务的唯一编排层。FastAPI route 只处理 HTTP 状态码和 envelope，MCP server 只处理工具协议和错误码；两者都不复制金融公式。

## 3. 代码范围

### 3.1 风险核心与协议

| 文件 | 作用 |
|---|---|
| `src/finance_advisor/risk/profile.py` | 六维画像得分和图表数据 |
| `src/finance_advisor/risk/metrics.py` | 单资产年化收益、波动、回撤、VaR、CVaR |
| `src/finance_advisor/risk/portfolio.py` | 权重校验、共同日期、组合净值、回撤和 Pearson 相关性 |
| `src/finance_advisor/risk/service.py` | 统一画像、资产、组合风险编排；并发读取历史数据；合并来源和 warning |
| `src/finance_advisor/mcp_server.py` | 暴露 `assess_investor_profile`、`analyze_asset_risk`、`analyze_portfolio_risk` |
| `src/finance_advisor/web/routes/risk.py` | 暴露三个风险 HTTP 端点，复用统一服务 |
| `config/hermes-config.template.yaml` | 将组合风险工具加入 finance 工具白名单 |

### 3.2 风险页面

| 文件 | 作用 |
|---|---|
| `frontend/src/features/risk/RiskPage.tsx` | 画像、资产、组合三个面板及完整状态展示 |
| `frontend/src/features/risk/RiskPage.css` | 风险控件、结果提示、图表和窄屏约束 |
| `frontend/src/features/risk/types.ts` | 与正式 HTTP 响应一致的 TypeScript 类型 |
| `frontend/src/App.tsx` | `/risk` 懒加载接线；与 `/market` 并存 |
| `frontend/src/components/ProfileForm.tsx` | 增加可选提交文案和稳定测试标识，不改变 Advisor 默认行为 |
| `frontend/src/api/keys.ts` | 增加风险资产 Query Key |

### 3.3 Fixture 与测试

| 文件 | 作用 |
|---|---|
| `frontend/mock/risk-profile.json` | 与正式画像 API 一致，包含六维 `dimensions` |
| `frontend/mock/risk-assets.json` | 单资产风险演示响应 |
| `frontend/mock/risk-portfolio.json` | 与正式组合 API 一致，包含指标、相关性、净值和回撤曲线 |
| `frontend/e2e/risk.spec.ts` | 画像、资产、组合、曲线和 1024 宽度检查 |
| `tests/test_portfolio_risk.py` | 组合公式、相关性、样本和输入边界 |
| `tests/test_risk_service.py` | 部分失败、全部失败、回看范围及 MCP/HTTP 一致性 |
| `tests/test_web_risk.py` | HTTP 状态、统一 envelope 和前端 fixture 契约 |
| `tests/test_mcp_tools.py` | MCP 正常、错误和 fallback 行为 |
| `tests/test_mcp_protocol.py` | 真实 stdio 子进程发现并调用工具 |

没有修改 `vendor/hermes-agent`，没有读取、写入或提交任何密钥。

## 4. HTTP API

所有接口使用统一结构：

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "source": "akshare|cache|fixture|system|mixed",
    "as_of": "ISO-8601",
    "request_id": "UUID",
    "is_fallback": false
  },
  "warnings": []
}
```

### 4.1 `POST /api/risk/profile`

请求：

```json
{
  "amount_cny": 50000,
  "horizon_months": 12,
  "max_loss_pct": 10,
  "income_stability": "stable",
  "experience": "basic",
  "liquidity_need": "medium",
  "emergency_fund_months": 6
}
```

返回：`score`、`risk_level`、`score_breakdown`、`hard_limits` 和六项 `dimensions`。

### 4.2 `POST /api/risk/assets`

```json
{
  "symbols": ["510300", "511010"],
  "lookback_days": 252
}
```

- 标的数量：1 到 4。
- 回看范围：60 到 1260。
- 单个标的数据加载失败时保留其他可用结果，并将该项标记为 `data_unavailable`。
- 历史数据已加载但不足 60 条时返回 `metrics=null` 和 `insufficient_data`，不补造指标。
- 所有标的都无法加载时返回 HTTP 503、`risk_analysis_failed`、`retryable=true`。

### 4.3 `POST /api/risk/portfolio`

```json
{
  "weights_pct": {
    "510300": 40,
    "511010": 30,
    "518880": 20,
    "511880": 10
  },
  "lookback_days": 252
}
```

- 权重必须非负、有限、无别名重复并合计 100%。
- 组合要求全部资产历史数据可用，否则返回结构化 503。
- 共同有效收盘价不足时返回 `ok=true`、`portfolio=null` 和 warning，这是可解释的数据不足状态。
- 正常结果包含 `portfolio_metrics`、`correlation_matrix`、`net_value_curve`、`drawdown_curve` 和 `methodology`。

## 5. 计算口径

```text
资产日收益 = 当日收盘价 / 前一共同交易日收盘价 - 1
组合日收益 = sum(资产日收益 * 权重)
组合净值 = 前一日组合净值 * (1 + 组合日收益)
回撤 = 当前净值 / 历史最高净值 - 1
```

- 只接受有限且大于 0 的收盘价；重复日期保留最后一个有效值。
- 多资产只使用全部标的共有日期，不对缺失日期前向填充。
- 组合采用固定权重每日再平衡。
- 年化因子为 252；波动率使用 `ddof=1`。
- VaR/CVaR 使用历史日收益 5% 分位数。
- 相关性使用共同日期收益的 Pearson 系数；常数序列交叉相关返回 `null` 和 warning。
- 历史结果不代表未来，VaR/CVaR 不覆盖所有极端事件。

## 6. AI 的作用边界

风险数值不由 AI 计算。AI 只负责：

1. 理解用户问题；
2. 选择并调用 finance MCP 工具；
3. 引用工具真实返回值进行解释；
4. 展示数据时间、来源、fallback 和风险提示。

AI 不得自行补造价格、风险分数、相关系数、权重或收益率。模型未配置时，Web 风险页面和确定性 MCP 工具仍可独立运行。

## 7. 前端行为

- `/risk` 与 `/market` 均采用路由懒加载；最终风险 JS chunk 约 33.48 KB，gzip 约 12.19 KB。
- 风险页面包含 loading、empty、validation、error/retry、partial、fixture/fallback 和 success。
- fixture 提示合并为单条明确告警，避免重复信息；最大回撤使用风险红色。
- 表格使用内部横向滚动，不制造页面级横向溢出。
- 关键控件提供稳定 `data-testid`，便于 CI、其他成员和 AI 自动复核。
- 页面没有交易按钮、买卖价格、收益承诺或确定性预测。

## 8. 最终验证

### 8.1 Python

```powershell
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pytest.exe --cov=finance_advisor --cov-fail-under=85
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-hermes.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\preflight.ps1
```

结果：

- Ruff format/check：通过；
- strict mypy：通过；
- pip check：无损坏依赖；
- pytest：75 项通过；
- 覆盖率：87.47%；
- Hermes 0.18.2 release wheel 和固定 gitlink 校验通过；
- finance MCP 真实 stdio 连接成功，发现 6 个工具；
- preflight：通过；模型 relay 因未配置环境变量按规则跳过。

### 8.2 前端

```powershell
Set-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

结果：

- `npm ci`：通过；peer/deprecated warning 不阻断安装；
- lint、typecheck、build：通过；
- 单元测试：12 项通过；
- E2E：18 项通过，其中风险流程 4 项；
- E2E runner 结束后 `8123/5173` 均释放；
- Vitest 固定单 worker，解决高核心数 Windows 上偶发长期无输出的问题；
- 构建仍有两个大于 500 KB 的共享 chunk 提示，不影响本次功能；风险和行情页面已独立拆包。

### 8.3 真实 HTTP 与 Chromium

使用正式 `frontend/dist` 和 fixture 模式启动 FastAPI 后：

```text
GET  /api/health          200
POST /api/risk/profile    200，六维画像 6 项
POST /api/risk/assets     200，source=fixture
POST /api/risk/portfolio  200，净值曲线 253 点
GET  /                    200
```

Chromium 在 `1366x768` 下完成画像提交、切换组合风险、请求真实 FastAPI、等待两张图表并截图：

```text
documentWidth = 1366
viewportWidth = 1366
horizontalOverflow = false
canvasCount = 2
consoleErrors = 0
```

本地验收截图：

```text
E:\dingtalk\workspace\项目\financial-advisor-agent\.runtime\acceptance\risk-final-1366x768.png
```

`.runtime` 按团队规则不提交 Git。上述验证为 fixture/离线链路，不等同于实时 AKShare 或真实模型 relay 验证。

## 9. 启动方法

```powershell
Set-Location E:\dingtalk\workspace\项目\financial-advisor-agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-app.ps1 -ForceFixture -NoOpen
```

访问：

```text
http://127.0.0.1:8123/risk
```

脚本默认重新构建前端。只有确认 `frontend/dist` 已是最新版本时才使用 `-SkipFrontendBuild`。

## 10. 合并说明

- 当前分支已包含 `main@2b8b4a3`，命令 `git merge-base --is-ancestor 2b8b4a3 HEAD` 返回 0。
- 3号行情页和 4号风险页已在同一个 `App.tsx` 中分别懒加载。
- mock API 同时保留 market compare、risk profile、risk assets 和 risk portfolio。
- 共享文件冲突已逐项解决，没有覆盖 3 号行情实现。
- 组长合并后应重新运行 Python 全量门禁和前端 18 项 E2E。

5号接入 Agent 报告时，风险数值只能引用 `analyze_asset_risk`、`analyze_portfolio_risk` 或对应 HTTP API；不得让模型自行计算或补造。
