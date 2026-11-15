export type Actor = {
  x: number;
  y: number;
  template: string;
  name: string;
  mode: string;
  personality: string;
  hunger: number;
  mood: number;
  path: number[][];
  goal: number[] | null;
  facing: string;
  speech: {
    id: string;
    text: string;
    status: string;
    delivered_at: number | null;
  } | null;
};
export type BeachObject = {
  x: number;
  y: number;
  kind: string;
  remaining: number;
  radius: number;
};
export type BeachState = {
  revision: number;
  run_epoch: string;
  test_run_id: string;
  tick: number;
  checkpoint: string;
  seed: number;
  actors: Record<string, Actor>;
  objects: Record<string, BeachObject>;
  inventory: { berry: number; wood: number; shell: number };
  pause_reasons: string[];
  dialogue: string | null;
  messages: any[];
  last_action: string | null;
  model?: string;
};
