import { test, expect } from '@playwright/test';

test.describe('Advisor Page', () => {
  test('shows report form and empty state', async ({ page }) => {
    await page.goto('/advisor');
    await expect(page.getByText('Agent 咨询报告')).toBeVisible();
    await expect(page.getByText('填写左侧画像表单')).toBeVisible();
  });

  test('renders profile form fields', async ({ page }) => {
    await page.goto('/advisor');
    await expect(page.getByText('投资金额（元）')).toBeVisible();
    await expect(page.getByText('投资期限（月）')).toBeVisible();
    await expect(page.getByText('最大可承受亏损（%）')).toBeVisible();
    await expect(page.getByText('收入稳定性')).toBeVisible();
    await expect(page.getByText('投资经验')).toBeVisible();
    await expect(page.getByText('流动性需求')).toBeVisible();
    await expect(page.getByText('应急资金可覆盖月数')).toBeVisible();
  });
});