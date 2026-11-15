import { useEffect, useRef, useState } from "react";
import {
  MessageSquare,
  Plus,
  Send,
  Users,
  ArrowRight,
  Square,
  Play,
} from "lucide-react";
import { client, command, ApiError, streamPost } from "../../api/client";
import { names, type TestRun } from "../../hooks/useTestRun";
import { JsonViewer } from "../../components/observe/JsonViewer";
import { GenerationControls } from "../../components/testbench/GenerationControls";
import { ActionResults } from "../../components/testbench/ActionResults";

export function ConversationChat({ lab }: { lab: TestRun }) {
  const [chat, setChat] = useState<any>(null);
  const [members, setMembers] = useState([
    "player",
    "npc-bigfish",
    "npc-claude",
  ]);
  const [draft, setDraft] = useState("");
  const [target, setTarget] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [allowFallback, setAllowFallback] = useState(true);
  const [interactionMode, setInteractionMode] = useState("disabled");
  const [viewer, setViewer] = useState("npc-bigfish");
  const [context, setContext] = useState<any>(null);
  const pending = useRef<any>(null);
  const streamController = useRef<AbortController | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const current = useRef("");
  const contextGeneration = useRef(0);
  const activeConversation = useRef("");
  activeConversation.current = chat?.conversation_id || "";
  const epoch = lab.run?.run_epoch || "";
  useEffect(() => () => streamController.current?.abort(), [epoch]);
  current.current = epoch;
  useEffect(() => {
    const saved = Object.values(lab.run?.chat_sessions || {}).at(-1);
    setChat(
      saved
        ? { ...saved, revision: lab.run!.revision, run_epoch: epoch }
        : null,
    );
    setContext(null);
    pending.current = null;
    setDraft("");
    setReplyTo(null);
  }, [epoch]);
  useEffect(() => {
    scroll.current?.scrollTo({
      top: scroll.current.scrollHeight,
      behavior: "smooth",
    });
  }, [chat?.messages]);
  useEffect(() => {
    contextGeneration.current++;
    setContext(null);
  }, [chat?.conversation_id, viewer]);
  const choices = [
    ...new Set([
      "player",
      ...(lab.run?.npc_ids || ["npc-bigfish", "npc-claude"]),
    ]),
  ];
  async function create() {
    if (!lab.run) return;
    const requestEpoch = epoch;
    await lab.attempt(async () => {
      const result = await client.post(lab.base + "/conversations", {
        ...command(lab.run!),
        members,
        interaction_mode: interactionMode,
      });
      if (current.current === requestEpoch) {
        setChat(result);
        await lab.refresh();
      }
    });
  }

  async function streamNpcTurn(npcId: string, text: string, requestId: string, scheduler = false, force = false) {
    const cid = chat.conversation_id;
    const requestEpoch = epoch;
    const controller = new AbortController();
    streamController.current = controller;
    let timedOut = false;
    let timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120000);
    const valid = () => current.current === requestEpoch && activeConversation.current === cid;
    const update = (fn: (previous: any) => any) => { if (valid()) setChat(fn); };
    const placeholderId = `stream-${requestId}`;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
    const response = await streamPost(
      lab.base + `/conversations/${chat.conversation_id}/turns/stream`,
      {
        turn_id: requestId,
        request_id: requestId,
        text,
        npc_id: npcId,
        allow_fallback: allowFallback,
        trigger: scheduler ? 'scheduler' : 'player_message',
        force,
        run_epoch: requestEpoch,
      },
      controller.signal,
    );
    if (!response.body) throw new Error("stream_body_missing");
    update((previous: any) => previous && {
      ...previous,
      messages: [...previous.messages, {
        message_id: placeholderId,
        author: npcId,
        text: "",
        targets: [],
        actual_recipients: [],
        members_at_delivery: previous.members,
        reply_to: null,
        adapter: "streaming",
        streaming: true,
      }],
    });
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let eventName = "message";
    let result: any = null;
    const consume = (block: string) => {
      let data = "";
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) return;
      const payload = JSON.parse(data);
      if (eventName === "delta") {
        update((previous: any) => previous && {
          ...previous,
          messages: previous.messages.map((message: any) =>
            message.message_id === placeholderId
              ? { ...message, text: message.text + payload.text }
              : message,
          ),
        });
      } else if (eventName === "result") {
        result = payload;
      } else if (eventName === "error") {
        throw new Error(payload.detail || "stream_failed");
      }
      eventName = "message";
    };
    while (true) {
      const chunk = await reader.read();
      clearTimeout(timer);
      timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120000);
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
      let split = buffer.indexOf("\n\n");
      while (split >= 0) {
        consume(buffer.slice(0, split));
        buffer = buffer.slice(split + 2);
        split = buffer.indexOf("\n\n");
      }
      if (chunk.done) break;
    }
    if (buffer.trim()) consume(buffer);
    if (!result) throw new Error("stream_result_missing");
    const latest = await client.get(lab.base + `/conversations/${cid}`);
    if (valid()) setChat(latest);
    return result;
    } catch (error) {
      update((previous: any) => previous && ({ ...previous,
        messages: previous.messages.filter((m: any) => m.message_id !== placeholderId) }));
      if (controller.signal.aborted) throw new Error(timedOut ? '生成等待超时，可重试。' : '已停止生成。');
      throw error;
    } finally {
      clearTimeout(timer);
      await reader?.cancel().catch(() => {});
      if (streamController.current === controller) streamController.current = null;
    }
  }

  async function npcExchange(mode: string, key: string, force = false) {
    const ids: string[] = chat.members.filter((n: string) => n !== 'player');
    if (ids.length < 2 || (mode === 'disabled' && !force)) return;
    const latest = await client.get(lab.base + `/conversations/${chat.conversation_id}`);
    const last = latest.messages.at(-1)?.author;
    const ordered = [...ids.filter((n) => n !== last), ...ids.filter((n) => n === last)];
    // Automatic continuation is bounded to one reply per player exchange.
    for (const npcId of (force || mode === 'forced' ? ordered : ordered.slice(0, 1))) {
      await streamNpcTurn(npcId, '请接着群聊中其他 NPC 的话题回应他们；没有话题时向另一位 NPC 发起一个简短问题。只说自己的台词。',
        `${key}-${npcId}`, true, force);
    }
  }

  async function send(text = draft) {
    if (!chat || !text.trim() || lab.busy) return;
    const requestEpoch = epoch;
    const conversationId = chat.conversation_id;
    if (pending.current && pending.current.text !== text) {
      lab.setError("上一条消息尚未确认，请先重试未确认消息。");
      return;
    }
    pending.current ||= {
      ...command(chat),
      text,
      targets: target ? [target] : [],
      reply_to: replyTo,
      generate: true,
    };
    await lab.attempt(async () => {
      try {
        const result = await client.post(
          lab.base + `/conversations/${chat.conversation_id}/messages`,
          pending.current,
        );
        if (
          current.current !== requestEpoch ||
          activeConversation.current !== conversationId
        )
          return;
        setChat(result);
        const npcIds = target
          ? [target]
          : result.generation_targets || chat.members.filter((member: string) => member !== "player");
        for (const npcId of npcIds) {
          const requestId = `${pending.current.command_id}-${npcId}`;
          await streamNpcTurn(npcId, text, requestId);
        }
        await npcExchange(chat.interaction_mode || interactionMode, `${pending.current.command_id}-npc`);
        if (npcIds.length) {
          const latest = await client.get(
            lab.base + `/conversations/${conversationId}`,
          );
          setChat(latest);
        }
        setDraft("");
        pending.current = null;
        setReplyTo(null);
        await lab.refresh();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          pending.current = null;
          const latest = await client.get(
            lab.base + `/conversations/${conversationId}`,
          );
          if (
            current.current === requestEpoch &&
            activeConversation.current === conversationId
          )
            setChat(latest);
        }
        throw e;
      }
    });
  }
  async function changeMembers(next: string[]) {
    if (pending.current) {
      lab.setError("请先重试未确认消息，再修改成员。");
      return;
    }
    if (!chat) {
      setMembers(next);
      return;
    }
    const requestEpoch = epoch;
    await lab.attempt(async () => {
      const result = await client.post(
        lab.base + `/conversations/${chat.conversation_id}/members`,
        { ...command(chat), members: next, interaction_mode: chat.interaction_mode || interactionMode },
      );
      if (current.current === requestEpoch) {
        setChat(result);
        setMembers(next);
        setInteractionMode(result.interaction_mode || interactionMode);
        pending.current = null;
        await lab.refresh();
      }
    });
  }
  const refresh = () =>
    lab.attempt(async () => {
      if (!chat) return;
      const result = await client.get(
        lab.base + `/conversations/${chat.conversation_id}`,
      );
      if (result.run_epoch === current.current) {
        setChat(result);
      }
    });
  async function refreshContext() {
    if (chat) {
      const version = current.current;
      const generation = ++contextGeneration.current;
      const result = await client.get(
        lab.base + `/conversations/${chat.conversation_id}/context/${viewer}`,
      );
      if (
        version === current.current &&
        generation === contextGeneration.current
      )
        setContext(result);
    }
  }
  const observing = chat && !chat.members.includes("player");
  return (
    <div className="chat-layout">
      <section className="chat-main">
        <div className="section-heading">
          <div>
            <span className="eyebrow">CONVERSATION / GROUP</span>
            <h2>海风里的碰面</h2>
          </div>
          <span className="badge">
            {chat ? `${chat.members.length} 位成员` : "新会话"}
          </span>
        </div>
        {!!lab.run && Object.keys(lab.run.chat_sessions).length > 0 && (
          <div className="chat-history-select">
            <select
              aria-label="已有会话"
              disabled={lab.busy || !!pending.current}
              value={chat?.conversation_id || ""}
              onChange={(e) => {
                const selected = lab.run!.chat_sessions[e.target.value];
                setChat(
                  selected
                    ? {
                        ...selected,
                        revision: lab.run!.revision,
                        run_epoch: epoch,
                      }
                    : null,
                );
                setContext(null);
                pending.current = null;
              }}
            >
              <option value="">新会话</option>
              {Object.values(lab.run.chat_sessions).map((c: any) => (
                <option key={c.conversation_id} value={c.conversation_id}>
                  {c.members.map((m: string) => names[m] || m).join("、")} ·{" "}
                  {c.messages.length} 条
                </option>
              ))}
            </select>
            <button
              className="icon"
              title="新建群聊"
              aria-label="新建群聊"
              disabled={lab.busy || !!pending.current}
              onClick={() => {
                setChat(null);
                setMembers(["player", "npc-bigfish", "npc-claude"]);
              }}
            >
              <Plus size={15} />
            </button>
          </div>
        )}
        {!lab.run ? (
          <div className="empty">
            <MessageSquare />
            <h3>还没有测试世界</h3>
            <p>创建测试世界后开始会话。</p>
          </div>
        ) : !chat ? (
          <div className="chat-setup">
            <Users size={32} />
            <h3>新建群聊</h3>
            <div className="member-options">
              {choices.map((n) => (
                <label key={n}>
                  <input
                    type="checkbox"
                    checked={members.includes(n)}
                    onChange={(e) =>
                      setMembers(
                        e.target.checked
                          ? [...members, n]
                          : members.filter((v) => v !== n),
                      )
                    }
                  />
                  {names[n] || n}
                </label>
              ))}
            </div>
            <button
              className="primary"
              disabled={members.length < 2 || lab.busy}
              onClick={create}
            >
              <Plus size={16} />
              创建会话
            </button>
            <span className="muted">
              {members.length < 2
                ? "至少选择两名参与者"
                : "正式会话 · 离线脚本"}
            </span>
          </div>
        ) : (
          <>
            <div className="chat-mode">
              <span className="badge">
                {chat.status === "paused" ? "成员不足 · 已暂停" : "正式会话"}
              </span>
              <span className="muted">离线脚本</span>
              <label className="fallback-toggle">
                <input
                  type="checkbox"
                  checked={allowFallback}
                  onChange={(e) => setAllowFallback(e.target.checked)}
                />
                允许离线保底
              </label>
              <label className="fallback-toggle">
                NPC 互动
                <select
                  disabled={lab.busy || !!pending.current}
                  aria-label="NPC 互动模式"
                  value={chat.interaction_mode || interactionMode}
                  onChange={async (e) => {
                    const mode = e.target.value;
                    setInteractionMode(mode);
                    if (chat) {
                      await lab.attempt(async () => { const latest = await client.get(lab.base + `/conversations/${chat.conversation_id}`); await client.post(
                        lab.base + `/conversations/${chat.conversation_id}/members`,
                        { ...command(latest), members: chat.members, interaction_mode: mode },
                      ).then((next) => setChat(next)); });
                    }
                  }}
                >
                  <option value="disabled">禁止 NPC 互聊</option>
                  <option value="automatic">自动接话一次</option>
                  <option value="forced">每次强制互聊一轮</option>
                </select>
              </label>
              <button className="text-button" onClick={refresh}>
                刷新会话
              </button>
            </div>
            <div className="messages" ref={scroll}>
              {!chat.messages.length && (
                <div className="chat-start">
                  <span>今天 · 海岸</span>
                  <p>
                    {observing
                      ? "你正在旁观这段会话"
                      : "海风很轻，聊点什么吧。"}
                  </p>
                </div>
              )}
              {chat.messages.map((m: any) => (
                <article
                  key={m.message_id}
                  className={`message ${m.author === "player" ? "own" : ""}`}
                >
                  <span
                    className={`avatar ${m.author === "npc-claude" ? "claude" : m.author === "player" ? "player" : ""}`}
                  >
                    {(names[m.author] || m.author)[0]}
                  </span>
                  <div className="message-body">
                    <div className="message-author">
                      {names[m.author] || m.author}
                      <small>
                        {m.streaming ? '生成中' : m.author === 'player' ? '玩家' : m.adapter === 'offline-script' ? '离线脚本' : 'NPC'}
                      </small>
                    </div>
                    {m.reply_to && (
                      <small className="reply-ref">
                        回复 {m.reply_to.slice(0, 8)}
                      </small>
                    )}
                    <div className="message-text">{m.text}</div>
                    <div className="message-meta">
                      送达{" "}
                      {m.actual_recipients
                        .map((n: string) => names[n] || n)
                        .join("、")}
                      <button
                        className="text-button"
                        onClick={() => setReplyTo(m.message_id)}
                      >
                        回复
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            {observing ? (
              <div className="observer-bar">
                <span>旁观中 · 仅查看历史</span>
                <button
                  className="primary"
                  onClick={() => changeMembers([...chat.members, "player"])}
                >
                  <Plus size={15} />
                  加入会话
                </button>
              </div>
            ) : (
              <div className="composer">
                <div className="suggestions">
                  {["这片海滩有什么？", "我们一起收集材料吧。"].map((t) => (
                    <button
                      disabled={lab.busy || chat.status !== "open"}
                      key={t}
                      onClick={() => send(t)}
                    >
                      {t}
                      <ArrowRight size={13} />
                    </button>
                  ))}
                </div>
                {replyTo && (
                  <div className="reply-ref">
                    回复 {replyTo.slice(0, 8)}{" "}
                    <button
                      className="text-button"
                      onClick={() => setReplyTo(null)}
                    >
                      取消
                    </button>
                  </div>
                )}
                <textarea
                  aria-label="聊天内容"
                  placeholder="说点什么……"
                  value={draft}
                  maxLength={2000}
                  onChange={(e) => {
                    setDraft(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing &&
                      e.keyCode !== 229
                    ) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <div className="composer-footer">
                  {pending.current && (
                    <button
                      className="text-button"
                      disabled={lab.busy}
                      onClick={() => send(pending.current.text)}
                    >
                      重试未确认消息
                    </button>
                  )}
                  <select
                    aria-label="指向对象"
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                  >
                    <option value="">所有人</option>
                    {chat.members
                      .filter((n: string) => n !== "player")
                      .map((n: string) => (
                        <option value={n} key={n}>
                          {names[n] || n}
                        </option>
                      ))}
                  </select>
                  <small>{draft.length}/2000</small>
                  <button
                    className="primary"
                    aria-label="发送消息"
                    disabled={
                      lab.busy || !draft.trim() || chat.status !== "open"
                    }
                    onClick={() => send()}
                  >
                    <Send size={16} />
                    发送
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
      <aside className="chat-side">
        <div className="side-title">
          <Users size={16} />
          <h3>会话成员</h3>
          <span>{(chat?.members || members).length}</span>
        </div>
        <div className="member-list">
          {choices.map((n) => (
            <label className="member" key={n}>
              <span
                className={`avatar ${n === "npc-claude" ? "claude" : n === "player" ? "player" : ""}`}
              >
                {(names[n] || n)[0]}
              </span>
              <span>
                <strong>{names[n] || n}</strong>
                <small>{n === "player" ? "玩家" : "待机 · 离线脚本"}</small>
              </span>
              <input
                aria-label={`会话成员 ${names[n] || n}`}
                type="checkbox"
                disabled={lab.busy}
                checked={(chat?.members || members).includes(n)}
                onChange={(e) =>
                  changeMembers(
                    e.target.checked
                      ? [...(chat?.members || members), n]
                      : (chat?.members || members).filter(
                          (v: string) => v !== n,
                        ),
                  )
                }
              />
            </label>
          ))}
        </div>
        <GenerationControls lab={lab} conversationId={chat?.conversation_id || null} allowFallback={allowFallback} />
        <ActionResults lab={lab} />
        <div className="side-section">
          <h3>发言调度</h3>
          <span className="badge neutral">每轮有限发言，可随时停止</span>
          <div className="scheduler-actions">
            <button disabled={!chat || lab.busy || !!pending.current || chat.status !== 'open' || chat.members.filter((n: string) => n !== 'player').length < 2}
              onClick={() => lab.attempt(async () => { await npcExchange('forced', crypto.randomUUID().replaceAll('-', ''), true); await lab.refresh(); })}>
              <Play size={14} />
              强制互聊一轮
            </button>
            <button disabled={!lab.busy} onClick={() => streamController.current?.abort()}>
              <Square size={14} />
              取消
            </button>
          </div>
        </div>
        <div className="side-section">
          <h3>角色可见会话</h3>
          <select
            aria-label="会话上下文角色"
            value={viewer}
            onChange={(e) => {
              setViewer(e.target.value);
              setContext(null);
            }}
          >
            {choices.map((n) => (
              <option key={n} value={n}>
                {names[n] || n}
              </option>
            ))}
          </select>
          <button
            disabled={!chat || lab.busy}
            onClick={() => lab.attempt(refreshContext)}
          >
            读取接收记录
          </button>
          {context ? (
            <JsonViewer value={context} />
          ) : (
            <div className="empty compact">暂无角色视图</div>
          )}
        </div>
      </aside>
    </div>
  );
}
