import { Plus, Trash2, RotateCcw, Send } from "lucide-react";
import { useState } from "react";
export const domainNames: Record<string, string> = {
  world: "世界",
  body: "身体状态",
  needs: "身体与需求",
  social: "关系与性格",
  activity: "任务与行动",
  environment: "环境",
  resources: "资源与物品",
  groups: "群体",
  production: "生产",
  events: "事件与知识",
  conversation: "会话",
  hooks: "Hooks",
  action_result: "动作结果",
};
const labels: Record<string, string> = {
  tick: "模拟 tick",
  speed: "时间倍率",
  pause_reasons: "暂停原因",
  scene: "场景",
  present: "在场",
  awake: "清醒",
  downed: "倒地",
  can_move: "可移动",
  can_speak: "可说话",
  conditions: "身体状况",
  hunger: "饥饿程度",
  fatigue: "疲劳程度",
  rest: "休息充足程度",
  mood: "心情",
  influences: "心情影响",
  personality_ref: "性格预设 ID",
  eligible: "发言资格",
  cooldown_until_tick: "冷却截止 tick",
  opinions: "方向关系",
  target_id: "对象 ID",
  value: "数值",
  relationship: "关系",
  basis_event_ids: "依据事件 ID",
  task_id: "任务 ID",
  phase: "阶段",
  target_kind: "目标类型",
  progress: "进度",
  schedule: "日程",
  interruption_reason: "中断原因",
  weather: "天气",
  temperature_c: "温度 °C",
  positions: "角色位置",
  locations: "地点",
  npc_id: "NPC ID",
  location_id: "地点 ID",
  x_m: "X (m)",
  y_m: "Y (m)",
  distance_m: "距离 (m)",
  reachable: "可达",
  arrived: "已到达",
  visible_to: "可见角色 ID",
  blocked: "阻挡",
  items: "物品",
  item_id: "物品 ID",
  quantity: "数量",
  owner_id: "所有者 ID",
  holder_id: "持有者 ID",
  reservations: "预约",
  reservation_id: "预约 ID",
  groups: "群体",
  group_id: "群体 ID",
  members: "成员 ID",
  roles: "成员职责",
  orders: "生产订单",
  facilities: "设施",
  crops: "作物",
  order_id: "订单 ID",
  status: "状态",
  missing_materials: "缺少材料 ID",
  facility_id: "设施 ID",
  crop_id: "作物 ID",
  growth: "生长进度",
  events: "事件",
  event_id: "事件 ID",
  fact: "事实 / 传闻",
  kind: "信息类型",
  actor: "作者 ID",
  targets: "指向对象 ID",
  observers: "观察者 ID",
  actual_recipients: "实际接收者 ID",
  source: "来源",
  source_event_id: "来源事件 ID",
  occurred_at_tick: "发生 tick",
  observed_at_tick: "观察 tick",
  certainty: "确信度",
  start_tick: "开始 tick",
  end_tick: "结束 tick",
  activity: "活动",
  name: "名称",
  stage: "阶段",
  severity: "严重程度",
};
export type JsonSchema = Record<string, any>;
function resolved(schema: JsonSchema, defs: JsonSchema): JsonSchema {
  if (schema.$ref) return resolved(defs[schema.$ref.split("/").pop()!], defs);
  if (schema.anyOf)
    return resolved(
      schema.anyOf.find((s: JsonSchema) => s.type !== "null") ||
        schema.anyOf[0],
      defs,
    );
  return schema;
}
function createValue(schema: JsonSchema, defs: JsonSchema): any {
  const spec = resolved(schema, defs);
  if (spec.default !== undefined && spec.default !== null) return spec.default;
  if (spec.enum) return spec.enum[0];
  if (spec.type === "object")
    return Object.fromEntries(
      (spec.required || []).map((key: string) => [
        key,
        createValue(spec.properties[key], defs),
      ]),
    );
  if (spec.type === "array") return [];
  if (spec.type === "boolean") return false;
  if (spec.type === "number" || spec.type === "integer")
    return spec.minimum || 0;
  return "";
}
function Field({
  name,
  schema,
  defs,
  value,
  onChange,
  path,
}: {
  name: string;
  schema: JsonSchema;
  defs: JsonSchema;
  value: any;
  onChange: (v: any) => void;
  path: string;
}) {
  const spec = resolved(schema, defs);
  const label = labels[name] || name;
  const known = value !== undefined && value !== null;
  const defaultValue = () =>
    spec.type === "array"
      ? []
      : spec.type === "object"
        ? {}
        : spec.type === "boolean"
          ? false
          : spec.type === "number" || spec.type === "integer"
            ? 0
            : spec.enum?.[0] || "";
  return (
    <div className={`field ${spec.type === "array" ? "collection" : ""}`}>
      <div className="field-label">
        <label htmlFor={path}>{label}</label>
        <button
          className="known-toggle"
          title={known ? "设为未知" : "设置字段"}
          onClick={() => onChange(known ? undefined : defaultValue())}
        >
          {known ? "已设置" : "unknown"}
        </button>
      </div>
      {known &&
        (spec.enum ? (
          <select
            id={path}
            aria-label={label}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          >
            {spec.enum.map((v: string) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        ) : spec.type === "boolean" ? (
          <input
            id={path}
            aria-label={label}
            type="checkbox"
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
          />
        ) : spec.type === "number" || spec.type === "integer" ? (
          <>
            <input
              id={path}
              aria-label={label}
              type="number"
              step={spec.type === "integer" ? 1 : 0.05}
              min={spec.minimum}
              max={spec.maximum}
              value={value}
              onChange={(e) =>
                onChange(
                  e.target.value === "" ? undefined : Number(e.target.value),
                )
              }
            />
            {spec.minimum === 0 && spec.maximum === 1 && (
              <small>
                {name === "rest"
                  ? "0 缺乏休息 → 1 充分休息"
                  : name === "mood"
                    ? "0 低落 → 1 愉快"
                    : "0 低 → 1 高"}
              </small>
            )}
          </>
        ) : spec.type === "array" ? (
          <div className="array-fields">
            {(value as any[]).map((item, index) => (
              <div className="array-row" key={index}>
                <div className="array-index">
                  {String(index + 1).padStart(2, "0")}
                  <button
                    className="icon"
                    aria-label={`删除${label}${index + 1}`}
                    onClick={() =>
                      onChange(value.filter((_: any, i: number) => i !== index))
                    }
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                {resolved(spec.items, defs).type === "object" ? (
                  <Fields
                    schema={resolved(spec.items, defs)}
                    defs={defs}
                    value={item}
                    onChange={(v) =>
                      onChange(
                        value.map((a: any, i: number) => (i === index ? v : a)),
                      )
                    }
                    path={`${path}-${index}`}
                  />
                ) : (
                  <input
                    aria-label={`${label}${index + 1}`}
                    value={item}
                    onChange={(e) =>
                      onChange(
                        value.map((a: any, i: number) =>
                          i === index ? e.target.value : a,
                        ),
                      )
                    }
                  />
                )}
              </div>
            ))}
            <button
              className="text-button"
              onClick={() =>
                onChange([...value, createValue(spec.items, defs)])
              }
            >
              <Plus size={14} />
              添加{label}
            </button>
          </div>
        ) : spec.type === "object" ? (
          <div className="record-fields">
            {Object.entries(value).map(([key, entry], index) => (
              <div className="record-row" key={index}>
                <input
                  aria-label={`${label}角色${index + 1}`}
                  value={key}
                  onChange={(e) =>
                    onChange(
                      Object.fromEntries(
                        Object.entries(value).map(([k, v], i) => [
                          i === index ? e.target.value : k,
                          v,
                        ]),
                      ),
                    )
                  }
                />
                <input
                  aria-label={`${label}职责${index + 1}`}
                  value={String(entry)}
                  onChange={(e) =>
                    onChange({ ...value, [key]: e.target.value })
                  }
                />
                <button
                  className="icon"
                  aria-label={`删除职责${index + 1}`}
                  onClick={() => {
                    const next = { ...value };
                    delete next[key];
                    onChange(next);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <button
              className="text-button"
              onClick={() =>
                onChange({
                  ...value,
                  [`npc-${Object.keys(value).length + 1}`]: "",
                })
              }
            >
              <Plus size={14} />
              添加职责
            </button>
          </div>
        ) : (
          <input
            id={path}
            aria-label={label}
            maxLength={spec.maxLength || 4096}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        ))}
      {!known && (
        <button
          className="unknown-field"
          aria-label={`设置${label}`}
          onClick={() => onChange(defaultValue())}
        >
          未上报
        </button>
      )}
    </div>
  );
}
function Fields({
  schema,
  defs,
  value,
  onChange,
  path,
}: {
  schema: JsonSchema;
  defs: JsonSchema;
  value: any;
  onChange: (v: any) => void;
  path: string;
}) {
  return (
    <div className="fields">
      {Object.entries(schema.properties || {}).map(([name, spec]) => (
        <Field
          key={name}
          name={name}
          schema={spec as JsonSchema}
          defs={defs}
          value={value[name]}
          path={`${path}-${name}`}
          onChange={(v) => {
            const next = { ...value };
            if (v === undefined) delete next[name];
            else next[name] = v;
            onChange(next);
          }}
        />
      ))}
    </div>
  );
}
export function DomainEditor({
  domain,
  schema,
  draft,
  confirmed,
  onChange,
  onSubmit,
  onRestore,
  busy,
}: {
  domain: string;
  schema: JsonSchema;
  draft: any;
  confirmed: any;
  onChange: (v: any) => void;
  onSubmit: () => void;
  onRestore: () => void;
  busy: boolean;
}) {
  const [showConfirmed, setShowConfirmed] = useState(false);
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">STATE INPUT / {domain.toUpperCase()}</span>
          <h2>{domainNames[domain]}</h2>
        </div>
        <span className="badge amber">
          {JSON.stringify(draft) === JSON.stringify(confirmed)
            ? "已同步"
            : "未提交草稿"}
        </span>
      </div>
      <Fields
        schema={schema}
        defs={schema.$defs || {}}
        value={draft}
        onChange={onChange}
        path={domain}
      />
      <div className="editor-actions">
        <button onClick={onRestore}>
          <RotateCcw size={15} />
          恢复确认值
        </button>
        <button className="primary" disabled={busy} onClick={onSubmit}>
          <Send size={15} />
          提交{domainNames[domain]}
        </button>
      </div>
      <button
        className="text-button"
        onClick={() => setShowConfirmed(!showConfirmed)}
      >
        服务端确认值
      </button>
      <pre
        data-testid={`${domain}-confirmed`}
        className={showConfirmed ? "confirmed" : "confirmed condensed"}
      >
        {confirmed && Object.keys(confirmed).length
          ? JSON.stringify(confirmed, null, 2)
          : "unknown · 尚未上报"}
      </pre>
    </>
  );
}
