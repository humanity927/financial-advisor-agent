# 4号交付说明：风险实验室与风险 MCP

> 负责人：4号成员  
> 分支：`feat/risk-lab-mcp`  
> 最近核验：2026-07-20  
> 状态：风险核心与 MCP 已完成；FastAPI 路由和前端页面等待公共骨架后接入  
> 数据边界：仅做历史统计和教学演示，不预测未来，不构成投资建议

## 1. 交付目标

本模块回答三个问题：

1. 用户的六维风险画像是什么；
2. 多个白名单 ETF 的历史收益相关性如何；
3. 给定非负且合计 100% 的资产权重后，组合历史收益、波动、回撤、VaR 和 CVaR 如何。

大模型不参与金融数值计算。确定性 Python 函数生成全部指标，Hermes 只负责调用 MCP 工具和解释结果。

## 2. 调用关系

```text
Hermes Agent
  -> finance MCP: analyze_portfolio_risk
     -> 白名单代码与权重校验
     -> MarketService.get_history
        -> AKShare / cache / fixture
     -> calculate_portfolio_risk
        -> 共同交易日对齐
        -> 各资产日收益与 Pearson 相关系数
        -> 固定权重组合日收益
        -> 组合净值与回撤曲线
        -> 复用 calculate_risk_metrics
     -> success_response / error_response
```

后续 FastAPI 风险路由应直接复用领域函数和统一响应结构，不在前端或 route 中复制金融公式。

## 3. 已修改文件

| 文件 | 变更 |
|---|---|
| `src/finance_advisor/risk/portfolio.py` | 新增权重校验、共同日期对齐、相关矩阵、组合净值、回撤和组合指标 |
| `src/finance_advisor/risk/profile.py` | 新增六维画像最大分值和图表数据，不修改原评分权重 |
| `src/finance_advisor/mcp_server.py` | 注册 `analyze_portfolio_risk`，补充画像 `dimensions` 字段 |
| `config/hermes-config.template.yaml` | 将新工具加入 finance 工具白名单 |
| `tests/test_portfolio_risk.py` | 新增组合算法、边界、相关性和样本不足测试 |
| `tests/test_profile.py` | 验证六维得分与原总分一致，维度满分合计 100 |
| `tests/test_mcp_tools.py` | 验证正常、无效权重、fixture 与样本不足响应 |
| `tests/test_mcp_protocol.py` | 通过真实 stdio MCP 子进程发现并调用新工具 |

没有修改 `vendor/hermes-agent`、行情提供器、资产配置算法、模型密钥或运行时数据。

## 4. 计算口径

### 4.1 数据清洗与对齐

- 只接受有限且大于 0 的收盘价；
- 同一资产同一日期重复时保留最后一个有效值；
- 多资产只使用全部标的共同拥有的日期；
- 至少需要 60 个共同有效收盘价；
- 不使用未来数据，不对缺失日期进行前向填充。

### 4.2 权重

- 每项权重必须是非负有限数值；
- 权重合计必须为 `100%`，绝对误差不超过 `1e-6`；
- 资产代码与权重键必须一一对应；
- 允许 0% 权重资产参与相关性比较；
- 组合采用固定权重每日再平衡口径。

### 4.3 指标

```text
资产日收益 = 当日收盘价 / 前一共同交易日收盘价 - 1
组合日收益 = sum(资产日收益 * 权重)
组合净值 = 前一日组合净值 * (1 + 组合日收益)
回撤 = 当前净值 / 历史最高净值 - 1
```

- 年化收益：按首尾净值的几何收益折算，年化因子 252；
- 年化波动率：样本标准差 `ddof=1` 乘 `sqrt(252)`；
- 最大回撤：组合净值相对历史峰值的最小值；
- VaR：历史日收益 5% 分位数的损失绝对值；
- CVaR：低于或等于 VaR 分位点的平均损失；
- 相关性：共同日期日收益的 Pearson 相关系数；
- 常数收益序列的交叉相关系数返回 `null` 和 warning，对角线仍为 1。

所有指标描述历史，不外推未来。

## 5. MCP 工具契约

工具名：`analyze_portfolio_risk`

输入示例：

```json
{
  "weights_pct": {
    "510300": 40.0,
    "511010": 30.0,
    "518880": 20.0,
    "511880": 10.0
  },
  "lookback_days": 252
}
```

限制：

- 支持 1～4 个白名单 ETF；
- `lookback_days` 范围为 60～1260；
- 支持代码或既有中文别名，但同一标的不能通过代码和别名重复出现。

成功响应的 `data`：

```text
portfolio.weights_pct
portfolio.portfolio_metrics
portfolio.correlation_matrix
portfolio.net_value_curve
portfolio.drawdown_curve
portfolio.methodology
assets[]
method
```

统一元数据继续使用项目既有字段：`source`、`as_of`、`request_id`、`is_fallback` 和 `warnings`。

稳定错误码：

| 错误码 | 含义 |
|---|---|
| `invalid_symbol` | 存在非白名单标的 |
| `invalid_weights` | 权重为空、重复、非有限、为负或合计不等于 100% |
| `invalid_lookback` | 回看天数不在 60～1260 |
| `portfolio_risk_failed` | 历史数据或组合计算发生非预期错误 |

共同样本不足不是协议错误：返回 `ok=true`、`portfolio=null` 和明确 warning，同时保留真实的 cache/fixture 来源信息，方便页面展示“数据不足”状态。

## 6. 前端展示字段

风险页面可以直接使用以下数据：

- `assess_investor_profile.data.dimensions`：六维画像图；
- `portfolio.portfolio_metrics`：指标摘要；
- `portfolio.correlation_matrix`：固定 `-1～1` 色域热力图；
- `portfolio.net_value_curve`：组合净值折线；
- `portfolio.drawdown_curve`：历史回撤曲线；
- `assets`：名称、类别、权重、来源和单项 warning；
- 顶层 `meta` 与 `warnings`：数据时间和降级状态。

页面不能仅用红绿表达结果，不能显示原始 JSON，fixture 必须写“演示数据/非实时数据”。

## 7. 真实验证记录

### 7.1 自动化全量验证

已执行：

```powershell
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/mypy.exe src
./.venv/Scripts/pytest.exe --cov=finance_advisor --cov-fail-under=85
./scripts/verify-hermes.ps1
./scripts/preflight.ps1
```

最近结果：

- Ruff：通过；
- strict mypy：通过；
- pytest：50 项通过；
- 总覆盖率：87.73%；
- Hermes：0.18.2 release wheel 与固定 gitlink 校验通过；
- finance MCP：真实 stdio 连接成功，发现 6 个工具；
- 模型预检：本机未配置提交所需的模型环境变量，因此按项目规则跳过，不影响金融核心和 MCP 验证。

### 7.2 4号成员手工复核

2026-07-20，4号成员在独立 PowerShell 终端中亲自执行以下步骤，不依赖开发代理代跑：

```powershell
cd E:\dingtalk\workspace\项目\financial-advisor-agent
git switch feat/risk-lab-mcp
git status --short --branch
./.venv/Scripts/python.exe --version
./.venv/Scripts/pytest.exe `
  tests/test_portfolio_risk.py `
  tests/test_profile.py `
  tests/test_mcp_tools.py `
  tests/test_mcp_protocol.py -q
./scripts/preflight.ps1
```

手工复核结果：

- 当前分支：`feat/risk-lab-mcp`；
- 工作区：干净，无未提交文件；
- Python：3.11.9；
- 风险相关定向测试：34 项通过，`100%`；
- finance MCP：真实 stdio 连接成功，用时约 3297ms；
- 工具发现：6 个，包含 `analyze_portfolio_risk`；
- 最终状态：`Preflight passed`。

终端中的 `Hermes source checkout is not initialized` 是非阻断警告：本地没有完整上游源码副本，但官方 0.18.2 release wheel 和固定 gitlink SHA 已通过校验。`Primary relay preflight skipped` 表示未配置大模型环境变量，只跳过模型调用，不影响4号风险核心与 MCP 验收。

### 7.3 四资产 fixture 冒烟

四资产 fixture 冒烟结果：

| 项目 | 结果 |
|---|---:|
| 权重 | 40% / 30% / 20% / 10% |
| 共同观测 | 253 |
| 年化收益 | 2.3325% |
| 年化波动率 | 3.9856% |
| 最大回撤 | -3.2517% |

这些数字来自合成 fixture，只用于验证算法和离线演示，不是真实行情结论。

### 7.4 独立公式复算

另外使用 Pandas 独立复算同一组四资产数据，未调用本模块的中间计算函数。对比结果如下：

| 对比项 | 最大绝对差异 |
|---|---:|
| 组合净值 | `< 5e-7` |
| 回撤百分比 | `< 5e-5` |
| Pearson 相关系数 | `< 2e-7` |

差异来自本模块面向接口输出时的固定小数位舍入，计算方向与独立复算一致。

## 8. 其他成员接入事项

### 2号前端

- 使用本文件第 6 节字段，不自行重算指标；
- 共享画像表单提交后展示 `dimensions`；
- 为 `portfolio=null`、fixture、cache、partial warning 提供独立状态；
- 风险页面最终文件放在 `frontend/src/features/risk/**`。

### 3号 Web 平台

- FastAPI 公共骨架合并后，将 `POST /api/risk/profile`、`POST /api/risk/assets`、`POST /api/risk/portfolio` 交给4号接入；
- 提供公共 `MarketService` 依赖或工厂，避免 Web route 从 MCP 层反向 import；
- 保持项目现有 `success_response` / `error_response`；
- `pyproject.toml` 中的 FastAPI/Uvicorn 依赖由3号统一维护。

### 5号 Hermes 报告

- 在报告约束中明确：组合风险数字只能引用 `analyze_portfolio_risk`；
- 不把相关性、VaR、CVaR解释成未来预测；
- 缺少用户权重时先追问或使用确定性配置工具结果，不能让模型自行编造权重。

## 9. 尚未完成与阻塞

- FastAPI 风险路由：等待3号公共 Web 骨架和依赖入口；
- 风险实验室页面：等待2号前端工程、共享组件和 API Client；
- 风险页面 E2E：等待Vite、Playwright配置；
- 与最新 `main` 的最终集成：在基础 PR 合并后执行。

若公共骨架延期，4号可以先提供风险领域处理函数和固定 JSON 契约，但不应重复创建第二套前端框架、API Client或FastAPI应用入口。
