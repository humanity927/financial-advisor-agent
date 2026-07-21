import { test, expect } from '@playwright/test';

test.describe('App Shell', () => {
  test('shows sidebar brand name', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('深睡金股')).toBeVisible();
  });

  test('all 5 navigation items are visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('总览')).toBeVisible();
    await expect(page.getByText('行情对比')).toBeVisible();
    await expect(page.getByText('风险实验室')).toBeVisible();
    await expect(page.getByText('配置规划')).toBeVisible();
    await expect(page.getByText('Agent 报告')).toBeVisible();
  });

  test('navigates to market page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('行情对比').click();
    await expect(page.getByText('由功能负责人独立开发中')).toBeVisible();
  });

  test('navigates to risk page', async ({ page }) => {
    await page.goto('/');
    await page.getByText('风险实验室').click();
    await expect(page.getByText('由功能负责人独立开发中')).toBeVisible();
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
    await expect(page.getByText('fixture 模式')).toBeVisible();
  });
});