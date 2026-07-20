# 前端 Mock 数据

这些 JSON 文件模拟后端 API 响应，供 3/4/5 号在无后端时独立开发前端页面。

## 使用方法

将 mock 文件与你的前端功能页面对照：

| 文件 | 对应 API | 适用页面 |
|---|---|---|
| `health.json` | `GET /api/health` | 总览 · HealthCard |
| `market-snapshot.json` | `GET /api/market/snapshot?symbols=...` | 总览 · SnapshotCard，行情对比 |
| `portfolio-plan.json` | `POST /api/portfolio/plan` | 总览 · AllocationPreview，配置规划 |
| `risk-profile.json` | `POST /api/risk/profile` | 风险实验室 |
| `risk-portfolio.json` | `POST /api/risk/portfolio` | 风险实验室 |

## 数据来源

所有数据来自真实 fixture 后端的采样，非 AI 编造。

## 响应结构

所有响应遵循统一结构 `ApiResponse<T>`：

```json
{
  "ok": true,
  "data": {},
  "meta": { "source": "...", "as_of": "...", "request_id": "...", "is_fallback": false },
  "warnings": []
}
```