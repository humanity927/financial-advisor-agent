import { test, expect } from '@playwright/test';

test.describe('Risk Lab', () => {
  test('renders profile assessment states and fixture result', async ({ page }) => {
    await page.goto('/risk');
    await expect(page.getByText('六维画像')).not.toBeVisible();
    await page.getByRole('button', { name: '评估风险画像' }).click();
    await expect(page.getByText('六维画像')).toBeVisible();
    await expect(page.getByText('稳健型')).toBeVisible();
    await expect(page.getByText('计算时间：2026/7/20 19:00:00')).toBeVisible();
  });

  test('calculates asset risk from fixture API', async ({ page }) => {
    await page.goto('/risk');
    await page.getByRole('tab', { name: '资产风险' }).click();
    await page.getByRole('button', { name: '计算资产风险' }).click();
    await expect(page.getByText('单资产历史风险指标')).toBeVisible();
    await expect(page.getByText('沪深300ETF', { exact: true })).toBeVisible();
    await expect(page.getByText('数据截至：2026-07-17')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '状态与来源' })).toBeVisible();
  });

  test('calculates portfolio risk and displays correlation section', async ({ page }) => {
    await page.goto('/risk');
    await page.getByRole('tab', { name: '组合风险' }).click();
    await page.getByRole('button', { name: '分析组合风险' }).click();
    await expect(page.getByText('组合成分与数据来源')).toBeVisible();
    await expect(page.getByText('共同日期收益相关性')).toBeVisible();
    await expect(page.getByText('最大回撤')).toBeVisible();
    await expect(page.getByText('共同有效收盘价：253 条')).toBeVisible();
    await expect(page.getByText('数据截至：2026-07-17')).toBeVisible();
    await expect(page.locator('[data-testid="risk-net-value-chart"] canvas')).toBeVisible();
    await expect(page.locator('[data-testid="risk-drawdown-chart"] canvas')).toBeVisible();
  });

  test('blocks portfolio submission when weights do not total 100 percent', async ({ page }) => {
    await page.goto('/risk');
    await page.getByRole('tab', { name: '组合风险' }).click();
    await page.getByRole('spinbutton', { name: '510300 权重' }).fill('20');

    await expect(page.getByTestId('risk-weight-total')).toContainText('80.00%');
    await expect(page.getByRole('button', { name: '分析组合风险' })).toBeDisabled();
  });

  test('keeps the risk workspace inside a compact desktop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('/risk');
    await expect(page.getByRole('heading', { name: '风险实验室' })).toBeVisible();

    const hasDocumentOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasDocumentOverflow).toBe(false);
  });
});
