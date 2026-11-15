import { test, expect } from '@playwright/test';

test('group SSE replies and explicit NPC exchange', async ({ page }) => {
  await page.goto('/testbench');
  await page.getByLabel('测试凭据').fill('e2e-admin');
  await page.getByRole('button', { name: '连接测试服务', exact: true }).click();
  await page.getByRole('button', { name: '新建测试世界' }).click();
  await page.getByRole('link', { name: '会话 2+' }).click();
  await page.getByRole('button', { name: '创建会话', exact: true }).click();
  await page.getByLabel('聊天内容').fill('大家好');
  const streamed = page.waitForResponse(r => r.url().endsWith('/turns/stream'));
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  expect((await streamed).headers()['content-type']).toContain('text/event-stream');
  await expect(page.locator('.messages .message')).toHaveCount(3);
  await expect(page.getByRole('button', { name: '强制互聊一轮' })).toBeEnabled();
  await page.getByRole('button', { name: '强制互聊一轮' }).click();
  await expect(page.locator('.messages .message')).toHaveCount(5);
  await expect(page.getByRole('button', { name: '强制互聊一轮' })).toBeEnabled();
  await page.getByLabel('NPC 互动模式').selectOption('automatic');
  await expect(page.getByLabel('NPC 互动模式')).toBeEnabled();
  await page.getByLabel('聊天内容').fill('继续讨论');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(page.locator('.messages .message')).toHaveCount(9);
  await expect(page.getByRole('button', { name: '强制互聊一轮' })).toBeEnabled();
  await expect(page.locator('.message-text').filter({ hasText: '"utterance"' })).toHaveCount(0);
});
