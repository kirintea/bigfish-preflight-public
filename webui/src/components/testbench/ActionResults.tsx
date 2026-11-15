import { MapPin, Play } from "lucide-react";
import { useState } from "react";
import { client } from "../../api/client";
import type { TestRun } from "../../hooks/useTestRun";

export function ActionResults({ lab }: { lab: TestRun }) {
  const [location, setLocation] = useState("");
  const [result, setResult] = useState<any>(null);
  async function execute() {
    if (!lab.run || !location.trim()) return;
    setResult(await client.post(`${lab.base}/npcs/${lab.npc}/actions`, { capability: "guide_to_location", parameters: { location_id: location } }));
  }
  return <section className="generation-controls" aria-label="模拟动作"><div className="side-title"><MapPin size={16} /><h3>模拟动作</h3></div><input aria-label="目标地点" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="location_id" /><button disabled={!lab.run || !location.trim()} onClick={() => void execute()}><Play size={14} />执行模拟动作</button>{result && <pre className="action-result">{JSON.stringify(result, null, 2)}</pre>}</section>;
}
