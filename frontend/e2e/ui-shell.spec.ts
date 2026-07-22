import { test, expect } from '@playwright/test';

test.describe('App Shell', () => {
  test('shows sidebar and topbar shell', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('.ant-layout-sider')).toBeVisible();
    await expect(page.getByRole('menuitem')).toHaveCount(7);
    await expect(page.getByTestId('system-topbar')).toBeVisible();
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
    await expect(topbar.getByText(/AKShare 就绪 · Tushare 就绪/)).toBeVisible();
  });

  test('keeps the mobile navigation trigger inside the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/advisor');

    const trigger = page.locator('.ant-layout-sider-zero-width-trigger');
    await expect(trigger).toBeVisible();
    const bounds = await trigger.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds?.x).toBeGreaterThanOrEqual(0);
    expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(390);

    await trigger.click();
    await expect(page.getByRole('menuitem', { name: '行情对比' })).toBeVisible();
  });
});
