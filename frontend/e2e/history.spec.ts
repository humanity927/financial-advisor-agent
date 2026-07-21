import { test, expect } from '@playwright/test';

test('creates, views, resumes, and deletes a consultation session', async ({ page }) => {
  const historyMessage = '历史记录测试：我计划投入12万元，投资期限2年，最大可承受亏损15%，收入稳定，有基础投资经验，流动性中等，应急资金6个月，关注510300。';
  await page.goto('/advisor');
  await page.getByPlaceholder('输入咨询内容').fill(historyMessage);
  await page.getByRole('button', { name: '发送' }).click();
  await expect(page.getByRole('heading', { name: '用户画像' })).toBeVisible();

  await page.getByRole('button', { name: '历史记录' }).click();
  await expect(page.getByRole('heading', { name: '历史记录' })).toBeVisible();
  const row = page.getByRole('row').filter({ hasText: '历史记录测试' }).first();
  await row.getByRole('button', { name: /查看/ }).click();
  const detail = page.getByRole('dialog');
  await expect(detail).toBeVisible();
  await expect(detail.getByText('历史记录测试', { exact: false }).first()).toBeVisible();
  await detail.getByRole('button', { name: '继续咨询' }).click();
  await expect(page).toHaveURL(/\/advisor\?session=/);
  await expect(page.getByText('历史记录测试', { exact: false }).first()).toBeVisible();

  await page.goto('/history');
  const restoredRow = page.getByRole('row').filter({ hasText: '历史记录测试' }).first();
  await restoredRow.getByRole('button', { name: /删除/ }).click();
  await page.getByRole('dialog', { name: '删除这条咨询记录？' })
    .getByRole('button', { name: /删\s*除/ })
    .click();
  await expect(restoredRow).not.toBeVisible();
});
