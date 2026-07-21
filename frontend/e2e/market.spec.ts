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
    await expect(page.locator('[data-testid="market-compare-chart"] canvas')).toBeVisible();
  });

  test('shows validation state when no symbol is selected', async ({ page }) => {
    await page.goto('/market');

    await page.getByRole('button', { name: '清空' }).click();

    await expect(page.getByText('请至少选择一个白名单标的')).toBeVisible();
    await expect(page.getByText('请选择标的后查看行情对比')).toBeVisible();
  });
});
