import { test, expect } from "@playwright/test";

test("single NPC generation and simulated action stay visible", async ({ page }) => {
  await page.goto("/testbench");
  await page.getByLabel("测试凭据").fill("e2e-admin");
  await page.getByRole("button", { name: "连接测试服务" }).click();
  await page.getByRole("button", { name: "新建测试世界" }).click();
  await page.getByRole("link", { name: /会话/ }).click();
  await page.getByRole("button", { name: "创建会话" }).click();
  await expect(page.getByLabel("NPC 单轮生成")).toBeVisible();
  await page.getByLabel("生成输入").fill("hello");
  await page.getByRole("button", { name: "生成一轮" }).click();
  await expect(page.locator(".action-result").first()).toContainText("succeeded");
  await expect(page.getByLabel("模拟动作")).toBeVisible();
});
