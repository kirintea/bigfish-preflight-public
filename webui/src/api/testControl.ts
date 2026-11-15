import { client, id } from "./client";
export type World = {
  test_run_id: string;
  world_id: string;
  run_epoch: string;
  revision: number;
  npc_ids: string[];
  name: string;
  tick: number | null;
  domain_states: Record<
    string,
    Record<string, { data: Record<string, any>; revision: number }>
  >;
  source_sequences: Record<string, number>;
  saved_scenarios: Record<string, any>;
  chat_sessions: Record<string, any>;
  scenario_replay: { cursor?: number; scenario?: any; results?: any[] };
};
export const base = (run: Pick<World, "test_run_id">) =>
  `/api/test/v1/runs/${run.test_run_id}`;
export const testControl = {
  create: () =>
    client.post<World>("/api/test/v1/runs", {
      name: `海岸测试 ${new Date().toLocaleTimeString()}`,
      npc_ids: ["npc-bigfish", "npc-claude"],
    }),
  state: (run: Pick<World, "test_run_id">) =>
    client.get<World>(base(run) + "/state"),
  context: (run: World, npc: string) =>
    client.get(base(run) + `/npcs/${npc}/context`),
};
export function report(
  run: World,
  domain: string,
  entity: string,
  payload: unknown,
  revision = run.revision,
) {
  const sourceKey = JSON.stringify([
    "test",
    run.test_run_id,
    domain,
    entity,
  ]).replaceAll(", ", ",");
  // Python's sequence keys use the standard JSON separators with a space.
  const sequence =
    Object.entries(run.source_sequences).find(([key]) => {
      try {
        return JSON.stringify(JSON.parse(key)) === sourceKey;
      } catch {
        return false;
      }
    })?.[1] || 0;
  return {
    schema_version: 1,
    report_id: id(),
    request_id: id(),
    world_id: run.world_id,
    run_epoch: run.run_epoch,
    domain,
    entity_id: entity,
    source_kind: "test",
    source_id: run.test_run_id,
    sequence: sequence + 1,
    expected_revision: revision,
    mode: "snapshot",
    occurred_at_tick: run.tick || 0,
    observed_at_tick: run.tick || 0,
    payload,
  };
}
