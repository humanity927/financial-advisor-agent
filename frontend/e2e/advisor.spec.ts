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

  test('submits profile and renders the fixture report', async ({ page }) => {
    await page.goto('/advisor');
    await page.getByRole('button', { name: '生成报告' }).click();

    await expect(page.getByRole('heading', { name: '用户画像' })).toBeVisible();
    await expect(page.getByTestId('system-topbar').getByText('演示数据')).toBeVisible();
    await expect(page.getByText('历史表现不代表未来收益。')).toBeVisible();
  });
});
