# 4号交接说明：风险实验室与风险 MCP

> 负责人：4号成员  
> 分支：`feat/risk-lab-mcp`  
> 本次交付提交：`cccf4b8` (`feat(risk): complete risk lab web integration`)
> 基线：`main@1231474`；依赖 3 号 Web 骨架：`6f26abc`
> 文档更新时间：2026-07-21
> 状态：风险后端 API、风险实验室页面、fixture、定向测试已完成；合并与真实服务联调结果见本文第 8 节。
> 数据边界：只做历史统计和教学演示，不预测未来，不执行交易，不构成投资建议。

## 1. 本次交付

本部分把原来的风险核心和 MCP 工具接入了 Web 工作台，完成了以下用户流程：

1. 在“风险画像”页提交七项用户信息，查看确定性的风险分数、风险等级、六维得分和硬约束。
2. 在“资产风险”页选择 1 到 4 个白名单 ETF，查看年化收益、年化波动率、最大回撤、95% VaR/CVaR 和观测数。
3. 在“组合风险”页调整四类 ETF 的固定权重，查看组合指标、权重、相关性矩阵、净值曲线和回撤曲线。
4. 所有数据都显示来源、时间和回退/演示状态；请求失败、数据不足和部分数据告警都有独立界面状态。

大模型不参与金融数值计算。Python 确定性函数产生风险指标，Agent/MCP 只负责工具调用和文字解释。

## 2. 调用链

```text
浏览器 /risk
  -> frontend/src/features/risk/RiskPage.tsx
  -> frontend/src/api/client.ts
  -> FastAPI /api/risk/{profile|assets|portfolio}
  -> web/routes/risk.py
  -> MarketService
     -> AKShare -> cache -> data/fixtures/market_data.json
  -> risk/profile.py、risk/metrics.py、risk/portfolio.py
  -> 统一 envelope 返回前端
  -> 风险画像、指标表、相关性表、净值/回撤图
```

MCP 仍然走原有链路：

```text
Hermes Agent -> finance MCP -> assess_investor_profile /
analyze_asset_risk / analyze_portfolio_risk -> 确定性风险函数
```

Web 路由没有反向 import MCP server，避免把 stdio 协议层和 HTTP 层耦合。

## 3. 修改文件

### 3.1 4号业务实现

| 文件 | 作用 |
|---|---|
| `src/finance_advisor/web/routes/risk.py` | 新增画像、单资产风险、组合风险三个 HTTP 路由；复用现有风险领域函数和统一响应结构 |
| `frontend/src/features/risk/RiskPage.tsx` | 风险实验室页面，包含三个 Tab、表单、状态、指标表、相关性表和 ECharts 曲线 |
| `frontend/src/features/risk/types.ts` | 风险页面的 API 类型；兼容后端正式组合结构和已有 fixture 结构 |
| `tests/test_web_risk.py` | 五项风险 Web API 定向测试 |
| `frontend/e2e/risk.spec.ts` | 画像、资产风险、组合风险三个真实浏览器流程 |
| `frontend/mock/risk-assets.json` | 资产风险 fixture，明确标记为演示数据 |

### 3.2 必要的共享接线

| 文件 | 变更原因 |
|---|---|
| `frontend/src/App.tsx` | 将 `/risk` 从占位页替换为 `RiskPage` |
| `frontend/e2e/mock-api.mjs` | 为前端 E2E 增加 `/api/risk/assets` fixture 路由 |
| `frontend/e2e/ui-shell.spec.ts` | 将风险导航断言从占位文本改为真实页面标题 |

本分支还合入了已推送的基础依赖：2号前端 `main@1231474` 和 3号 Web 骨架 `6f26abc`。没有修改 `vendor/hermes-agent`，没有读取或写入密钥。

## 4. HTTP 接口契约

所有接口均返回项目统一 envelope：`ok`、`data`、`meta`、`warnings`；失败时增加 `error.code`、`error.message` 和 `error.retryable`。

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

成功数据包含：

```text
score
risk_level
score_breakdown
hard_limits
dimensions[]: dimension / score / max_score
```

### 4.2 `POST /api/risk/assets`

请求字段：

```json
{
  "symbols": ["510300", "511010"],
  "lookback_days": 252
}
```

限制：标的 1 到 4 个；`lookback_days` 为 60 到 1260。每个资产返回 `metrics`、`source`、`warning`；数据不足时 `metrics` 为 `null`，不会伪造数值。

### 4.3 `POST /api/risk/portfolio`

请求字段：

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

权重必须非负、有限、与白名单标的一一对应，合计必须为 100%。成功的 `data.portfolio` 包含：

```text
weights_pct
portfolio_metrics
correlation_matrix
net_value_curve
drawdown_curve
methodology
```

共同有效收盘价不足时仍返回 `ok=true`，但 `portfolio=null` 并附明确 warning，方便前端展示“数据不足”。

## 5. 计算口径

- 只接受有限且大于 0 的收盘价；重复日期保留最后一个有效值。
- 多资产只使用全部标的共同拥有的日期，不对缺失日期前向填充。
- 组合使用固定权重每日再平衡口径。
- 年化因子为 252 个交易日；波动率使用样本标准差 `ddof=1`。
- VaR/CVaR 使用历史日收益 5% 分位数，不代表极端事件保护。
- 相关性为共同日期收益的 Pearson 相关系数；波动不足时返回 `null` 和 warning。
- 前端只展示 API 返回数字，不自行计算或补造金融数值。

原有 MCP `analyze_portfolio_risk` 的计算规则保持不变，Web API 直接复用同一领域函数，避免 Web 和 MCP 产生两套公式。

## 6. 页面状态和安全边界

- 画像、资产和组合三个面板都覆盖 loading、empty、API error、retry 和 success。
- `source=fixture` 或 `is_fallback=true` 时显示演示/回退提示。
- 组合共同数据不足时展示 partial 状态，不显示虚假曲线或指标。
- 相关性和风险指标带有历史统计说明；页面不提供交易按钮、买入价、卖出价、收益承诺或预测文案。
- 报告和 API 错误不向前端暴露 Python traceback。

## 7. 本地运行

项目根目录：

```text
E:\dingtalk\workspace\项目\financial-advisor-agent
```

安装前端依赖：

```powershell
Set-Location E:\dingtalk\workspace\项目\financial-advisor-agent\frontend
npm.cmd ci
```

仅看前端 fixture：

```powershell
Set-Location E:\dingtalk\workspace\项目\financial-advisor-agent\frontend
npm.cmd run e2e
```

启动包含前端构建的本地 Web：

```powershell
Set-Location E:\dingtalk\workspace\项目\financial-advisor-agent
.\scripts\run-app.ps1 -ForceFixture -NoOpen
```

默认地址：`http://127.0.0.1:8123`。该脚本绑定回环地址，不对公网开放。`-ForceFixture` 仅用于无行情网络时的离线演示，正式数据链路仍按 AKShare、缓存、fixture 顺序工作。

## 8. 验证记录

以下命令已在 2026-07-21 执行：

```powershell
.\.venv\Scripts\ruff.exe format --check src tests
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\pytest.exe tests\test_web_risk.py tests\test_web_app.py tests\test_web_market.py -q
Set-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
npm.cmd run test
npm.cmd run e2e
```

结果：

- Ruff format：通过；
- Ruff lint：通过；
- strict mypy：通过；
- Web 定向测试：12 项通过；
- 前端 typecheck：通过；
- 前端 lint：通过；
- 前端 build：通过；存在约 2.3 MB 主 chunk 的优化提示，不阻断功能；
- 前端单元测试：12 项通过；
- 前端 E2E：13 项通过，其中本次新增风险流程 3 项。

上述前端检查使用 `npm ci` 安装锁定依赖；安装时的 peer/deprecated 警告未导致失败。

另外已执行完整 Python 覆盖率门禁、`scripts/verify-hermes.ps1` 和 `scripts/preflight.ps1`：66 项测试通过，覆盖率 85.24%，Hermes 固定版本校验通过，preflight 通过；模型 relay 因未配置模型环境变量按项目规则跳过。使用 `scripts/run-app.ps1 -ForceFixture -NoOpen -SkipFrontendBuild` 启动后，HTTP 冒烟结果为：`GET /api/health=200`、`POST /api/risk/profile=200`、`POST /api/risk/assets=200`、`POST /api/risk/portfolio=200`、首页 `GET /=200`。这些是本地 fixture/离线验证，不等同于实时 AKShare 或模型联调。

## 9. 后续成员接入

### 2号前端

- `/risk` 已在本分支接入 `RiskPage`；若 2 号后续统一路由，应保留该路由和 `frontend/src/features/risk/**`。
- 共享 API Client 和 `ApiResponse` envelope 不要复制；新增接口继续使用 `client.post`。
- 若要改变全局主题或共享组件，单独提交共享文件改动，避免与风险业务混在一起。

### 3号 Web

- 本分支已基于 3 号 Web 骨架实现 `routes/risk.py`；合并时保留 `web/common.py` 的 `MarketService` 工厂和统一异常处理。
- 不要把风险公式复制到 route；风险计算继续放在 `risk/` 领域模块。
- FastAPI 依赖和启动脚本沿用 3 号版本。

### 5号 Agent 报告

- 报告中的组合风险数字只能引用 `analyze_portfolio_risk` 或对应 Web API 返回值。
- 不把年化收益、相关性、VaR、CVaR解释成未来预测。
- 缺少用户画像或权重时先追问，不能由模型自行补造。

## 10. Git 交付

本分支只应提交风险实现、必要的 Web/前端接线、风险测试和本交接文档。提交前检查：

```powershell
git status --short --branch
git diff --check
git diff --cached --stat
```

当前分支目标：`feat/risk-lab-mcp`。推送后以远程分支最新提交为准；不得把 `.env`、API Key、缓存、`node_modules`、`frontend/dist` 或测试日志提交到仓库。
