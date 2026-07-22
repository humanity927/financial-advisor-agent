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
    await expect(page.getByTestId('portfolio-submit')).toBeEnabled();
  });

  test('blocks invalid current totals and supports suggestion-only mode', async ({ page }) => {
    await page.goto('/portfolio');

    await page.getByLabel('现金比例').fill('20');
    await expect(page.getByText('当前比例合计：90.0%')).toBeVisible();
    await expect(page.getByTestId('portfolio-submit')).toBeDisabled();

    await page.getByLabel('参与当前配置对比').click();
    await expect(page.getByText('未纳入当前配置对比')).toBeVisible();
    await expect(page.getByTestId('portfolio-submit')).toBeEnabled();
  });

  test('submits profile and renders allocation plan with deviation', async ({ page }) => {
    await page.goto('/portfolio');
    await page.getByTestId('portfolio-submit').click();

    await expect(page.getByText('资产配置方案')).toBeVisible();
    await expect(page.getByText('比例与金额明细')).toBeVisible();
    await expect(page.getByText('调整步骤')).toBeVisible();
    await expect(page.getByText('方案理由')).toBeVisible();
    await expect(page.getByText('比例差额 0')).toBeVisible();
    await expect(page.getByText('金额差额 0')).toBeVisible();
    await expect(page.getByTestId('portfolio-allocation-chart').locator('canvas')).toBeVisible();
    await expect(page.getByTestId('portfolio-comparison-chart').locator('canvas')).toBeVisible();
    await expect(page.getByText('风险提示')).toBeVisible();
  });

  test('keeps portfolio results inside a compact desktop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('/portfolio');
    await page.getByTestId('portfolio-submit').click();
    await expect(page.getByTestId('portfolio-allocation-chart').locator('canvas')).toBeVisible();

    const layout = await page.evaluate(() => {
      const viewportWidth = document.documentElement.clientWidth;
      const stacks = Array.from(document.querySelectorAll(
        '.portfolio-grid > .profile-workspace-sidebar, .portfolio-grid > .profile-workspace-main',
      ));
      return {
        hasDocumentOverflow: document.documentElement.scrollWidth > viewportWidth,
        stacksInsideViewport: stacks.every(
          (stack) => stack.getBoundingClientRect().right <= viewportWidth,
        ),
      };
    });

    expect(layout.hasDocumentOverflow).toBe(false);
    expect(layout.stacksInsideViewport).toBe(true);
  });
});
