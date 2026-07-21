import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const root = fileURLToPath(new URL('..', import.meta.url));
const startupTimeoutMs = 30_000;

const services = [
  {
    name: 'fixture mock API',
    command: process.execPath,
    args: [join(root, 'e2e', 'mock-api.mjs')],
    url: 'http://127.0.0.1:8123/api/health',
  },
  {
    name: 'Vite dev server',
    command: process.execPath,
    args: [join(root, 'node_modules', 'vite', 'bin', 'vite.js'), '--host', '127.0.0.1'],
    url: 'http://127.0.0.1:5173',
  },
];

async function isReachable(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForUrl(url, name) {
  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    if (await isReachable(url)) {
      return;
    }
    await delay(250);
  }
  throw new Error(`${name} did not become ready at ${url}`);
}

async function startService(service) {
  if (await isReachable(service.url)) {
    throw new Error(
      `${service.name} address is already in use (${service.url}); stop the existing service before E2E`,
    );
  }

  const child = spawn(service.command, service.args, {
    cwd: root,
    env: process.env,
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  const exited = new Promise((resolve) => {
    child.once('exit', (code) => resolve(code));
  });

  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`${service.name} exited before it became ready`);
    }
    if (await isReachable(service.url)) {
      return { ...service, child, exited };
    }
    await delay(250);
  }
  throw new Error(`${service.name} did not become ready at ${service.url}`);
}

async function stopService(running) {
  if (!running.child) {
    return;
  }

  const { child, exited } = running;
  if (child.exitCode !== null) {
    return;
  }

  child.kill();
  const stopped = await Promise.race([
    exited.then(() => true),
    delay(1_500).then(() => false),
  ]);
  if (!stopped && process.platform === 'win32' && child.pid) {
    await new Promise((resolve) => {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
      }).once('exit', resolve);
    });
  }
}

async function runPlaywright(args) {
  const child = spawn(
    process.execPath,
    [join(root, 'node_modules', 'playwright', 'cli.js'), 'test', ...args],
    {
      cwd: root,
      env: {
        ...process.env,
        FINANCE_SKIP_PLAYWRIGHT_WEBSERVER: '1',
      },
      stdio: 'inherit',
    },
  );
  return new Promise((resolve) => {
    child.once('exit', (code) => resolve(code ?? 1));
  });
}

const started = [];

try {
  for (const service of services) {
    started.push(await startService(service));
  }
  process.exitCode = await runPlaywright(process.argv.slice(2));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  for (const service of started.reverse()) {
    await stopService(service);
  }
}
