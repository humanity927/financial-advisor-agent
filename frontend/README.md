# 前端开发指南

## 技术栈

- React 18 + TypeScript (strict)
- Vite 6
- Ant Design 5
- React Router DOM
- TanStack Query 5
- ECharts (echarts-for-react)
- React Markdown + rehype-sanitize
- Lucide React icons
- Vitest + React Testing Library
- Playwright

## 启动

```bash
npm ci          # 安装依赖 (锁定版本)
npm run dev     # 开发模式 http://127.0.0.1:5173
npm run build   # 生产构建
```

## API 代理

Vite 将 `/api` 自动代理到 `http://127.0.0.1:8123`，无需 CORS 配置。

## 目录规范

```
src/
├── api/            # API 客户端、类型、Query Key 工厂
├── app/layout/     # 应用壳 (AppShell, Sidebar, TopBar)
├── components/     # 共享组件
│   ├── SourceStamp.tsx    # 数据来源标签
│   ├── StatusBadge.tsx    # 状态徽章
│   ├── MetricValue.tsx    # 涨跌着色数值
│   ├── PageState.tsx      # 统一页面状态 (6种)
│   ├── ProfileForm.tsx    # 投资者画像表单
│   └── SectionHeader.tsx  # 页面标题
└── features/       # 功能页面 (按域划分)
    ├── overview/   # 总览页 (2号)
    ├── market/     # 行情对比 (3号)
    ├── risk/       # 风险实验室 (4号)
    ├── portfolio/  # 配置规划 (5号)
    └── advisor/    # Agent 报告页 (2号)
```

## 共享 API 类型 (src/api/types.ts)

```typescript
// 所有响应使用统一的 ApiResponse<T> 包装
interface ApiResponse<T> {
  ok: boolean;
  data: T;
  meta: { source: string; as_of: string; request_id: string; is_fallback: boolean };
  warnings: string[];
  error?: { code: string; message: string; retryable: boolean };
}
```

## 页面开发规则

1. `features/{feature}/` 内的组件只能 import `components/`、`api/` 和自身目录文件
2. **禁止跨 feature import**（例如 market 不能 import risk 的代码）
3. 每个页面必须覆盖：loading / empty / error / fixture / success 状态
4. 使用 `PageState` 组件实现统一状态管理

## 路由

| 路径 | 功能 | 负责人 |
|---|---|---|
| `/` | 总览 | 2号 |
| `/market` | 行情对比 | 3号 |
| `/risk` | 风险实验室 | 4号 |
| `/portfolio` | 配置规划 | 5号 |
| `/advisor` | Agent 报告 | 2号后端、5号适配器 |

注册在 `App.tsx`，新增页面请联系 2 号。

## 测试

```bash
npm run test       # Vitest 单元测试
npm run e2e        # Playwright E2E
npm run lint       # ESLint
npm run typecheck  # TypeScript 类型检查
```

## 冻结契约

所有 API 路径和响应结构见开发指南第 6 节，修改需 Issue 并由文件所有者提交兼容性变更。