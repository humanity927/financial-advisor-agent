import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));

async function loadFixture(name) {
  const file = join(frontendRoot, 'mock', name);
  return JSON.parse(await readFile(file, 'utf8'));
}

const fixtures = {
  health: await loadFixture('health.json'),
  marketSnapshot: await loadFixture('market-snapshot.json'),
  portfolioPlan: await loadFixture('portfolio-plan.json'),
  riskProfile: await loadFixture('risk-profile.json'),
  riskPortfolio: await loadFixture('risk-portfolio.json'),
};

const advisorResponse = {
  ok: true,
  data: {
    content:
      '# 用户画像\n\n这是 fixture E2E 报告。\n\n# 行情摘要\n\n使用演示数据。\n\n# 风险指标\n\n仅展示历史统计。\n\n# 配置建议\n\n请结合自身情况审慎决策。\n\n# 建议原因\n\n基于确定性规则。\n\n# 数据时间与来源\n\n来源：fixture。\n\n# 风险提示\n\n历史表现不代表未来收益。',
    source: 'fixture',
    as_of: '2026-07-17',
    is_fallback: true,
    warnings: ['演示数据/非实时数据'],
  },
  meta: {
    source: 'fixture',
    as_of: '2026-07-17',
    request_id: 'e2e-advisor',
    is_fallback: true,
  },
  warnings: ['演示数据/非实时数据'],
};

function sendJson(response, status, payload) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(payload));
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1:8123');

  if (request.method === 'GET' && url.pathname === '/api/health') {
    sendJson(response, 200, fixtures.health);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/market/snapshot') {
    sendJson(response, 200, fixtures.marketSnapshot);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/portfolio/plan') {
    sendJson(response, 200, fixtures.portfolioPlan);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/risk/profile') {
    sendJson(response, 200, fixtures.riskProfile);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/risk/portfolio') {
    sendJson(response, 200, fixtures.riskPortfolio);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/advisor/report') {
    sendJson(response, 200, advisorResponse);
    return;
  }

  sendJson(response, 404, {
    ok: false,
    data: null,
    meta: {
      source: 'system',
      as_of: new Date().toISOString(),
      request_id: 'e2e-not-found',
      is_fallback: false,
    },
    warnings: [],
    error: { code: 'not_found', message: 'fixture endpoint not found', retryable: false },
  });
});

server.listen(8123, '127.0.0.1', () => {
  console.log('fixture mock API listening on http://127.0.0.1:8123');
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
