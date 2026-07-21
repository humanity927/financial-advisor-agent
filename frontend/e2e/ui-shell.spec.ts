import { test, expect } from '@playwright/test';

test.describe('App Shell', () => {
  test('shows sidebar brand name', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('深睡金股')).toBeVisible();
  });

  test('all 5 navigation items are visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('menuitem', { name: '总览' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '行情对比' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '风险实验室' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '配置规划' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Agent 报告' })).toBeVisible();
  });

  test('navigates to market page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('行情对比').click();
    await expect(page.getByText('由功能负责人独立开发中')).toBeVisible();
  });

  test('navigates to risk page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('风险实验室').click();
    await expect(page.getByRole('heading', { name: '风险实验室' })).toBeVisible();
    await expect(page.getByText('教学演示边界')).toBeVisible();
  });

  test('navigates to portfolio page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('配置规划').click();
    await expect(page.getByText('由功能负责人独立开发中')).toBeVisible();
  });

  test('navigates to advisor page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('Agent 报告').click();
    await expect(page.getByText('Agent 咨询报告')).toBeVisible();
  });

  test('shows fixture mode tag in top bar', async ({ page }) => {
    await page.goto('/');
    const topbar = page.getByTestId('system-topbar');
    await expect(topbar.getByText('演示模式')).toBeVisible();
    await expect(topbar.getByText('演示数据')).toBeVisible();
  });
});
