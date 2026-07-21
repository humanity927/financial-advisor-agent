import { test, expect } from '@playwright/test';

const COMPLETE_PROFILE = '我计划投入10万元，投资期限2年，最大可承受亏损15%，收入稳定，有基础投资经验，流动性中等，应急资金6个月，关注510300。';

test.describe('Agent consultation', () => {
  test('runs a multi-turn workspace action and shows four tool states', async ({ page }) => {
    await page.goto('/advisor');
    await expect(page.getByRole('heading', { name: 'Agent 咨询' })).toBeVisible();
    const input = page.getByPlaceholder('输入咨询内容');
    await input.fill(COMPLETE_PROFILE);
    await page.getByRole('button', { name: '发送' }).click();

    await expect(page.getByRole('heading', { name: '用户画像' })).toBeVisible();
    await expect(page.getByText('用户画像 · system')).toBeVisible();
    await expect(page.getByText('行情快照 · fixture')).toBeVisible();
    await expect(page.getByText('风险指标 · fixture')).toBeVisible();
    await expect(page.getByText('配置建议 · system')).toBeVisible();
    await expect(page.getByText('已同步到工作台')).toBeVisible();
    await expect(page.getByText('数据截至 2026-07-17')).toBeVisible();
  });

  test('keeps chat layout within mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/advisor');
    await expect(page.getByPlaceholder('输入咨询内容')).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
  });
});

test.describe('Formal report', () => {
  test('shows the complete profile form and renders an audited report', async ({ page }) => {
    await page.goto('/report');
    await expect(page.getByRole('heading', { name: '正式咨询报告' })).toBeVisible();
    await expect(page.getByText('投资金额（元）')).toBeVisible();
    await page.getByRole('button', { name: '生成报告' }).click();

    await expect(page.getByRole('heading', { name: '用户画像' })).toBeVisible();
    await expect(page.getByText('assess_investor_profile · system')).toBeVisible();
    await expect(page.getByText('历史表现不代表未来收益。')).toBeVisible();
  });
});
