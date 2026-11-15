import { useEffect, useRef, useState } from "react";
import Phaser from "phaser";
import {
  Backpack,
  Bug,
  ChevronRight,
  MessageSquare,
  Pause,
  Play,
  RotateCcw,
  Send,
  X,
  Footprints,
  Hand,
  Plus,
  Trash2,
  Save,
  Upload,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { client, command, id, ApiError } from "../../api/client";
import type { TestRun } from "../../hooks/useTestRun";
import { JsonViewer } from "../../components/observe/JsonViewer";
import { BeachScene } from "./BeachScene";
import type { BeachState } from "./types";
import "./prologue.css";

const itemNames: Record<string, string> = {
  berry: "浆果",
  wood: "漂流木",
  shell: "贝壳",
  crate: "漂流箱",
  sign: "路牌",
};
const errors: Record<string, string> = {
  out_of_range: "离目标太远了，请走近一些。",
  blocked_interaction: "中间有障碍，换个位置试试。",
  unreachable: "这里无法到达。",
  encounter_required: "先与大肥鱼交谈。",
  depleted: "这里已经采集过了。",
  stale_speech: "这段随行对话已经结束。",
  revision_conflict: "场景已更新，请再试一次。",
  stale_epoch: "场景已重新开始，旧操作已失效。",
  invalid_spawn: "出生位置不可通行。",
  checkpoint_inventory_mismatch: "剧情检查点与已采集物品不一致。",
};
export function Prologue({ lab }: { lab: TestRun }) {
  const [state, setState] = useState<BeachState | null>(null);
  const stateRef = useRef<BeachState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const waiting = useRef(0);
  async function acquire() {
    waiting.current++;
    while (lock.current)
      await new Promise((resolve) => setTimeout(resolve, 10));
    waiting.current--;
    lock.current = true;
  }
  const epochGeneration = useRef(0);
  const [debug, setDebug] = useState(false);
  const [inventory, setInventory] = useState(false);
  const [draft, setDraft] = useState("");
  const [allowFallback, setAllowFallback] = useState(true);
  const [replyDraft, setReplyDraft] = useState("");
  const [replyKind, setReplyKind] = useState("answer");
  const [debugTemplate, setDebugTemplate] = useState("npc-claude");
  const [personality, setPersonality] = useState("expectant");
  const [checkpoint, setCheckpoint] = useState("gathering");
  const [selectedActor, setSelectedActor] = useState("npc-bigfish");
  const [actorDraft, setActorDraft] = useState<any>(null);
  const [spawnX, setSpawnX] = useState(944);
  const [spawnY, setSpawnY] = useState(336);
  const [preset, setPreset] = useState<any>(null);
  const [presetName, setPresetName] = useState("beach-default");
  const [savedPresets, setSavedPresets] = useState<Record<string, any>>({});
  const gameHost = useRef<HTMLDivElement>(null);
  const speechHost = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<BeachScene | null>(null);
  const pending = useRef<any>(null);
  const delivered = useRef(new Set<string>());
  const directions = useRef({ dx: 0, dy: 0 });
  function sync(next: BeachState) {
    stateRef.current = next;
    setState(next);
    if (sceneRef.current?.sys.isActive()) sceneRef.current.sync(next);
  }
  async function send(
    kind: string,
    args: Record<string, any> = {},
    quiet = false,
  ) {
    if (!stateRef.current) return;
    if (quiet && (lock.current || waiting.current || pending.current)) return;
    if (!quiet) setBusy(true);
    await acquire();
    const current = stateRef.current!;
    const generation = epochGeneration.current;
    const retryable = kind !== "tick" && kind !== "deliver";
    const signature = JSON.stringify({ kind, ...args });
    if (
      retryable &&
      pending.current &&
      pending.current.signature !== signature
    ) {
      setError("上一项操作尚未确认，请先重试原操作，或重新开始。");
      lock.current = false;
      setBusy(false);
      return;
    }
    if (retryable && !pending.current)
      pending.current = {
        signature,
        body: { ...command(current), kind, ...args },
      };
    const body = retryable
      ? pending.current.body
      : { ...command(current), kind, ...args };
    try {
      const next = await client.post<BeachState>(
        kind === "say" ? "/api/play/v1/agent-turn" : "/api/play/v1/command",
        kind === "say"
          ? {
              text: args.text,
              request_id: body.command_id,
              turn_id: body.command_id,
              allow_fallback: allowFallback,
            }
          : body,
      );
      if (generation !== epochGeneration.current) return;
      sync(next);
      if (retryable) {
        setError("");
        pending.current = null;
      }
      return next;
    } catch (e) {
      if (generation !== epochGeneration.current) return;
      if (!quiet)
        setError(
          e instanceof Error
            ? errors[e.message] || e.message
            : "连接失败，草稿已保留",
        );
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        if (retryable) pending.current = null;
        if (e.status === 409)
          try {
            sync(await client.get("/api/play/v1/state"));
          } catch {
            /* Retain the last confirmed state. */
          }
      }
    } finally {
      lock.current = false;
      if (!quiet) setBusy(false);
    }
  }
  const sendRef = useRef(send);
  sendRef.current = send;
  async function start(reset = false) {
    setBusy(true);
    await acquire();
    const generation = ++epochGeneration.current;
    try {
      const next = await client.post<BeachState>(
        reset ? "/api/play/v1/reset" : "/api/play/v1/sessions",
        reset && stateRef.current ? command(stateRef.current) : undefined,
      );
      if (generation === epochGeneration.current) {
        sync(next);
        setDraft("");
        setReplyDraft("");
        setError("");
        pending.current = null;
        delivered.current.clear();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "连接失败");
      if (e instanceof ApiError && e.status === 409)
        sync(await client.get("/api/play/v1/state"));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    let live = true;
    void client
      .get<BeachState>("/api/play/v1/state")
      .then((value) => {
        if (live) sync(value);
      })
      .catch(() => {});
    return () => {
      live = false;
      epochGeneration.current++;
    };
  }, []);
  function nearest() {
    const s = stateRef.current;
    if (!s) return null;
    const p = s.actors.player;
    return (
      [
        ...Object.entries(s.objects).filter(
          ([, o]) => o.remaining > 0 || o.kind === "sign",
        ),
        ...Object.entries(s.actors).filter(([k]) => k !== "player"),
      ]
        .map(([key, o]) => ({ key, o, d: Math.hypot(p.x - o.x, p.y - o.y) }))
        .filter((v) => v.d <= ("radius" in v.o ? Number(v.o.radius) : 90))
        .sort((a, b) => a.d - b.d || a.key.localeCompare(b.key))[0] || null
    );
  }
  const interactRef = useRef(() => {});
  interactRef.current = () => {
    const n = nearest();
    if (n && !stateRef.current?.dialogue)
      void sendRef.current("interact", { target: n.key });
  };
  useEffect(() => {
    if (!gameHost.current) return;
    const scene = new BeachScene();
    sceneRef.current = scene;
    scene.onReady = () => {
      if (stateRef.current) scene.sync(stateRef.current);
    };
    scene.interact = () => interactRef.current();
    scene.targetPoint = (x, y) => {
      if (stateRef.current && !stateRef.current.dialogue)
        void sendRef.current("walk_to", { x, y });
    };
    const game = new Phaser.Game({
      type: Phaser.CANVAS,
      parent: gameHost.current,
      width: 1408,
      height: 800,
      pixelArt: true,
      antialias: false,
      backgroundColor: "#37abc1",
      scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
      scene: [scene],
      audio: { noAudio: true },
      banner: false,
    });
    const resize = new ResizeObserver(() => {
      game.scale.getParentBounds();
      game.scale.refresh();
    });
    resize.observe(gameHost.current);
    const timer = window.setInterval(() => {
      if (
        !stateRef.current ||
        document.hidden ||
        lock.current ||
        waiting.current ||
        pending.current
      )
        return;
      const active = document.activeElement?.tagName;
      const typing =
        active === "INPUT" || active === "TEXTAREA" || active === "SELECT";
      const dx = typing ? 0 : scene.keys.dx || directions.current.dx,
        dy = typing ? 0 : scene.keys.dy || directions.current.dy;
      if (!stateRef.current.pause_reasons.length)
        void sendRef.current("tick", { dx, dy }, true);
    }, 130);
    return () => {
      clearInterval(timer);
      resize.disconnect();
      game.destroy(true);
      sceneRef.current = null;
    };
  }, []);
  useEffect(() => {
    if (sceneRef.current) sceneRef.current.debug = debug;
  }, [debug]);
  useEffect(() => {
    if (debug && lab.connected && state?.test_run_id)
      void client
        .get<Record<string, any>>(
          `/api/test/v1/runs/${state.test_run_id}/prologue/presets`,
        )
        .then(setSavedPresets)
        .catch((e) => setError(String(e)));
  }, [debug, lab.connected, state?.test_run_id]);
  const speechEntry = state
    ? Object.entries(state.actors).find(
        ([, a]) => a.speech?.status === "waiting",
      )
    : null;
  const speech = speechEntry?.[1].speech;
  useEffect(() => {
    const timer = setInterval(() => {
      const s = stateRef.current,
        host = speechHost.current;
      if (
        !s ||
        s.dialogue ||
        document.hidden ||
        !host ||
        lock.current ||
        pending.current
      )
        return;
      const entry = Object.entries(s.actors).find(
        ([, a]) => a.speech?.status === "waiting",
      );
      if (!entry?.[1].speech) return;
      const message = entry[1].speech,
        rect = host.getBoundingClientRect();
      if (
        message.delivered_at !== null ||
        delivered.current.has(message.id) ||
        rect.width <= 0 ||
        rect.height <= 0 ||
        rect.bottom <= 0 ||
        rect.top >= innerHeight
      )
        return;
      delivered.current.add(message.id);
      void sendRef
        .current("deliver", { target: entry[0], reply_to: message.id }, true)
        .then((result) => {
          if (!result) delivered.current.delete(message.id);
        });
    }, 250);
    return () => clearInterval(timer);
  }, []);
  function makePreset() {
    const s = stateRef.current!;
    return {
      schema_version: 1,
      seed: s.seed,
      checkpoint: s.checkpoint,
      x: s.actors.player.x,
      y: s.actors.player.y,
      collected_objects: Object.entries(s.objects)
        .filter(([, o]) => !o.remaining && o.kind !== "sign")
        .map(([key]) => key),
      npcs: Object.entries(s.actors)
        .filter(([key]) => key !== "player")
        .map(([key, a]) => ({
          id: key,
          template: a.template,
          x: a.x,
          y: a.y,
          personality: a.personality,
          mode: ["idle", "follow", "stay"].includes(a.mode) ? a.mode : "idle",
          hunger: a.hunger,
          mood: a.mood,
        })),
    };
  }
  async function applyPreset(value: any) {
    if (!stateRef.current) return;
    setBusy(true);
    await acquire();
    epochGeneration.current++;
    try {
      const next = await client.post<BeachState>(
        `/api/test/v1/runs/${stateRef.current.test_run_id}/prologue/preset`,
        { ...command(stateRef.current), preset: value },
      );
      sync(next);
      pending.current = null;
      delivered.current.clear();
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "调试请求失败");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function addNPC() {
    const p = makePreset();
    p.npcs.push({
      id: `${debugTemplate.replace("npc-", "")}-${id().slice(0, 6)}`,
      template: debugTemplate,
      x: spawnX,
      y: spawnY,
      personality,
      mode: "idle",
      hunger: 0.35,
      mood: 0.65,
    });
    await applyPreset(p);
  }
  async function savePreset() {
    if (!stateRef.current) return;
    setBusy(true);
    await acquire();
    try {
      const value = makePreset();
      const next = await client.post<BeachState>(
        `/api/test/v1/runs/${stateRef.current.test_run_id}/prologue/presets/${encodeURIComponent(presetName)}`,
        { ...command(stateRef.current), preset: value },
      );
      sync(next);
      setPreset(value);
      setSavedPresets((prev) => ({ ...prev, [presetName]: value }));
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function step() {
    if (!stateRef.current) return;
    await acquire();
    try {
      const next = await client.post<BeachState>(
        `/api/test/v1/runs/${stateRef.current.test_run_id}/prologue/step`,
        { ...command(stateRef.current), kind: "step" },
      );
      sync(next);
    } catch (e) {
      setError(String(e));
    } finally {
      lock.current = false;
    }
  }
  const n = nearest();
  return (
    <div className={`prologue ${debug ? "debug-open" : ""}`}>
      <div className="prologue-header">
        <div>
          <span className="eyebrow">PROLOGUE / 01</span>
          <h1>爱、荒岛和大肥鱼</h1>
        </div>
        <div className="prologue-tools">
          <span className="chapter-label">海滩相遇</span>
          <button
            className="icon"
            title={inventory ? "关闭背包" : "打开背包"}
            aria-label="背包"
            onClick={() => setInventory(!inventory)}
          >
            <Backpack size={18} />
          </button>
          <button
            className="icon"
            disabled={!state || busy}
            title={state?.pause_reasons.includes("manual") ? "继续" : "暂停"}
            aria-label={
              state?.pause_reasons.includes("manual") ? "继续" : "暂停"
            }
            onClick={() =>
              send("pause", {
                enabled: !state?.pause_reasons.includes("manual"),
              })
            }
          >
            {state?.pause_reasons.includes("manual") ? (
              <Play size={18} />
            ) : (
              <Pause size={18} />
            )}
          </button>
          <button
            className={`icon ${debug ? "active" : ""}`}
            title="场景调试"
            aria-label="场景调试"
            onClick={() => setDebug(!debug)}
          >
            <Bug size={18} />
          </button>
          <button
            className="icon"
            disabled={!state || busy}
            title="重新开始"
            aria-label="重新开始"
            onClick={() => start(true)}
          >
            <RotateCcw size={17} />
          </button>
        </div>
      </div>
      {error && (
        <div className="game-error" role="alert">
          {error}
          {pending.current && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => {
                const { kind, ...args } = JSON.parse(
                  pending.current!.signature,
                );
                void send(kind, args);
              }}
            >
              重试未确认操作
            </button>
          )}
          <button className="text-button" onClick={() => setError("")}>
            关闭
          </button>
        </div>
      )}
      <div className="scene-layout">
        <section className="scene-surface">
          <div className="game-stage">
            <div
              className="phaser-host"
              ref={gameHost}
              data-testid="beach-canvas"
            />
            {!state ? (
              <div className="start-scene">
                <span className="chapter-number">01</span>
                <h2>潮水退去的时候</h2>
                <p>一片陌生的海岸。还有一个看起来有点饿的人。</p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => start()}
                >
                  {busy ? "连接海滩…" : "醒来"}
                  <ChevronRight size={16} />
                </button>
              </div>
            ) : (
              <>
                <div className="quest-hud">
                  <span className="quest-label">
                    {state.checkpoint === "completed" ? "已完成" : "当前目标"}
                  </span>
                  <strong>
                    {state.checkpoint === "encounter"
                      ? "与大肥鱼打个招呼"
                      : state.checkpoint === "completed"
                        ? "海滩上的第一份收获"
                        : "收集海滩上的材料"}
                  </strong>
                  {state.checkpoint !== "encounter" && (
                    <div className="quest-progress">
                      <span
                        className={state.inventory.berry >= 3 ? "done" : ""}
                      >
                        浆果 <b>{Math.min(3, state.inventory.berry)}/3</b>
                      </span>
                      <span className={state.inventory.wood >= 2 ? "done" : ""}>
                        漂流木 <b>{Math.min(2, state.inventory.wood)}/2</b>
                      </span>
                    </div>
                  )}
                </div>
                <div className="scene-location">
                  <span className="status-dot" />晴 · 南岸 <small>09:00</small>
                </div>
                {inventory && (
                  <div className="inventory-panel">
                    <div className="inventory-heading">
                      <Backpack size={15} />
                      <h3>背包</h3>
                      <button
                        className="icon"
                        aria-label="关闭背包"
                        onClick={() => setInventory(false)}
                      >
                        <X size={16} />
                      </button>
                    </div>
                    {Object.entries(state.inventory).map(([key, count]) => (
                      <div className="inventory-item" key={key}>
                        <span className={`item-pixel ${key}`} />
                        <span>{itemNames[key]}</span>
                        <b data-testid={`inventory-${key}`}>{count}</b>
                      </div>
                    ))}
                  </div>
                )}
                {!state.dialogue && n && (
                  <button
                    className="interact-hint"
                    disabled={busy}
                    onClick={() => interactRef.current()}
                  >
                    <kbd>E</kbd>
                    {"kind" in n.o
                      ? `${n.o.kind === "crate" ? "打开" : n.o.kind === "sign" ? "阅读" : "采集"}${itemNames[n.o.kind]}`
                      : `与${n.o.name}交谈`}
                  </button>
                )}
                {state.pause_reasons.includes("manual") && (
                  <div className="paused-label">
                    <Pause size={14} />
                    已暂停
                  </div>
                )}
              </>
            )}
          </div>
          {state?.dialogue && (
            <div className="dialogue-panel">
              <div className="dialogue-portrait">
                <div className="portrait-pixel">
                  <div className="portrait-hat" />
                  <div className="portrait-hair" />
                  <div className="portrait-face">
                    <i />
                    <i />
                  </div>
                  <div className="portrait-shirt" />
                </div>
              </div>
              <div className="dialogue-content">
                <div className="dialogue-heading">
                  <span>{state.actors[state.dialogue]?.name || "大肥鱼"}</span>
                  <small>
                    Agent 回合 / {state.model === "llm-agent" ? "真实模型" : "离线模型"}
                  </small>
                  <label className="fallback-toggle">
                    <input
                      type="checkbox"
                      checked={allowFallback}
                      onChange={(e) => setAllowFallback(e.target.checked)}
                    />
                    允许离线保底
                  </label>
                  <button
                    className="icon"
                    title="结束对话"
                    aria-label="结束对话"
                    disabled={busy}
                    onClick={() => send("close_dialogue")}
                  >
                    <X size={17} />
                  </button>
                </div>
                <p>
                  {state.messages
                    .filter((m) => m.author === state.dialogue)
                    .at(-1)?.text || "你醒啦？这里的海风不错，就是肚子有点空……"}
                </p>
                {state.messages.filter((m) => m.author === "player").at(-1) && (
                  <div className="last-player-message">
                    沈理：
                    {
                      state.messages.filter((m) => m.author === "player").at(-1)
                        .text
                    }
                  </div>
                )}
                <div className="suggestions">
                  {["这里是什么地方？", "我们先找点吃的吧。"].map((text) => (
                    <button
                      disabled={busy}
                      key={text}
                      onClick={() =>
                        send("say", { text }).then((result) => {
                          if (result) setDraft("");
                        })
                      }
                    >
                      {text}
                      <ChevronRight size={12} />
                    </button>
                  ))}
                </div>
                <form
                  className="dialogue-input"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (draft.trim())
                      void send("say", { text: draft }).then((result) => {
                        if (result) setDraft("");
                      });
                  }}
                >
                  <textarea
                    aria-label="序章对话"
                    placeholder="你想说……"
                    maxLength={2000}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing &&
                        e.keyCode !== 229
                      ) {
                        e.preventDefault();
                        if (draft.trim())
                          void send("say", { text: draft }).then((result) => {
                            if (result) setDraft("");
                          });
                      }
                    }}
                  />
                  <button
                    className="primary"
                    type="submit"
                    disabled={busy || !draft.trim()}
                    aria-label="发送序章对话"
                  >
                    <Send size={15} />
                  </button>
                </form>
              </div>
            </div>
          )}
          {speech && speechEntry && !state?.dialogue && (
            <div className="follow-reply" ref={speechHost}>
              <MessageSquare size={17} />
              <div>
                <strong>{speechEntry[1].name}</strong>
                <p>{speech.text}</p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (replyDraft.trim())
                      void send("reply", {
                        target: speechEntry[0],
                        reply_to: speech.id,
                        text: replyDraft,
                        response_kind: replyKind,
                      }).then((result) => {
                        if (result) setReplyDraft("");
                      });
                  }}
                >
                  <select
                    aria-label="随行回应方式"
                    value={replyKind}
                    onChange={(e) => setReplyKind(e.target.value)}
                  >
                    <option value="answer">回应</option>
                    <option value="later">稍后再聊</option>
                    <option value="decline">结束同行</option>
                  </select>
                  <input
                    aria-label="随行回复"
                    placeholder="回复……"
                    value={replyDraft}
                    maxLength={2000}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing || e.keyCode === 229) {
                        if (e.key === "Enter") e.preventDefault();
                      }
                    }}
                  />
                  <button
                    type="submit"
                    className="icon"
                    disabled={busy || !replyDraft.trim()}
                    aria-label="发送随行回复"
                  >
                    <Send size={15} />
                  </button>
                </form>
              </div>
            </div>
          )}
          {state && (
            <footer className="scene-footer">
              <div className="scene-controls">
                <button
                  disabled={
                    busy || !!state.dialogue || !state.actors["npc-bigfish"]
                  }
                  onClick={() => send("follow", { target: "npc-bigfish" })}
                >
                  <Footprints size={15} />
                  邀请跟随
                </button>
                <button
                  disabled={
                    busy || !!state.dialogue || !state.actors["npc-bigfish"]
                  }
                  onClick={() => send("stay", { target: "npc-bigfish" })}
                >
                  <Hand size={15} />
                  原地休息
                </button>
              </div>
              <span className="scene-receipt">
                {state.last_action?.startsWith("collected:")
                  ? `已收集${itemNames[state.objects[state.last_action.slice(10)]?.kind] || "物品"}`
                  : state.last_action === "talk"
                    ? "大肥鱼看向了你。"
                    : state.last_action || "潮水轻轻拍着海岸。"}
              </span>
              <div className="direction-pad">
                {[
                  [ArrowUp, 0, -1, "向上"],
                  [ArrowLeft, -1, 0, "向左"],
                  [ArrowDown, 0, 1, "向下"],
                  [ArrowRight, 1, 0, "向右"],
                ].map(([Icon, dx, dy, label]) => {
                  const I = Icon as typeof ArrowUp;
                  return (
                    <button
                      className="icon"
                      aria-label={label as string}
                      title={label as string}
                      key={label as string}
                      onPointerDown={(e) => {
                        e.currentTarget.setPointerCapture(e.pointerId);
                        directions.current = {
                          dx: dx as number,
                          dy: dy as number,
                        };
                      }}
                      onPointerUp={() => {
                        directions.current = { dx: 0, dy: 0 };
                      }}
                      onPointerCancel={() => {
                        directions.current = { dx: 0, dy: 0 };
                      }}
                    >
                      <I size={14} />
                    </button>
                  );
                })}
              </div>
            </footer>
          )}
        </section>
        {debug && (
          <aside className="debug-panel">
            <div className="side-title">
              <Bug size={16} />
              <h3>场景调试</h3>
              <span className="badge amber">TEST</span>
            </div>
            {!lab.connected ? (
              <div className="empty compact">连接测试凭据后可编辑场景。</div>
            ) : !state ? (
              <div className="empty compact">先开始海滩场景。</div>
            ) : (
              <>
                <div className="debug-version">
                  epoch <code>{state.run_epoch.slice(0, 8)}</code>
                  <span>
                    rev {state.revision} · tick {state.tick}
                  </span>
                </div>
                <div className="side-section">
                  <h3>剧情检查点</h3>
                  <select
                    aria-label="剧情检查点"
                    value={checkpoint}
                    onChange={(e) => setCheckpoint(e.target.value)}
                  >
                    <option value="encounter">海滩首遇</option>
                    <option value="gathering">已交谈 · 开始采集</option>
                    <option value="completed">采集完成</option>
                  </select>
                  <button
                    disabled={busy}
                    onClick={() =>
                      applyPreset({
                        ...makePreset(),
                        checkpoint,
                        collected_objects: null,
                      })
                    }
                  >
                    应用检查点
                  </button>
                </div>
                <div className="side-section">
                  <h3>添加 NPC</h3>
                  <select
                    aria-label="NPC 模板"
                    value={debugTemplate}
                    onChange={(e) => setDebugTemplate(e.target.value)}
                  >
                    {Object.entries({
                      "npc-bigfish": "大肥鱼",
                      "npc-claude": "克劳德",
                      cook: "厨师",
                      merchant: "商人",
                      farmer: "农夫",
                      adventurer: "冒险家",
                      mechanic: "机械师",
                    }).map(([k, v]) => (
                      <option value={k} key={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="性格预设"
                    value={personality}
                    onChange={(e) => setPersonality(e.target.value)}
                  >
                    <option value="mellow">随和 · 未回应继续同行</option>
                    <option value="expectant">期待回应 · 超时离场</option>
                  </select>
                  <div className="debug-coordinates">
                    <label>
                      X
                      <input
                        type="number"
                        aria-label="出生 X"
                        value={spawnX}
                        onChange={(e) => setSpawnX(Number(e.target.value))}
                      />
                    </label>
                    <label>
                      Y
                      <input
                        type="number"
                        aria-label="出生 Y"
                        value={spawnY}
                        onChange={(e) => setSpawnY(Number(e.target.value))}
                      />
                    </label>
                  </div>
                  <button disabled={busy} onClick={addNPC}>
                    <Plus size={14} />
                    加入场景
                  </button>
                </div>
                <div className="side-section">
                  <h3>场景角色</h3>
                  {Object.entries(state.actors)
                    .filter(([key]) => key !== "player")
                    .map(([key, a]) => (
                      <div className="debug-actor" key={key}>
                        <button
                          className="text-button"
                          onClick={() => {
                            setSelectedActor(key);
                            setActorDraft({
                              x: a.x,
                              y: a.y,
                              mode: ["idle", "follow", "stay"].includes(a.mode)
                                ? a.mode
                                : "idle",
                              personality: a.personality,
                              hunger: a.hunger,
                              mood: a.mood,
                            });
                          }}
                        >
                          {a.name}
                          <small>{key}</small>
                        </button>
                        <span>{a.mode}</span>
                        <button
                          className="icon"
                          aria-label={`移除${key}`}
                          title="移除 NPC"
                          disabled={busy}
                          onClick={() => {
                            const p = makePreset();
                            p.npcs = p.npcs.filter((v: any) => v.id !== key);
                            void applyPreset(p);
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                </div>
                <div className="debug-actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      send("pause", {
                        enabled: !state.pause_reasons.includes("manual"),
                      })
                    }
                  >
                    {state.pause_reasons.includes("manual") ? (
                      <Play size={14} />
                    ) : (
                      <Pause size={14} />
                    )}
                    暂停/继续
                  </button>
                  <button
                    disabled={busy || !state.pause_reasons.includes("manual")}
                    onClick={step}
                  >
                    <ChevronRight size={14} />
                    单步
                  </button>
                </div>
                <div className="side-section">
                  <h3>版本化预设</h3>
                  <input
                    aria-label="预设名称"
                    value={presetName}
                    maxLength={80}
                    onChange={(e) => setPresetName(e.target.value)}
                  />
                  <div className="debug-actions">
                    <button disabled={busy || !presetName} onClick={savePreset}>
                      <Save size={14} />
                      保存预设
                    </button>
                    <button
                      disabled={!preset || busy}
                      onClick={() => applyPreset(preset)}
                    >
                      <Upload size={14} />
                      载入预设
                    </button>
                  </div>
                  <select
                    aria-label="已保存预设"
                    value=""
                    onChange={(e) => {
                      const value = savedPresets[e.target.value];
                      if (value) {
                        setPresetName(e.target.value);
                        setPreset(value);
                      }
                    }}
                  >
                    <option value="">选择服务端预设</option>
                    {Object.keys(savedPresets).map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="side-section">
                  <h3>选中实体 · 确认状态</h3>
                  {actorDraft && (
                    <div className="actor-editor">
                      <select
                        aria-label="实体行为"
                        value={actorDraft.mode}
                        onChange={(e) =>
                          setActorDraft({ ...actorDraft, mode: e.target.value })
                        }
                      >
                        <option value="idle">自主活动</option>
                        <option value="follow">跟随</option>
                        <option value="stay">原地停留</option>
                      </select>
                      <select
                        aria-label="实体性格"
                        value={actorDraft.personality}
                        onChange={(e) =>
                          setActorDraft({
                            ...actorDraft,
                            personality: e.target.value,
                          })
                        }
                      >
                        <option value="mellow">随和</option>
                        <option value="expectant">期待回应</option>
                      </select>
                      {(["x", "y", "hunger", "mood"] as const).map((field) => (
                        <label key={field}>
                          {
                            {
                              x: "X",
                              y: "Y",
                              hunger: "饥饿程度 0..1",
                              mood: "心情 0..1",
                            }[field]
                          }
                          <input
                            type="number"
                            aria-label={`实体 ${field}`}
                            step={field === "x" || field === "y" ? 1 : 0.05}
                            min={0}
                            max={field === "x" ? 1408 : field === "y" ? 800 : 1}
                            value={actorDraft[field]}
                            onChange={(e) =>
                              setActorDraft({
                                ...actorDraft,
                                [field]: Number(e.target.value),
                              })
                            }
                          />
                        </label>
                      ))}
                      <button
                        disabled={busy}
                        onClick={() => {
                          const value = makePreset();
                          value.npcs = value.npcs.map((a) =>
                            a.id === selectedActor
                              ? { ...a, ...actorDraft }
                              : a,
                          );
                          void applyPreset(value);
                        }}
                      >
                        应用实体状态
                      </button>
                    </div>
                  )}
                  <JsonViewer value={state.actors[selectedActor]} />
                  <span className="badge neutral">
                    Agent API / MCP · {state.model || "offline-agent"}
                  </span>
                </div>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
