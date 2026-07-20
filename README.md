# 金融理财咨询智能 Agent

基于 Hermes Agent、MCP、AKShare 和确定性风险模型的教学演示项目。系统查询 A 股 ETF 行情、评估用户风险承受能力、计算历史风险指标并生成透明的四类资产配置。系统不执行交易，不构成投资建议。

## 架构

```text
Hermes Dashboard
  -> Hermes Agent 0.18.2
     -> GPT-5.6 OpenAI-compatible relay
     -> DeepSeek fallback
     -> finance MCP (stdio)
        -> AKShare -> cache -> synthetic fixture
        -> profile scoring
        -> risk metrics
        -> rule-based allocation
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
FINANCE_FORCE_FIXTURE=0
```

不要修改或提交 `.env.example` 来保存真实密钥。

启动脚本会在每次运行前把 `.env` 中的中转站 URL、模型 ID 和 fixture 开关同步到忽略提交的运行时 `config.yaml`，因此编辑 `.env` 后不需要手工改 YAML。

运行完整预检：

```powershell
./scripts/preflight.ps1 -RequireModel
```

启动 Dashboard：

```powershell
./scripts/run-dashboard.ps1
```

浏览器地址：[http://127.0.0.1:9119](http://127.0.0.1:9119)。Dashboard 只监听回环地址。

没有行情网络时可以强制使用明确标记的演示数据：

```powershell
./scripts/run-dashboard.ps1 -ForceFixture
```

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

## 支持标的

| 代码 | 名称 | 资产类别 |
|---|---|---|
| 510300 | 沪深300ETF | 股票 |
| 511010 | 国债ETF | 债券 |
| 518880 | 黄金ETF | 黄金 |
| 511880 | 货币ETF | 现金管理 |

## 数据与模型说明

- 行情优先来自 AKShare；现价缓存60秒，历史数据缓存6小时。
- 实时请求失败后依次使用过期缓存和 `data/fixtures` 中的合成演示数据。
- fixture 永远标记为“演示数据/非实时数据”，不能当作真实行情引用。
- 历史风险指标包括年化收益、年化波动率、最大回撤、单日95% VaR和CVaR。
- 资产配置由固定规则产生，大模型只负责理解、工具调度和文字解释。

## 质量检查

```powershell
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/mypy.exe src
./.venv/Scripts/pytest.exe --cov=finance_advisor --cov-fail-under=85
./scripts/verify-hermes.ps1
./scripts/preflight.ps1
```

`preflight.ps1` 在未配置模型密钥时仍会完成本地金融核心和 MCP 检查，并明确跳过联网模型测试。答辩前必须使用 `-RequireModel` 完成真实模型及备用通道验证。

## 常见问题

- GitHub clone 较慢：保持 submodule 固定到文档中的提交，不要改用非官方源码镜像。
- 中转站普通聊天可用但 Agent 不工作：运行模型预检；中转站必须完整支持 `/v1/chat/completions`、标准 `tool_calls` 和工具结果续写。
- AKShare失败：检查 `meta.source`。`cache` 表示缓存，`fixture` 表示非实时演示数据。
- Hermes更新提示：本项目禁止直接运行 `hermes update`。升级应修改固定提交并重新运行全部测试。

## 免责声明

本项目仅用于课程教学和软件工程演示。历史表现不代表未来收益，VaR/CVaR 不覆盖所有极端事件，输出不构成任何投资、法律或税务建议。
