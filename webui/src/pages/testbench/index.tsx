import { useEffect, useRef, useState } from "react";
import { Dialog } from "radix-ui";
import {
  Download,
  Upload,
  RefreshCw,
  RotateCcw,
  Play,
  Save,
  Plus,
  X,
  Send,
  Activity,
  Globe,
  ChevronRight,
} from "lucide-react";
import { client, id, command, ApiError } from "../../api/client";
import { report, type World } from "../../api/testControl";
import { names, type TestRun } from "../../hooks/useTestRun";
import {
  DomainEditor,
  domainNames,
} from "../../components/testbench/DomainEditor";
import { PanelSplitter } from "../../components/observe/PanelSplitter";
import { JsonViewer } from "../../components/observe/JsonViewer";
import { TraceTimeline } from "../../components/observe/TraceTimeline";
import { ConversationChat } from "./ConversationChat";

type Draft = { data: any; revision: number; baseline: any };
const defaults: Record<string, any> = {
  needs: { hunger: 0.35, fatigue: 0.2, rest: 0.7, mood: 0.65 },
  body: { present: true, awake: true, can_move: true, can_speak: true },
  world: { tick: 0, speed: 1, pause_reasons: [], scene: "beach" },
  social: {
    opinions: [{ target_id: "npc-claude", value: 0, relationship: "stranger" }],
  },
  activity: { phase: "idle", progress: 0 },
  environment: { weather: "clear", temperature_c: 26 },
  resources: { items: [] },
  groups: { groups: [] },
  production: { orders: [], facilities: [], crops: [] },
  events: { events: [] },
};
export function Testbench({
  lab,
  section,
  setSection,
}: {
  lab: TestRun;
  section: string;
  setSection: (s: string) => void;
}) {
  const [schemas, setSchemas] = useState<any>({});
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [context, setContext] = useState<any>(null);
  const [trace, setTrace] = useState<any>(null);
  const [traceId, setTraceId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [pending, setPending] = useState<any[] | null>(null);
  const [width, setWidth] = useState(350);
  const [mobileTab, setMobileTab] = useState("编辑");
  const [scenario, setScenario] = useState<any>(null);
  const [scenarioResult, setScenarioResult] = useState<any>(null);
  const contextRequest = useRef(0);
  const activeIdentity = useRef("");
  const pendingBatch = useRef("");
  const [runId, setRunId] = useState("");
  const run = lab.run;
  const entity =
    schemas[section]?.entity === "npc" ? lab.npc : run?.world_id || "";
  const key = run
    ? `${run.test_run_id}/${run.run_epoch}/${entity}/${section}`
    : "";
  activeIdentity.current = key;
  const confirmed = run?.domain_states[section]?.[entity]?.data || {};
  const draft = drafts[key] || {
    data: Object.keys(confirmed).length ? confirmed : defaults[section] || {},
    revision: run?.revision || 0,
    baseline: confirmed,
  };
  useEffect(() => {
    let active = true;
    if (lab.connected)
      void client
        .get("/api/test/v1/runs/schema")
        .then((value) => {
          if (active) setSchemas(value);
        })
        .catch((e) => {
          if (active) lab.setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [lab.connected]);
  useEffect(() => {
    contextRequest.current++;
    setContext(null);
  }, [run?.run_epoch, lab.npc]);
  const change = (data: any) =>
    setDrafts((prev) => ({ ...prev, [key]: { ...draft, data } }));
  async function refreshContext() {
    if (!run) return;
    const token = ++contextRequest.current;
    const value = await client.get(lab.base + `/npcs/${lab.npc}/context`);
    if (token === contextRequest.current) setContext(value);
  }
  async function observe(requestId: string) {
    setTraceId(requestId);
    void client
      .get("/api/v1/observe/status")
      .then(lab.setStatus)
      .catch(() => {});
    try {
      setTrace(await client.get(`/api/v1/observe/requests/${requestId}`));
    } catch (e) {
      setTrace({
        reason:
          e instanceof ApiError && e.status === 404
            ? "no_record_or_trimmed"
            : "unavailable",
        stages: [],
      });
    }
  }
  function prepare(batch = false) {
    if (!run) return;
    pendingBatch.current = id();
    const items = batch
      ? Object.entries(drafts)
          .filter(([k]) => k.startsWith(`${run.test_run_id}/${run.run_epoch}/`))
          .map(([k, d]) => {
            const parts = k.split("/");
            return report(run, parts[3], parts[2], d.data, d.revision);
          })
      : [report(run, section, entity, draft.data, draft.revision)];
    setPending(items);
  }
  async function submit() {
    if (!pending || !run) return;
    const requestKey = key;
    const outgoing = pending;
    await lab.attempt(async () => {
      try {
        const response =
          outgoing.length === 1
            ? await client.post(lab.base + "/reports", outgoing[0])
            : await client.post(lab.base + "/reports/batch", {
                batch_id: pendingBatch.current,
                expected_revision: outgoing[0].expected_revision,
                reports: outgoing,
              });
        setResult(response);
        await observe(response.request_id);
        if (response.status === "accepted" || response.status === "duplicate") {
          await lab.refresh();
          setDrafts((prev) => {
            const next = { ...prev };
            for (const item of outgoing)
              delete next[
                `${run.test_run_id}/${run.run_epoch}/${item.entity_id}/${item.domain}`
              ];
            return next;
          });
          if (activeIdentity.current === requestKey) setPending(null);
        }
      } catch (e) {
        if (e instanceof ApiError) {
          setResult({
            status: e.status === 409 ? "conflict" : "rejected",
            reason: e.detail,
            request_id: e.requestId,
          });
          await observe(e.requestId);
        }
        throw e;
      }
    });
  }
  async function rebase() {
    const latest = await lab.refresh();
    if (!latest) return;
    setDrafts((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([k, d]) => {
          const parts = k.split("/");
          if (parts[0] !== latest.test_run_id || parts[1] !== latest.run_epoch)
            return [k, d];
          return [
            k,
            {
              ...d,
              revision: latest.revision,
              baseline: latest.domain_states[parts[3]]?.[parts[2]]?.data || {},
            },
          ];
        }),
      ),
    );
    setPending(null);
    setResult(null);
    lab.setError("");
  }
  function download(data: any, filename: string) {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function exportScenario() {
    if (run) {
      const data = await client.post(lab.base + "/scenario/export");
      setScenario(data);
      download(data, "bigfish-scenario.json");
    }
  }
  async function loadScenario(file: File) {
    if (file.size > 1_000_000) throw new Error("场景文件超过 1 MB");
    const data = JSON.parse(await file.text());
    const normalized = await client.post(lab.base + "/scenario/import", data);
    setScenario(normalized);
    await lab.refresh();
  }
  async function replay() {
    if (!scenario) return;
    const response = await client.post(lab.base + "/replay", scenario);
    setScenarioResult(response);
    await lab.select(response.test_run_id);
  }
  const replayPending = useRef<any>(null);
  const selectedReplay =
    !!scenario &&
    JSON.stringify(scenario) === JSON.stringify(run?.scenario_replay?.scenario);
  async function stepReplay(restart = false) {
    if (!run || !scenario) return;
    if (restart || !selectedReplay) {
      const result = await client.post(lab.base + "/replay/start", scenario);
      setScenarioResult(result);
      await lab.select(result.test_run_id);
      return;
    }
    replayPending.current ||= command(run);
    const result = await client.post(
      lab.base + "/replay/step",
      replayPending.current,
    );
    replayPending.current = null;
    setScenarioResult(result);
    await lab.refresh();
  }
  useEffect(() => {
    replayPending.current = null;
  }, [run?.run_epoch, scenario]);
  useEffect(() => {
    setScenarioResult(null);
  }, [scenario]);
  return (
    <div className="workbench">
      <header className="workbench-toolbar">
        <div className="world-title">
          <Globe size={18} />
          <div>
            <strong>{run?.name || "尚未选择测试世界"}</strong>
            <small>{run ? run.test_run_id.slice(0, 12) : "隔离测试环境"}</small>
          </div>
        </div>
        <div className="run-actions">
          <input
            aria-label="已有 run ID"
            placeholder="run ID"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
          />
          <button
            className="icon"
            title="载入测试世界"
            aria-label="载入测试世界"
            disabled={!runId || lab.busy}
            onClick={() => lab.select(runId)}
          >
            <Upload size={16} />
          </button>
          <button disabled={!lab.connected || lab.busy} onClick={lab.create}>
            <Plus size={15} />
            新建测试世界
          </button>
        </div>
      </header>
      <div className="run-meta">
        <label>
          当前 NPC{" "}
          <select
            aria-label="当前 NPC"
            value={lab.npc}
            onChange={(e) => lab.setNpc(e.target.value)}
          >
            {(run?.npc_ids || ["npc-bigfish", "npc-claude"]).map((n) => (
              <option key={n} value={n}>
                {names[n] || n}
              </option>
            ))}
          </select>
        </label>
        <span>
          代次 <code>{run?.run_epoch.slice(0, 8) || "—"}</code>
        </span>
        <span data-testid="run-revision">
          revision <b>{run?.revision ?? "—"}</b>
        </span>
        <span className="badge">{lab.connected ? "后端已连接" : "未连接"}</span>
        <button
          className="icon"
          title="刷新确认状态"
          aria-label="刷新确认状态"
          disabled={!run || lab.busy}
          onClick={() => lab.attempt(lab.refresh)}
        >
          <RefreshCw size={15} />
        </button>
      </div>
      {section === "conversation" ? (
        <ConversationChat lab={lab} />
      ) : (
        <>
          <div className="mobile-tabs">
            {["编辑", "上下文", "链路"].map((t) => (
              <button
                key={t}
                className={mobileTab === t ? "active" : ""}
                onClick={() => setMobileTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div
            className="workspace-body"
            style={{ "--inspector-width": `${width}px` } as React.CSSProperties}
          >
            <section
              className={`editor-pane mobile-${mobileTab === "编辑" ? "show" : "hide"}`}
            >
              <div className="domain-tabs" role="tablist">
                {Object.keys(schemas)
                  .filter((d) => d !== "conversation")
                  .map((d) => (
                    <button
                      role="tab"
                      aria-selected={section === d}
                      className={section === d ? "active" : ""}
                      key={d}
                      onClick={() => setSection(d)}
                    >
                      {domainNames[d]}
                    </button>
                  ))}
              </div>
              {!run ? (
                <div className="empty">
                  <Globe size={32} />
                  <h2>准备一个测试世界</h2>
                  <p>从新建世界开始，所有上报保存在隔离的 run 中。</p>
                </div>
              ) : section === "scenarios" ? (
                <>
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">SCENARIOS / REPLAY</span>
                      <h2>场景与重放</h2>
                    </div>
                  </div>
                  <div className="scenario-controls">
                    <button onClick={() => lab.attempt(exportScenario)}>
                      <Download size={16} />
                      导出场景
                    </button>
                    <label className="file-button">
                      <Upload size={16} />
                      导入场景
                      <input
                        type="file"
                        accept="application/json"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) void lab.attempt(() => loadScenario(f));
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <button
                      disabled={lab.busy}
                      onClick={() => setPending([{ reset: true }])}
                    >
                      <RotateCcw size={16} />
                      重置世界
                    </button>
                    <button
                      disabled={!scenario || lab.busy}
                      onClick={() => lab.attempt(replay)}
                    >
                      <Play size={16} />
                      顺序重放
                    </button>
                    <button
                      disabled={
                        !scenario ||
                        lab.busy ||
                        (selectedReplay &&
                          run.scenario_replay.cursor ===
                            run.scenario_replay.scenario.steps.length)
                      }
                      onClick={() => lab.attempt(() => stepReplay())}
                    >
                      <ChevronRight size={16} />
                      {selectedReplay ? "下一步" : "准备逐步重放"}
                    </button>
                    {selectedReplay && (
                      <button
                        disabled={lab.busy}
                        onClick={() => lab.attempt(() => stepReplay(true))}
                      >
                        <RotateCcw size={16} />
                        重新逐步重放
                      </button>
                    )}
                  </div>
                  <div className="saved-scenarios">
                    {Object.entries(run.saved_scenarios).map(([name, s]) => (
                      <button key={name} onClick={() => setScenario(s)}>
                        <Save size={16} />
                        {name}
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                  <JsonViewer value={scenario || { status: "没有载入场景" }} />
                  {scenarioResult && <JsonViewer value={scenarioResult} />}
                </>
              ) : schemas[section] && !schemas[section].supported ? (
                <div className="empty">
                  <Activity size={30} />
                  <h2>{domainNames[section]}</h2>
                  <span className="badge neutral">unsupported</span>
                  <button disabled>提交</button>
                </div>
              ) : schemas[section] ? (
                <DomainEditor
                  domain={section}
                  schema={schemas[section].schema}
                  draft={draft.data}
                  confirmed={confirmed}
                  busy={lab.busy}
                  onChange={change}
                  onRestore={() =>
                    setDrafts((prev) => ({
                      ...prev,
                      [key]: {
                        data: confirmed,
                        baseline: confirmed,
                        revision: run.revision,
                      },
                    }))
                  }
                  onSubmit={() => prepare()}
                />
              ) : (
                <div className="empty">加载领域定义…</div>
              )}
              {run &&
                Object.keys(drafts).some((k) =>
                  k.startsWith(`${run.test_run_id}/${run.run_epoch}/`),
                ) && (
                  <button
                    className="batch-submit"
                    disabled={lab.busy}
                    onClick={() => prepare(true)}
                  >
                    <Send size={15} />
                    预览多面板原子提交
                  </button>
                )}
              {result && (
                <div
                  data-testid="report-result"
                  className={`report-result ${result.status}`}
                >
                  <strong>{result.status}</strong>
                  <span>{result.reason}</span>
                  <button
                    className="text-button"
                    onClick={() => observe(result.request_id)}
                  >
                    查看请求链路
                  </button>
                  {result.status === "conflict" && (
                    <button onClick={() => lab.attempt(rebase)}>
                      保留草稿并读取新基线
                    </button>
                  )}
                  <code>{result.request_id?.slice(0, 16)}</code>
                </div>
              )}
            </section>
            <PanelSplitter value={width} onChange={setWidth} />
            <aside
              className={`inspector mobile-${mobileTab !== "编辑" ? "show" : "hide"}`}
            >
              <div
                className={`context-section mobile-${mobileTab === "上下文" ? "show" : "hide"}`}
              >
                <div className="side-title">
                  <h3>NPC 可见上下文</h3>
                  <button
                    className="icon"
                    title="刷新上下文"
                    aria-label="刷新上下文"
                    disabled={!run || lab.busy}
                    onClick={() => lab.attempt(refreshContext)}
                  >
                    <RefreshCw size={15} />
                  </button>
                </div>
                <div className="context-status">
                  <span className="badge">{names[lab.npc] || lab.npc}</span>
                  <small>
                    {context
                      ? context.revision === run?.revision
                        ? "当前版本"
                        : "上下文已过期"
                      : "尚未读取"}
                  </small>
                </div>
                <div data-testid="context-preview">
                  {context ? (
                    <JsonViewer value={context} />
                  ) : (
                    <div className="empty compact">unknown · 等待读取</div>
                  )}
                </div>
              </div>
              <div
                className={`trace-section mobile-${mobileTab === "链路" ? "show" : "hide"}`}
              >
                <div className="side-title">
                  <h3>阶段时间线</h3>
                  <span className="badge neutral">本地</span>
                </div>
                <div className="export-status">
                  {lab.status?.export?.last_error || lab.status?.export_errors
                    ? "导出异常 · 本地记录可用"
                    : "Collector 状态以服务端观测为准"}
                </div>
                <div className="trace-query">
                  <input
                    aria-label="链路 request ID"
                    value={traceId}
                    onChange={(e) => setTraceId(e.target.value)}
                  />
                  <button
                    className="icon"
                    title="查询链路"
                    aria-label="查询链路"
                    disabled={!traceId || lab.busy}
                    onClick={() => observe(traceId)}
                  >
                    <RefreshCw size={15} />
                  </button>
                </div>
                <TraceTimeline trace={trace} />
              </div>
            </aside>
          </div>
        </>
      )}
      <Dialog.Root
        open={!!pending}
        onOpenChange={(open) => {
          if (!open && !lab.busy) setPending(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="modal-overlay" />
          <Dialog.Content className="modal">
            <div className="modal-heading">
              <Dialog.Title>
                {pending?.[0]?.reset ? "重置测试世界" : "确认提交差异"}
              </Dialog.Title>
              <Dialog.Close
                className="icon"
                disabled={lab.busy}
                aria-label="关闭"
              >
                <X size={18} />
              </Dialog.Close>
            </div>
            <Dialog.Description>
              {pending?.[0]?.reset
                ? "创建新代次并清空当前状态。旧请求将失效。"
                : `基线 revision ${pending?.[0]?.expected_revision ?? "—"} → 服务端确认后生效`}
            </Dialog.Description>
            {!pending?.[0]?.reset && (
              <>
                <div className="diff-legend">
                  <span>当前确认值</span>
                  <span>待提交草稿</span>
                </div>
                <div className="diff-columns">
                  <pre>{JSON.stringify(confirmed, null, 2)}</pre>
                  <pre>
                    {JSON.stringify(
                      pending?.map((p) => ({
                        domain: p.domain,
                        payload: p.payload,
                      })),
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </>
            )}
            {lab.error && <div className="inline-error">{lab.error}</div>}
            <div className="modal-actions">
              <button disabled={lab.busy} onClick={() => setPending(null)}>
                取消
              </button>
              <button
                className="primary"
                disabled={lab.busy}
                onClick={() =>
                  pending?.[0]?.reset
                    ? lab.attempt(async () => {
                        const next = await client.post<World>(
                          lab.base + "/reset",
                          command(run!),
                        );
                        lab.setRun(next);
                        setPending(null);
                        setContext(null);
                      })
                    : submit()
                }
              >
                {lab.busy ? "提交中…" : "确认提交"}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
