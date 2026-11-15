import { Eye, Play, Square } from "lucide-react";
import { useState } from "react";
import { client } from "../../api/client";
import type { TestRun } from "../../hooks/useTestRun";

export function GenerationControls({ lab, conversationId, allowFallback }: { lab: TestRun; conversationId: string | null; allowFallback: boolean }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function generate() {
    if (!lab.run || !conversationId || !text.trim()) return;
    setBusy(true);
    const turnId = crypto.randomUUID().replaceAll("-", "");
    try { setResult(await client.post(`${lab.base}/conversations/${conversationId}/turns`, { turn_id: turnId, request_id: turnId, text, npc_id: lab.npc, allow_fallback: allowFallback })); }
    finally { setBusy(false); }
  }
  return <section className="generation-controls" aria-label="NPC 单轮生成">
    <div className="side-title"><Eye size={16} /><h3>单轮生成</h3></div>
    <textarea aria-label="生成输入" value={text} onChange={(e) => setText(e.target.value)} placeholder="输入一条玩家消息" />
    <div className="scheduler-actions"><button disabled={busy || !conversationId || !text.trim()} onClick={() => void generate()}><Play size={14} />生成一轮</button><button disabled={!busy} onClick={() => setBusy(false)}><Square size={14} />取消</button></div>
    {result && <pre className="action-result">{JSON.stringify(result, null, 2)}</pre>}
  </section>;
}
