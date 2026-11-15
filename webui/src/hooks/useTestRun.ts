import { useRef, useState } from "react";
import { testControl, type World, base } from "../api/testControl";
import { client, setCredential } from "../api/client";
export const names: Record<string, string> = {
  player: "沈理",
  "npc-bigfish": "大肥鱼",
  "npc-claude": "克劳德",
};
export function useTestRun() {
  const [run, setRun] = useState<World | null>(null);
  const [npc, setNpc] = useState("npc-bigfish");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const generation = useRef(0);
  async function attempt<T>(task: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError("");
    try {
      return await task();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  const connect = (token: string) =>
    attempt(async () => {
      setConnected(false);
      setCredential(token);
      const value = await client.get("/api/v1/observe/status");
      setStatus(value);
      setConnected(true);
    });
  const create = () =>
    attempt(async () => {
      const token = ++generation.current;
      const created = await testControl.create();
      const state = await testControl.state(created);
      if (token === generation.current) setRun(state);
    });
  const refresh = async () => {
    if (run) {
      const token = generation.current;
      const state = await testControl.state(run);
      if (token === generation.current) setRun(state);
      return state;
    }
  };
  const select = async (runId: string) => {
    await attempt(async () => {
      const token = ++generation.current;
      const state = await client.get<World>(`/api/test/v1/runs/${runId}/state`);
      if (token === generation.current) setRun(state);
    });
  };
  return {
    run,
    setRun,
    npc,
    setNpc,
    busy,
    error,
    setError,
    connected,
    status,
    setStatus,
    attempt,
    connect,
    create,
    refresh,
    select,
    base: run ? base(run) : "",
  };
}
export type TestRun = ReturnType<typeof useTestRun>;
