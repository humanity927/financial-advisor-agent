import { test, expect } from '@playwright/test';

test.describe('Portfolio Page', () => {
  test('renders profile and current allocation controls', async ({ page }) => {
    await page.goto('/portfolio');

    await expect(page.getByRole('heading', { name: '配置规划' })).toBeVisible();
    await expect(page.getByText('当前配置', { exact: true })).toBeVisible();
    await expect(page.getByText('现金比例（%）')).toBeVisible();
    await expect(page.getByText('债券比例（%）')).toBeVisible();
    await expect(page.getByText('股票比例（%）')).toBeVisible();
    await expect(page.getByText('黄金比例（%）')).toBeVisible();
    await expect(page.getByText('当前比例合计：100.0%')).toBeVisible();
  });

  test('submits profile and renders allocation plan with deviation', async ({ page }) => {
    await page.goto('/portfolio');
    await page.locator('button[type="submit"]').click();

    await expect(page.getByText('资产配置方案')).toBeVisible();
    await expect(page.getByText('比例与金额明细')).toBeVisible();
    await expect(page.getByText('调整步骤')).toBeVisible();
    await expect(page.getByText('方案理由')).toBeVisible();
    await expect(page.getByText('偏离合计 0')).toBeVisible();
    await expect(page.getByText('风险提示')).toBeVisible();
  });
});
