import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

test("run selection reads server version and filtered context", async ({
  page,
}) => {
  await page.goto("/testbench");
  await page.getByLabel("测试凭据").fill("e2e-admin");
  await page.getByRole("button", { name: "连接测试服务" }).click();
  await page.getByRole("button", { name: "新建测试世界" }).click();
  await expect(page.getByTestId("run-revision")).toContainText("0");
  await expect(page.getByLabel("当前 NPC")).toHaveValue("npc-bigfish");
  await page.getByRole("button", { name: "刷新上下文" }).click();
  await expect(page.getByTestId("context-preview")).toContainText(
    "npc-bigfish",
  );
});

async function connect(page: any) {
  await page.goto("/testbench");
  await page.getByLabel("测试凭据").fill("e2e-admin");
  await page.getByRole("button", { name: "连接测试服务", exact: true }).click();
  const created = page.waitForResponse(
    (r: any) =>
      r.request().method() === "POST" && r.url().endsWith("/api/test/v1/runs"),
  );
  await page.getByRole("button", { name: "新建测试世界" }).click();
  await expect(page.getByTestId("run-revision")).toContainText("0");
  return (await created).json();
}

test("needs submission preserves drafts and uses server confirmation", async ({
  page,
  request,
}) => {
  await connect(page);
  await page.getByLabel("饥饿程度", { exact: true }).fill("0.8");
  await expect(page.getByTestId("needs-confirmed")).toContainText("unknown");
  await page.getByRole("tab", { name: "关系与性格" }).click();
  await page.getByRole("tab", { name: "身体与需求" }).click();
  await expect(page.getByLabel("饥饿程度", { exact: true })).toHaveValue("0.8");
  await page
    .getByRole("button", { name: "提交身体与需求", exact: true })
    .click();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(page.getByTestId("report-result")).toContainText("accepted");
  await expect(page.getByTestId("needs-confirmed")).toContainText("0.8");
  const runId = await page.locator(".world-title small").textContent();
  expect(runId).toBeTruthy();
});

test("batch confirmations are atomic and invalid draft preserves all stored domains", async ({
  page,
}) => {
  const run = await connect(page),
    endpoint = `/api/test/v1/runs/${run.test_run_id}/state`,
    headers = { Authorization: "Bearer e2e-admin" };
  await page.getByLabel("饥饿程度", { exact: true }).fill("0.77");
  await page.getByRole("tab", { name: "身体状态", exact: true }).click();
  await page.getByLabel("可移动", { exact: true }).uncheck();
  await page
    .getByRole("button", { name: "预览多面板原子提交", exact: true })
    .click();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(page.getByTestId("report-result")).toContainText("accepted");
  const stored = await (await page.request.get(endpoint, { headers })).json();
  expect(stored.revision).toBe(1);
  expect(stored.domain_states.needs["npc-bigfish"].data.hunger).toBe(0.77);
  expect(stored.domain_states.body["npc-bigfish"].data.can_move).toBe(false);
  await page.getByLabel("清醒", { exact: true }).uncheck();
  await page.getByRole("tab", { name: "身体与需求", exact: true }).click();
  await page.getByLabel("饥饿程度", { exact: true }).fill("9");
  await page
    .getByRole("button", { name: "预览多面板原子提交", exact: true })
    .click();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(page.getByTestId("report-result")).toContainText("rejected");
  const unchanged = await (
    await page.request.get(endpoint, { headers })
  ).json();
  expect(unchanged.revision).toBe(1);
  expect(unchanged.domain_states.body["npc-bigfish"].data.awake).toBe(true);
});

test("world social activity environment resources groups production and events forms commit real values", async ({
  page,
}) => {
  const run = await connect(page);
  const submit = async (name: string) => {
    await page
      .getByRole("button", { name: `提交${name}`, exact: true })
      .click();
    await page.getByRole("button", { name: "确认提交", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  };
  await page.getByRole("tab", { name: "世界", exact: true }).click();
  await page.getByLabel("模拟 tick", { exact: true }).fill("5");
  await submit("世界");
  await page.getByRole("tab", { name: "关系与性格", exact: true }).click();
  await page.getByLabel("关系", { exact: true }).selectOption("friend");
  await submit("关系与性格");
  await page.getByRole("tab", { name: "任务与行动", exact: true }).click();
  await page.getByLabel("阶段", { exact: true }).selectOption("moving");
  await submit("任务与行动");
  await page.getByRole("tab", { name: "环境", exact: true }).click();
  await page.getByLabel("天气", { exact: true }).selectOption("rain");
  await submit("环境");
  await page.getByRole("tab", { name: "资源与物品", exact: true }).click();
  await page.getByRole("button", { name: "添加物品", exact: true }).click();
  await page.getByLabel("物品 ID", { exact: true }).fill("berry-bag");
  await page.getByRole("button", { name: "设置数量", exact: true }).click();
  await page.getByLabel("数量", { exact: true }).fill("3");
  await submit("资源与物品");
  await page.getByRole("tab", { name: "群体", exact: true }).click();
  await page.getByRole("button", { name: "添加群体", exact: true }).click();
  await page.getByLabel("群体 ID", { exact: true }).fill("beach-team");
  await submit("群体");
  await page.getByRole("tab", { name: "生产", exact: true }).click();
  await page.getByRole("button", { name: "添加设施", exact: true }).click();
  await page.getByLabel("设施 ID", { exact: true }).fill("campfire");
  await submit("生产");
  await page.getByRole("tab", { name: "事件与知识", exact: true }).click();
  await page.getByRole("button", { name: "添加事件", exact: true }).click();
  await page.getByLabel("事件 ID", { exact: true }).fill("beach-rain");
  await page.getByLabel("事实 / 传闻", { exact: true }).fill("海滩下雨了。");
  await submit("事件与知识");
  const state = await (
    await page.request.get(`/api/test/v1/runs/${run.test_run_id}/state`, {
      headers: { Authorization: "Bearer e2e-admin" },
    })
  ).json();
  expect(state.revision).toBe(8);
  expect(
    state.domain_states.social["npc-bigfish"].data.opinions[0].relationship,
  ).toBe("friend");
  expect(
    state.domain_states.resources[run.world_id].data.items[0].quantity,
  ).toBe(3);
  expect(state.events["beach-rain"].fact).toBe("海滩下雨了。");
});

test("group chat defaults three members and delivers free text through real API", async ({
  page,
}) => {
  await connect(page);
  await page.getByRole("link", { name: "会话 2+" }).click();
  await expect(page.locator(".member-options input:checked")).toHaveCount(3);
  await page.getByRole("button", { name: "创建会话", exact: true }).click();
  await page.getByLabel("聊天内容").fill("海风有柠檬味，我想沿着海岸走。");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.locator(".message")).toHaveCount(3);
  await expect(page.locator(".message-text").first()).toHaveText(
    "海风有柠檬味，我想沿着海岸走。",
  );
  await expect(page.locator(".message-meta").first()).toContainText(
    "大肥鱼、克劳德",
  );
  await expect(page.getByLabel("聊天内容")).toHaveValue("");
});

test("prologue is nonblank interactive and accepts free dialogue", async ({
  page,
}) => {
  page.on("pageerror", (error) => console.log("BROWSER ERROR", error.stack));
  await page.goto("/prologue");
  await page.getByRole("button", { name: "醒来", exact: true }).click();
  await expect(page.locator(".quest-hud")).toContainText("大肥鱼");
  await page.getByRole("button", { name: "与大肥鱼交谈" }).click();
  await page
    .getByLabel("序章对话", { exact: true })
    .fill("我想先看看这片海岸，不走预设选项。");
  await page.getByRole("button", { name: "发送序章对话" }).click();
  await expect(page.locator(".last-player-message")).toContainText(
    "不走预设选项",
  );
  await expect(page.locator(".quest-hud")).toContainText("收集海滩上的材料");
  await page.getByRole("button", { name: "结束对话" }).click();
  await page.getByRole("button", { name: "背包", exact: true }).click();
  await expect(page.getByTestId("inventory-berry")).toHaveText("0");
  const pixels = await page
    .locator("canvas")
    .evaluate((canvas: HTMLCanvasElement) => {
      const c = canvas.getContext("2d")!;
      const data = c.getImageData(0, 0, canvas.width, canvas.height).data;
      const colors = new Set<string>();
      for (let i = 0; i < data.length; i += 100)
        colors.add(`${data[i]}-${data[i + 1]}-${data[i + 2]}`);
      return colors.size;
    });
  expect(pixels).toBeGreaterThan(30);
});

test("draft remains isolated per NPC and version conflict preserves edits", async ({
  page,
  context,
}) => {
  const run = await connect(page);
  await page.getByLabel("饥饿程度", { exact: true }).fill("0.72");
  await page.getByLabel("当前 NPC").selectOption("npc-claude");
  await expect(page.getByLabel("饥饿程度", { exact: true })).toHaveValue(
    "0.35",
  );
  await page.getByLabel("当前 NPC").selectOption("npc-bigfish");
  await expect(page.getByLabel("饥饿程度", { exact: true })).toHaveValue(
    "0.72",
  );
  const second = await context.newPage();
  await second.goto("/testbench");
  await second.getByLabel("测试凭据").fill("e2e-admin");
  await second
    .getByRole("button", { name: "连接测试服务", exact: true })
    .click();
  await second.getByLabel("已有 run ID").fill(run.test_run_id);
  await second
    .getByRole("button", { name: "载入测试世界", exact: true })
    .click();
  await expect(second.getByTestId("run-revision")).toContainText("0");
  await second.getByLabel("饥饿程度", { exact: true }).fill("0.91");
  await page
    .getByRole("button", { name: "提交身体与需求", exact: true })
    .click();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(page.getByTestId("report-result")).toContainText("accepted");
  await second
    .getByRole("button", { name: "提交身体与需求", exact: true })
    .click();
  await second.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(second.getByTestId("report-result")).toContainText("conflict");
  await second.getByRole("button", { name: "取消", exact: true }).click();
  await expect(second.getByLabel("饥饿程度", { exact: true })).toHaveValue(
    "0.91",
  );
  await second.getByRole("button", { name: "保留草稿并读取新基线" }).click();
  await expect(second.getByTestId("needs-confirmed")).toContainText("0.72");
  await expect(second.getByLabel("饥饿程度", { exact: true })).toHaveValue(
    "0.91",
  );
});

test("group chat composition and read-only observer membership", async ({
  page,
}) => {
  await connect(page);
  await page.getByRole("link", { name: "会话 2+" }).click();
  await page
    .locator(".member-options")
    .getByText("沈理", { exact: true })
    .click();
  await page.getByRole("button", { name: "创建会话", exact: true }).click();
  await expect(page.getByText("旁观中 · 仅查看历史")).toBeVisible();
  await expect(page.getByLabel("聊天内容")).toHaveCount(0);
  await page.getByRole("button", { name: "加入会话", exact: true }).click();
  const input = page.getByLabel("聊天内容");
  await input.fill("中文组合输入");
  await input.dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true,
    keyCode: 229,
  });
  await expect(page.locator(".message")).toHaveCount(0);
  await expect(input).toHaveValue("中文组合输入");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.locator(".message")).toHaveCount(3);
  await page.getByLabel("会话成员 克劳德").click();
  await expect(page.getByLabel("会话成员 克劳德")).not.toBeChecked();
  await page.getByLabel("会话成员 大肥鱼").click();
  await expect(page.getByLabel("会话成员 大肥鱼")).not.toBeChecked();
  await expect(page.locator(".chat-mode")).toContainText("已暂停");
});

test("lost dialogue response retries once after background ticks", async ({
  page,
}) => {
  await page.goto("/prologue");
  await page.getByRole("button", { name: "醒来", exact: true }).click();
  await page.getByRole("button", { name: "与大肥鱼交谈" }).click();
  const input = page.getByLabel("序章对话", { exact: true });
  await input.fill("这条消息只能送达一次。");
  let lost = false;
  await page.route("**/api/play/v1/agent-turn", async (route) => {
    if (!lost) {
      lost = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.getByRole("button", { name: "发送序章对话", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "发送序章对话", exact: true }).click();
  await expect(input).toHaveValue("");
  const state = await (await page.request.get("/api/play/v1/state")).json();
  expect(state.messages).toHaveLength(2);
});

test("visible follow speech starts timeout through delivery API", async ({
  page,
}) => {
  await page.goto("/prologue");
  await page.getByRole("button", { name: "醒来", exact: true }).click();
  await page.getByRole("button", { name: "与大肥鱼交谈" }).click();
  await page.getByLabel("序章对话", { exact: true }).fill("一起走吧");
  await page.getByRole("button", { name: "发送序章对话", exact: true }).click();
  await expect(page.locator(".quest-hud")).toContainText("收集");
  await page.getByRole("button", { name: "结束对话", exact: true }).click();
  await page.getByRole("button", { name: "邀请跟随", exact: true }).click();
  await expect(page.locator(".follow-reply")).toBeVisible({ timeout: 20000 });
  await expect
    .poll(
      async () => {
        const state = await (
          await page.request.get("/api/play/v1/state")
        ).json();
        return state.actors["npc-bigfish"].speech?.delivered_at;
      },
      { timeout: 6000 },
    )
    .toEqual(expect.any(Number));
  let lost = false;
  const ids: string[] = [];
  await page.route("**/api/play/v1/command", async (route) => {
    const body = route.request().postDataJSON();
    if (body.kind === "reply") {
      ids.push(body.command_id);
      if (!lost) {
        lost = true;
        await route.fetch();
        await route.abort("failed");
        return;
      }
    }
    await route.continue();
  });
  await page
    .getByLabel("随行回复", { exact: true })
    .fill("我听见了，这条回复只发一次。");
  await page.getByRole("button", { name: "发送随行回复", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "发送随行回复", exact: true }).click();
  await expect(page.locator(".follow-reply")).toHaveCount(0);
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
  const final = await (await page.request.get("/api/play/v1/state")).json();
  expect(
    final.messages.filter(
      (m: any) => m.text === "我听见了，这条回复只发一次。",
    ),
  ).toHaveLength(1);
});

test("lost movement response has an exact command retry", async ({ page }) => {
  await page.goto("/prologue");
  await page.getByRole("button", { name: "醒来", exact: true }).click();
  const ids: string[] = [];
  await page.route("**/api/play/v1/command", async (route) => {
    const body = route.request().postDataJSON();
    if (body.kind === "walk_to") {
      ids.push(body.command_id);
      if (ids.length === 1) {
        await route.fetch();
        await route.abort("failed");
        return;
      }
    }
    await route.continue();
  });
  const canvas = page.locator("canvas"),
    box = (await canvas.boundingBox())!;
  await canvas.click({
    position: { x: (box.width * 600) / 1408, y: (box.height * 400) / 800 },
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await page
    .getByRole("button", { name: "重试未确认操作", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
  await expect
    .poll(async () => {
      const state = await (await page.request.get("/api/play/v1/state")).json();
      return state.actors.player.x;
    })
    .toBeLessThan(690);
});

test("visibility trace and missing records use management and filtered APIs", async ({
  page,
}) => {
  const run = await connect(page),
    base = `/api/test/v1/runs/${run.test_run_id}`;
  const response = await page.request.post(base + "/reports", {
    headers: { Authorization: "Bearer e2e-admin" },
    data: {
      schema_version: 1,
      report_id: crypto.randomUUID().replaceAll("-", ""),
      request_id: "fixture",
      world_id: run.world_id,
      run_epoch: run.run_epoch,
      source_kind: "test",
      source_id: run.test_run_id,
      domain: "events",
      entity_id: run.world_id,
      sequence: 1,
      expected_revision: 0,
      mode: "snapshot",
      occurred_at_tick: 0,
      observed_at_tick: 0,
      payload: {
        events: [
          {
            event_id: "secret-shell",
            fact: "只有大肥鱼知道的贝壳",
            observers: ["npc-bigfish"],
          },
        ],
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const report = await response.json();
  await page.getByRole("button", { name: "刷新确认状态", exact: true }).click();
  await page.getByRole("button", { name: "刷新上下文", exact: true }).click();
  await expect(page.getByTestId("context-preview")).toContainText(
    "只有大肥鱼知道的贝壳",
  );
  await page.getByLabel("当前 NPC").selectOption("npc-claude");
  const contextResponse = page.waitForResponse((r) =>
    r.url().endsWith("/npcs/npc-claude/context"),
  );
  await page.getByRole("button", { name: "刷新上下文", exact: true }).click();
  expect(JSON.stringify(await (await contextResponse).json())).not.toContain(
    "secret-shell",
  );
  await expect(page.getByTestId("context-preview")).not.toContainText(
    "只有大肥鱼知道的贝壳",
  );
  await page.getByLabel("链路 request ID").fill(report.request_id);
  await page.getByRole("button", { name: "查询链路", exact: true }).click();
  await expect(page.locator(".timeline")).toContainText("report_commit");
  await page.getByLabel("链路 request ID").fill("missing-record");
  await page.getByRole("button", { name: "查询链路", exact: true }).click();
  await expect(page.locator(".timeline")).toContainText("无记录或记录已裁剪");
});

test("scenario imports baseline and replays one confirmed step at a time", async ({
  page,
}) => {
  await connect(page);
  await page.getByRole("link", { name: "场景与重放", exact: true }).click();
  await page
    .locator("input[type=file]")
    .setInputFiles(path.resolve("../configs/test_scenarios/baseline.json"));
  await expect(page.locator(".saved-scenarios")).toContainText(
    "beach-needs-baseline",
  );
  await page.getByRole("button", { name: "准备逐步重放", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeEnabled();
  for (let i = 1; i <= 3; i++) {
    await page.getByRole("button", { name: "下一步", exact: true }).click();
    await expect(page.locator(".editor-pane")).toContainText(
      `"completed_steps": ${i}`,
    );
  }
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  const scenario = JSON.parse(
    await readFile(
      path.resolve("../configs/test_scenarios/baseline.json"),
      "utf8",
    ),
  );
  scenario.name = "another-scenario";
  scenario.steps = scenario.steps.slice(0, 1);
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "another.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(scenario)),
    });
  await expect(
    page.getByRole("button", { name: "准备逐步重放", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "准备逐步重放", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(page.locator(".editor-pane")).toContainText(
    '"completed_steps": 1',
  );
  await page.getByRole("button", { name: "重新逐步重放", exact: true }).click();
  await expect(page.locator(".editor-pane")).toContainText(
    '"completed_steps": 0',
  );
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeEnabled();
});

test("beach complete gathering uses canvas navigation and authoritative inventory", async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.goto("/prologue");
  await page.getByRole("button", { name: "醒来", exact: true }).click();
  await page.getByRole("button", { name: "与大肥鱼交谈" }).click();
  await page.getByLabel("序章对话", { exact: true }).fill("我来收集一些材料。");
  await page.getByRole("button", { name: "发送序章对话", exact: true }).click();
  await expect(page.locator(".quest-hud")).toContainText("收集");
  await page.getByRole("button", { name: "结束对话", exact: true }).click();
  await expect(page.getByLabel("序章对话", { exact: true })).toHaveCount(0);
  for (const [target, x, y, label] of [
    ["berry-01", 416, 304, "采集浆果"],
    ["wood-01", 256, 464, "采集漂流木"],
    ["wood-02", 1088, 496, "采集漂流木"],
  ] as const) {
    const canvas = page.locator("canvas"),
      box = (await canvas.boundingBox())!;
    const walking = page.waitForRequest(
      (r) =>
        r.url().endsWith("/api/play/v1/command") &&
        r.postDataJSON()?.kind === "walk_to",
    );
    await canvas.click({
      position: { x: (x / 1408) * box.width, y: (y / 800) * box.height },
    });
    const point = (await walking).postDataJSON();
    expect(point.x).toBeCloseTo(x, -1);
    expect(point.y).toBeCloseTo(y, -1);
    await expect
      .poll(
        async () => {
          const s = await (await page.request.get("/api/play/v1/state")).json();
          const p = s.actors.player;
          return Math.hypot(p.x - x, p.y - y);
        },
        { timeout: 25000 },
      )
      .toBeLessThan(32);
    await page.getByRole("button", { name: new RegExp(label + "$") }).click();
    await expect
      .poll(async () => {
        const s = await (await page.request.get("/api/play/v1/state")).json();
        return s.objects[target].remaining;
      })
      .toBe(0);
  }
  await expect(page.locator(".quest-hud")).toContainText("第一份收获");
  await page.getByRole("button", { name: "背包", exact: true }).click();
  await expect(page.getByTestId("inventory-berry")).toHaveText("3");
  await expect(page.getByTestId("inventory-wood")).toHaveText("2");
  const state = await (await page.request.get("/api/play/v1/state")).json();
  const stored = await (
    await page.request.get(`/api/test/v1/runs/${state.test_run_id}/state`, {
      headers: { Authorization: "Bearer e2e-admin" },
    })
  ).json();
  expect(stored.prologue.inventory).toEqual(state.inventory);
  expect(
    stored.domain_states.resources[stored.world_id].data.items.find(
      (i: any) => i.item_id === "bag-wood",
    ).quantity,
  ).toBe(2);
});

for (const [width, height] of [
  [1440, 900],
  [1024, 768],
  [390, 844],
]) {
  test(`visual layout ${width} desktop mobile evidence`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const directory = path.resolve("../runtime/e2e/screenshots");
    await mkdir(directory, { recursive: true });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await connect(page);
    await page.screenshot({
      path: path.join(directory, `testbench-${width}.png`),
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page
      .getByRole("button", { name: "提交身体与需求", exact: true })
      .click();
    await page.screenshot({ path: path.join(directory, `diff-${width}.png`) });
    await page.getByRole("button", { name: "取消", exact: true }).click();
    await page.getByRole("link", { name: "会话 2+" }).click();
    await page.getByRole("button", { name: "创建会话", exact: true }).click();
    await page.getByLabel("聊天内容").fill("先在海滩歇一会儿吧。");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await expect(page.locator(".message")).toHaveCount(3);
    await page.screenshot({
      path: path.join(directory, `conversation-${width}.png`),
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.getByRole("link", { name: "海滩序章", exact: true }).click();
    await page.getByRole("button", { name: "醒来", exact: true }).click();
    await page.getByRole("button", { name: "暂停", exact: true }).click();
    await page.screenshot({ path: path.join(directory, `beach-${width}.png`) });
    await page.getByRole("button", { name: "与大肥鱼交谈" }).click();
    await expect(page.getByLabel("序章对话", { exact: true })).toBeVisible();
    await page.screenshot({
      path: path.join(directory, `dialogue-${width}.png`),
    });
    await page.getByRole("button", { name: "结束对话", exact: true }).click();
    await page.getByRole("button", { name: "场景调试", exact: true }).click();
    await expect(page.getByLabel("NPC 模板")).toBeVisible();
    await page.screenshot({ path: path.join(directory, `debug-${width}.png`) });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    expect(errors).toEqual([]);
  });
}
