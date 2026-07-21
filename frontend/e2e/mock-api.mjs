import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const apiPort = Number(process.env.FINANCE_E2E_API_PORT ?? 8123);

async function loadFixture(name) {
  const file = join(frontendRoot, 'mock', name);
  return JSON.parse(await readFile(file, 'utf8'));
}

const fixtures = {
  health: await loadFixture('health.json'),
  marketSnapshot: await loadFixture('market-snapshot.json'),
  marketCompare: await loadFixture('market-compare.json'),
  portfolioPlan: await loadFixture('portfolio-plan.json'),
  riskProfile: await loadFixture('risk-profile.json'),
  riskPortfolio: await loadFixture('risk-portfolio.json'),
  riskAssets: await loadFixture('risk-assets.json'),
};

const advisorResponse = {
  ok: true,
  data: {
    content:
      '## 用户画像\n\n这是 fixture E2E 报告。\n\n## 行情摘要\n\n使用演示数据。\n\n## 风险指标\n\n仅展示历史统计。\n\n## 配置建议\n\n请结合自身情况审慎决策。\n\n## 建议原因\n\n基于确定性规则。\n\n## 数据时间与来源\n\n来源：fixture。\n\n## 风险提示\n\n历史表现不代表未来收益。',
    source: 'fixture',
    as_of: '2026-07-17',
    is_fallback: true,
    warnings: ['演示数据/非实时数据'],
    tool_calls: [
      'assess_investor_profile',
      'get_market_snapshot',
      'analyze_asset_risk',
      'build_allocation',
    ].map((tool) => ({
      tool,
      called_at: '2026-07-21T10:00:00+08:00',
      ok: true,
      source: tool === 'get_market_snapshot' || tool === 'analyze_asset_risk' ? 'fixture' : 'system',
      as_of: '2026-07-17',
      error_code: null,
      summary: {},
    })),
  },
  meta: {
    source: 'fixture',
    as_of: '2026-07-17',
    request_id: 'e2e-advisor',
    is_fallback: true,
  },
  warnings: ['演示数据/非实时数据'],
};

const catalogItems = [
  { symbol: '510300', name: '沪深300ETF', asset_class: '股票', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511010', name: '国债ETF', asset_class: '债券', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '518880', name: '黄金ETF', asset_class: '黄金', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511880', name: '货币ETF', asset_class: '现金', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '000001', name: '上证指数', asset_class: '股票', market: 'SH', asset_type: 'index', provider_symbol: 'sh000001' },
];
const sessions = new Map();

function envelope(data, source = 'system') {
  return {
    ok: true,
    data,
    meta: {
      source,
      as_of: '2026-07-21T10:00:00+08:00',
      request_id: `e2e-${Date.now()}`,
      is_fallback: source === 'fixture',
    },
    warnings: [],
  };
}

function newSession(title = '新咨询') {
  const now = new Date().toISOString();
  const session = {
    id: crypto.randomUUID(),
    title,
    created_at: now,
    updated_at: now,
    profile: {},
    symbols: [],
    risk_symbol: null,
    current_allocation_pct: null,
    messages: [],
  };
  sessions.set(session.id, session);
  return session;
}

function chatTurn(session, content) {
  const now = new Date().toISOString();
  const profile = {
    amount_cny: 100000,
    horizon_months: 24,
    max_loss_pct: 15,
    income_stability: 'stable',
    experience: 'basic',
    liquidity_need: 'medium',
    emergency_fund_months: 6,
  };
  const actions = [
    { type: 'profile.patch', payload: profile },
    { type: 'market.symbol.add', payload: { symbol: '510300' } },
    { type: 'risk.symbol.select', payload: { symbol: '510300' } },
  ];
  const user = {
    id: crypto.randomUUID(), role: 'user', content, created_at: now, status: 'complete',
    source: 'system', as_of: null, is_fallback: false, tool_calls: [], actions: [],
  };
  const assistant = {
    id: crypto.randomUUID(), role: 'assistant', content: advisorResponse.data.content,
    created_at: now, status: 'complete', source: 'fixture', as_of: '2026-07-17',
    is_fallback: true, tool_calls: advisorResponse.data.tool_calls, actions,
  };
  session.title = content.slice(0, 24);
  session.profile = profile;
  session.symbols = ['510300'];
  session.risk_symbol = '510300';
  session.messages.push(user, assistant);
  session.updated_at = now;
  return { session, message: assistant, missing_fields: [], actions };
}

function sendJson(response, status, payload) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(payload));
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    return {};
  }
}

function filterMarketCompare(payload, symbols) {
  const available = new Set(payload.data.symbols.map((item) => item.symbol));
  const requested = Array.isArray(symbols) && symbols.length > 0
    ? symbols.map(String)
    : payload.data.symbols.map((item) => item.symbol);
  const invalid = requested.find((symbol) => !available.has(symbol));
  if (invalid) {
    return {
      status: 400,
      payload: {
        ok: false,
        data: null,
        meta: {
          source: 'system',
          as_of: new Date().toISOString(),
          request_id: 'e2e-invalid-symbol',
          is_fallback: false,
        },
        warnings: [],
        error: { code: 'invalid_symbol', message: `不支持的标的代码：${invalid}`, retryable: false },
      },
    };
  }

  const wanted = new Set(requested);
  return {
    status: 200,
    payload: {
      ...payload,
      data: {
        ...payload.data,
        symbols: payload.data.symbols.filter((item) => wanted.has(item.symbol)),
        normalized_series: payload.data.normalized_series.filter((item) => wanted.has(item.symbol)),
        interval_returns: payload.data.interval_returns.filter((item) => wanted.has(item.symbol)),
        snapshots: payload.data.snapshots.filter((item) => wanted.has(item.symbol)),
        source_details: payload.data.source_details.filter((item) => wanted.has(item.symbol)),
      },
    },
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1:8123');

  if (request.method === 'GET' && url.pathname === '/api/health') {
    sendJson(response, 200, fixtures.health);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/market/snapshot') {
    sendJson(response, 200, fixtures.marketSnapshot);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/market/catalog/search') {
    const query = (url.searchParams.get('q') ?? '').toLowerCase();
    const items = catalogItems.filter(
      (item) => item.symbol.includes(query) || item.name.toLowerCase().includes(query),
    );
    sendJson(response, 200, envelope({ items, catalog_fetched_at: '2026-07-21T09:00:00+08:00', query }, 'akshare'));
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/market/compare') {
    const body = await readJsonBody(request);
    const result = filterMarketCompare(fixtures.marketCompare, body.symbols);
    sendJson(response, result.status, result.payload);
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
  if (request.method === 'POST' && url.pathname === '/api/risk/assets') {
    sendJson(response, 200, fixtures.riskAssets);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/advisor/report') {
    sendJson(response, 200, advisorResponse);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/sessions') {
    const body = await readJsonBody(request);
    sendJson(response, 200, envelope(newSession(String(body.title ?? '新咨询'))));
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/sessions') {
    const items = Array.from(sessions.values()).map((session) => ({
      id: session.id,
      title: session.title,
      created_at: session.created_at,
      updated_at: session.updated_at,
      message_count: session.messages.length,
      symbols: session.symbols,
      profile_fields: Object.keys(session.profile).length,
    }));
    sendJson(response, 200, envelope({ sessions: items }));
    return;
  }
  if (request.method === 'DELETE' && url.pathname === '/api/sessions') {
    const deleted = sessions.size;
    sessions.clear();
    sendJson(response, 200, envelope({ deleted }));
    return;
  }
  const sessionMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)$/);
  if (sessionMatch && request.method === 'GET') {
    const session = sessions.get(sessionMatch[1]);
    if (session) {
      sendJson(response, 200, envelope(session));
    } else {
      sendJson(response, 404, { ok: false, data: null, meta: envelope(null).meta, warnings: [], error: { code: 'session_not_found', message: '会话不存在', retryable: false } });
    }
    return;
  }
  if (sessionMatch && request.method === 'DELETE') {
    const deleted = sessions.delete(sessionMatch[1]);
    sendJson(response, deleted ? 200 : 404, deleted ? envelope({ deleted: true }) : { ok: false, data: null, meta: envelope(null).meta, warnings: [], error: { code: 'session_not_found', message: '会话不存在', retryable: false } });
    return;
  }
  const messageMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/messages$/);
  if (messageMatch && request.method === 'POST') {
    const session = sessions.get(messageMatch[1]);
    const body = await readJsonBody(request);
    if (!session) {
      sendJson(response, 404, { ok: false, data: null, meta: envelope(null).meta, warnings: [], error: { code: 'session_not_found', message: '会话不存在', retryable: false } });
      return;
    }
    sendJson(response, 200, envelope(chatTurn(session, String(body.content ?? '')), 'fixture'));
    return;
  }
  const regenerateMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/regenerate$/);
  if (regenerateMatch && request.method === 'POST') {
    const session = sessions.get(regenerateMatch[1]);
    if (session) {
      const content = session.messages.findLast((item) => item.role === 'user')?.content ?? '重新生成';
      session.messages = session.messages.slice(0, -2);
      sendJson(response, 200, envelope(chatTurn(session, content), 'fixture'));
    } else {
      sendJson(response, 404, { ok: false, data: null, meta: envelope(null).meta, warnings: [], error: { code: 'session_not_found', message: '会话不存在', retryable: false } });
    }
    return;
  }
  if (request.method === 'POST' && url.pathname.startsWith('/api/advisor/runs/')) {
    sendJson(response, 200, envelope({ cancelled: true }));
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

const sockets = new Set();
server.on('connection', (socket) => {
  sockets.add(socket);
  socket.on('close', () => sockets.delete(socket));
});

server.listen(apiPort, '127.0.0.1', () => {
  console.log(`fixture mock API listening on http://127.0.0.1:${apiPort}`);
});

function shutdown() {
  for (const socket of sockets) {
    socket.destroy();
  }
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 500).unref();
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
