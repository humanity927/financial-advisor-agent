import { test, expect } from '@playwright/test';

test.describe('App Shell', () => {
  test('shows sidebar and topbar shell', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('.ant-layout-sider')).toBeVisible();
    await expect(page.getByRole('menuitem')).toHaveCount(5);
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

    await expect(page).toHaveURL(/\/advisor$/);
    await expect(page.locator('form')).toBeVisible();
  });

  test('shows fixture mode indicators in top bar', async ({ page }) => {
    await page.goto('/');

    const topbar = page.getByTestId('system-topbar');
    await expect(topbar).toBeVisible();
    await expect(topbar.locator('.ant-tag')).toHaveCount(2);
  });
});
