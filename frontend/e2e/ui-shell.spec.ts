import { test, expect } from '@playwright/test';

test.describe('App Shell', () => {
  test('shows sidebar and topbar shell', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('.ant-layout-sider')).toBeVisible();
    await expect(page.getByRole('menuitem')).toHaveCount(7);
    await expect(page.getByTestId('system-topbar')).toBeVisible();
    await expect(page.getByRole('button', { name: '深睡金股总览' }).getByText('深睡金股')).toBeVisible();
    const bottomNavigation = page.getByRole('navigation', { name: '咨询与记录' });
    await expect(bottomNavigation.getByRole('menuitem', { name: 'Agent 咨询' })).toBeVisible();
    await expect(bottomNavigation.getByRole('menuitem', { name: '历史记录' })).toBeVisible();
  });

  test('shows loading and error states without layout overflow', async ({ page }) => {
    let releaseHealth: (() => void) | undefined;
    const healthGate = new Promise<void>((resolve) => {
      releaseHealth = resolve;
    });

    await page.route('**/api/health', async (route) => {
      await healthGate;
      await route.abort('failed');
    });
    await page.goto('/');

    await expect(page.locator('.overview-health-card .ant-skeleton')).toBeVisible();
    releaseHealth?.();
    await expect(page.locator('.overview-health-card .ant-alert-error')).toBeVisible();
    await expect(page.locator('.overview-health-card .page-state .ant-btn')).toBeVisible();

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasOverflow).toBe(false);
  });

  test('collapses the desktop sidebar without losing navigation access', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto('/');

    const sidebar = page.locator('.shell-sidebar');
    await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(228);
    await page.getByRole('button', { name: '收起导航' }).click();
    await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(72);
    await expect(page.getByRole('button', { name: '展开导航' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Agent 咨询' })).toBeVisible();
  });

  test('keeps bottom navigation reachable in a short window', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 520 });
    await page.goto('/');

    const bottomNavigation = page.getByRole('navigation', { name: '咨询与记录' });
    await expect(bottomNavigation.getByRole('menuitem', { name: 'Agent 咨询' })).toBeVisible();
    await expect(bottomNavigation.getByRole('menuitem', { name: '历史记录' })).toBeVisible();
  });

  test('navigates to market page', async ({ page }) => {
    await page.goto('/market');

    await expect(page).toHaveURL(/\/market$/);
    await expect(page.getByTestId('market-compare-chart')).toBeVisible();
  });

  test('navigates to risk page', async ({ page }) => {
    await page.goto('/risk');

    await expect(page).toHaveURL(/\/risk$/);
    await expect(page.getByRole('heading', { name: '风险实验室' })).toBeVisible();
    await expect(page.getByText('教学演示边界')).toBeVisible();
  });

  test('navigates to portfolio page', async ({ page }) => {
    await page.goto('/portfolio');

    await expect(page).toHaveURL(/\/portfolio$/);
    await expect(page.getByRole('heading', { name: '配置规划' })).toBeVisible();
    await expect(page.getByTestId('portfolio-result-panel')).toBeVisible();
  });

  test('navigates to advisor page', async ({ page }) => {
    await page.goto('/advisor');

    await expect(page).toHaveURL(/\/advisor(?:\?session=[^&]+)?$/);
    await expect(page.getByPlaceholder('输入咨询内容')).toBeVisible();
  });

  test('shows fixture mode indicators in top bar', async ({ page }) => {
    await page.goto('/');

    const topbar = page.getByTestId('system-topbar');
    await expect(topbar).toBeVisible();
    await expect(topbar.getByText('演示模式')).toBeVisible();
    await expect(topbar.getByText(/AKShare 就绪/)).toBeVisible();
    await expect(topbar.getByText(/Tushare 就绪/)).toBeVisible();
  });

  test('uses validated representative catalog data for the overview snapshot', async ({ page }) => {
    let snapshotUrl = '';
    page.on('request', (request) => {
      if (request.url().includes('/api/market/snapshot')) snapshotUrl = request.url();
    });

    await page.goto('/');
    await expect(page.getByText('已校验标的')).toBeVisible();
    await expect(page.getByText('10 项')).toBeVisible();
    await expect(page.getByText('演示数据 / 非实时行情')).toBeVisible();
    await expect(page.getByRole('cell', { name: '上证指数' })).toBeVisible();
    await expect(page.getByRole('cell', { name: '创业板指' })).toBeVisible();
    await expect.poll(() => snapshotUrl).toContain('000001');
    expect(snapshotUrl).toContain('399006');
  });

  test('uses the same investor-profile sidebar width across workspaces', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const widths: number[] = [];
    for (const path of ['/risk', '/portfolio', '/report']) {
      await page.goto(path);
      const sidebar = page.locator('.profile-workspace-sidebar');
      await expect(sidebar).toBeVisible();
      widths.push((await sidebar.boundingBox())?.width ?? 0);
    }

    expect(widths.every((width) => Math.abs(width - widths[0]) < 1)).toBe(true);
    expect(widths[0]).toBeGreaterThanOrEqual(304);
    expect(widths[0]).toBeLessThanOrEqual(336);
  });

  test('keeps the mobile navigation trigger inside the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/advisor');

    const trigger = page.getByRole('button', { name: '展开导航' });
    await expect(trigger).toBeVisible();
    const bounds = await trigger.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds?.x).toBeGreaterThanOrEqual(0);
    expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(390);

    await trigger.click();
    await expect(page.getByRole('menuitem', { name: '行情对比' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Agent 咨询' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '历史记录' })).toBeVisible();
  });

  test('keeps every route inside the mobile viewport without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    await page.setViewportSize({ width: 390, height: 844 });

    for (const path of ['/', '/market', '/risk', '/portfolio', '/report', '/advisor', '/history']) {
      await page.goto(path);
      await expect(page.locator('.section-header-title')).toBeVisible();
      const hasOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(hasOverflow, `${path} should not overflow horizontally`).toBe(false);
    }

    expect(errors).toEqual([]);
  });
});
