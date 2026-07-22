import { test, expect } from '@playwright/test';

test.describe('Market Page', () => {
  test('renders market comparison data from fixture API', async ({ page }) => {
    await page.goto('/market');

    await expect(page.getByRole('heading', { name: '行情对比' })).toBeVisible();
    await expect(page.getByText('归一化走势', { exact: true })).toBeVisible();
    await expect(page.getByText('区间收益与最新快照', { exact: true })).toBeVisible();
    await expect(page.getByRole('cell', { name: '510300' }).first()).toBeVisible();
    await expect(page.getByRole('cell', { name: '国债ETF' }).first()).toBeVisible();
    await expect(page.getByText('演示数据 / 非实时行情')).toBeVisible();
    await expect(page.getByText('+3.45%')).toBeVisible();
    const chart = page.locator('[data-testid="market-compare-chart"] canvas');
    await expect(chart).toBeVisible();
    await expect(chart).not.toHaveAttribute('width', '0');
  });

  test('sends the selected range and filters the comparison rows', async ({ page }) => {
    const compareRequests: Array<{ symbols: string[]; range: string }> = [];
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().endsWith('/api/market/compare')) {
        compareRequests.push(request.postDataJSON() as { symbols: string[]; range: string });
      }
    });

    await page.goto('/market');
    await expect(page.getByText('归一化走势', { exact: true })).toBeVisible();
    await page.getByText('近3月', { exact: true }).click();
    await expect.poll(() => compareRequests.some((item) => item.range === '3M')).toBe(true);

    await page.getByRole('checkbox', { name: /国债ETF/ }).click();
    await expect
      .poll(() => compareRequests.some((item) => item.symbols.length === 3 && !item.symbols.includes('511010')))
      .toBe(true);
    await expect(page.getByText('已选 3 / 4 个关注标的')).toBeVisible();
  });

  test('searches, adds, rejects duplicates, and removes watched symbols', async ({ page }) => {
    await page.goto('/market');
    const search = page.getByPlaceholder('输入代码或名称');
    await search.fill('000001');
    await search.press('Enter');
    await expect(page.getByText('000001 · 上证指数')).toBeVisible();
    await page.getByRole('button', { name: '关注 000001' }).click();
    await expect(page.getByText('已选 5 / 5 个关注标的')).toBeVisible();
    await page.getByRole('button', { name: '关注 000001' }).click();
    await expect(page.getByText('000001 已在关注列表')).toBeVisible();
    await page.getByRole('button', { name: '删除 000001' }).click();
    await expect(page.getByText('已选 4 / 4 个关注标的')).toBeVisible();
  });

  test('shows validation state when no symbol is selected', async ({ page }) => {
    await page.goto('/market');

    await page.getByRole('button', { name: '清空' }).click();

    await expect(page.getByText('请至少选择一个白名单标的')).toBeVisible();
    await expect(page.getByText('请选择标的后查看行情对比')).toBeVisible();
  });

  test('keeps the market workspace within a compact desktop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('/market');
    await expect(page.getByText('归一化走势', { exact: true })).toBeVisible();

    const hasDocumentOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasDocumentOverflow).toBe(false);
  });
});
