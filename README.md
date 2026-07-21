# 金融理财咨询智能 Agent

基于 Hermes Agent、MCP、AKShare 和确定性风险模型的教学演示项目。系统查询 A 股 ETF 行情、评估用户风险承受能力、计算历史风险指标并生成透明的四类资产配置。系统不执行交易，不构成投资建议。

## 架构

```text
React 工作台
  -> FastAPI BFF
     -> 行情目录与行情服务：AKShare -> 真实行情磁盘缓存 -> 明确失败
     -> 确定性画像、风险与配置服务
     -> 本地会话存储（.runtime/sessions）
     -> Hermes CLI 公共 chat 接口
        -> finance MCP (stdio)
           -> assess_investor_profile
           -> get_market_snapshot
           -> analyze_asset_risk
           -> build_allocation
```

Hermes 固定在 `v2026.7.7.2` / `9de9c25f620ff7f1ce0fd5457d596052d5159596`，位于 `vendor/hermes-agent` 并用于上游源码审计。运行时安装相同版本的官方发布 wheel，因为固定提交不追踪 Dashboard 的预构建资源。业务代码不会修改或 import Hermes 私有模块。

## Windows 快速开始

环境要求：PowerShell、Git 和 Python 3.11。建议能够访问 GitHub，以便初始化用于审计的 submodule。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./scripts/bootstrap.ps1
```

安装脚本会创建 `.venv`，在该 venv 内配置清华 PyPI 源，失败时单次改用阿里云源。脚本只接受官方 `hermes-agent==0.18.2` 发布 wheel，并以 editable 方式安装本项目。

如果 GitHub Git 通道在下载中持续断开，可跳过 submodule 网络初始化。仓库仍保留相同 SHA 的 gitlink，运行时安装方式不变：

```powershell
./scripts/bootstrap.ps1 -SkipSubmoduleNetwork
```

编辑 `.runtime/hermes/.env`：

```dotenv
RELAY_BASE_URL=https://你的中转站/v1
RELAY_API_KEY=你的密钥
RELAY_MODEL_ID=中转站实际返回的模型ID
DEEPSEEK_API_KEY=国内备用密钥
```

不要修改或提交 `.env.example` 来保存真实密钥。fixture/mock 仅供自动化测试，正常启动脚本会固定关闭 fixture。

启动脚本会在每次运行前把 `.env` 中的中转站 URL 和模型 ID 同步到忽略提交的运行时 `config.yaml`，因此编辑 `.env` 后不需要手工改 YAML。

运行完整预检：

```powershell
./scripts/preflight.ps1 -RequireModel
```

启动 Dashboard：

```powershell
./scripts/run-dashboard.ps1
```

浏览器地址：[http://127.0.0.1:9119](http://127.0.0.1:9119)。Dashboard 只监听回环地址。

## 金融工作台 Web API

FastAPI 工作台默认只绑定回环地址：

```powershell
./scripts/run-app.ps1
```

浏览器地址：[http://127.0.0.1:8123](http://127.0.0.1:8123)。脚本默认先重建 `frontend/dist`，随后由 FastAPI 在同一端口托管 SPA；只有明确传入 `-SkipFrontendBuild` 才会复用已有构建。`/api/*` 不会被 fallback 成前端页面，行情页位于 `/market`。

核心端点：

```text
GET  /api/health
GET  /api/market/catalog/search?q=沪深300
GET  /api/market/snapshot?symbols=510300,000300
POST /api/market/compare
POST /api/risk/profile
POST /api/risk/assets
POST /api/risk/portfolio
POST /api/portfolio/plan
POST /api/advisor/report
POST /api/advisor/runs/{request_id}/cancel
GET|POST|DELETE /api/sessions
GET|DELETE      /api/sessions/{session_id}
POST            /api/sessions/{session_id}/messages
POST            /api/sessions/{session_id}/regenerate
POST            /api/sessions/{session_id}/actions
```

行情中心可按代码或名称搜索 A 股 ETF，并包含一组内置 A 股指数元数据。AKShare 返回的目录会在代码、名称、市场和资产类型校验后持久化到 `.runtime/market-catalog.json`。关注列表最多 8 个标的，支持添加、删除、切换和比较。`POST /api/market/compare` 的 `range` 可选 `1M`、`3M`、`1Y`，返回共同交易日对齐后的归一化曲线、区间收益、行情快照、数据来源、抓取时间、最近交易日和缓存状态。

风险端点复用 `risk/profile.py`、`risk/metrics.py` 和 `risk/portfolio.py` 的确定性计算：`/api/risk/profile` 返回六维画像，`/api/risk/assets` 返回单资产历史风险指标，`/api/risk/portfolio` 返回组合风险、相关性、净值和回撤曲线。所有结果都带有数据来源、时间和演示/回退告警；历史统计不代表未来收益。

Agent 咨询页逐项收集投资金额、期限、最大亏损、收入稳定性、经验、流动性需求和应急资金月数。字段完整后才调用正式报告，并校验四类 MCP 工具审计记录。允许的跨页动作仅包括 `profile.patch`、`market.symbol.add/remove`、`risk.symbol.select` 和 `portfolio.inputs.patch`；未知动作由 Pydantic 拒绝。会话保存在 `.runtime/sessions`，可创建、继续、恢复、重新生成、删除或清空，长敏感号码在写盘前会被移除。

页面职责如下：总览只展示核心状态与入口；行情中心管理关注标的和比较；风险实验室解释历史风险指标；配置规划展示画像、建议配置和当前配置偏离；Agent 咨询承载多轮工具编排；正式报告提供完整咨询结果；历史记录管理本地会话。

## 演示问题

完整咨询：

```text
我有5万元，投资期限一年，最多接受10%亏损，收入稳定，有基础投资经验，
流动性要求中等，已经有6个月应急资金。请查询相关ETF行情、分析风险并给出配置建议。
```

系统应展示画像评估、行情查询、风险计算、配置生成四类工具调用。

安全边界：

```text
沪深300ETF明天一定会上涨吗？请告诉我具体买入价格。
```

系统应拒绝确定性预测和真实交易指令，改为说明历史风险与数据局限。

## 标的范围

第一版仅支持经过目录校验的 A 股指数和 ETF，不支持个股荐股、交易或收益预测。内置目录提供沪深300ETF、国债ETF、黄金ETF、货币ETF及常用沪深指数作为离线元数据；ETF 搜索结果可由 AKShare 动态扩充。目录仅保存元数据，绝不提供价格或历史行情。

## 数据与模型说明

- 当前固定依赖 AKShare `1.18.64`，ETF 使用 `fund_etf_hist_em` 与 `fund_etf_spot_em`，指数使用 `stock_zh_index_daily_em`。
- 行情请求有 8 秒超时和最多 2 次有限重试；快照缓存60秒，历史数据缓存6小时。
- 正常链路仅为 AKShare -> 由 AKShare 真实结果形成的磁盘缓存。缓存包含抓取时间、最近交易日和是否过期标记。
- AKShare 和真实缓存均不可用时返回明确错误，不生成替代行情。fixture/mock 只用于 pytest、MCP 协议测试和前端 E2E。
- 历史风险指标包括年化收益、年化波动率、最大回撤、单日95% VaR和CVaR。
- 资产配置由固定规则产生，大模型只负责理解、工具调度和文字解释。

## 质量检查

```powershell
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/mypy.exe src
./.venv/Scripts/pytest.exe --cov=finance_advisor --cov-fail-under=85
cd frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
npm.cmd run e2e
cd ..
./scripts/verify-hermes.ps1
./scripts/preflight.ps1 -RequireModel
```

`preflight.ps1` 在未配置模型密钥时仍会完成本地金融核心和 MCP 检查，并明确跳过联网模型测试。答辩前必须使用 `-RequireModel` 完成真实模型及备用通道验证。

## 常见问题

- GitHub clone 较慢：保持 submodule 固定到文档中的提交，不要改用非官方源码镜像。
- 中转站普通聊天可用但 Agent 不工作：运行模型预检；中转站必须完整支持 `/v1/chat/completions`、标准 `tool_calls` 和工具结果续写。
- AKShare失败：检查 `meta.source` 和 warning。`cache` 表示真实行情缓存，并会说明是否过期；无真实缓存时请求明确失败。
- Hermes更新提示：本项目禁止直接运行 `hermes update`。升级应修改固定提交并重新运行全部测试。

## 免责声明

本项目仅用于课程教学和软件工程演示。历史表现不代表未来收益，VaR/CVaR 不覆盖所有极端事件，输出不构成任何投资、法律或税务建议。
