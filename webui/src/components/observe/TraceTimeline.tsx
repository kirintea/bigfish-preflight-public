import { Check, Circle, AlertCircle } from "lucide-react";
import { JsonViewer } from "./JsonViewer";
export function TraceTimeline({ trace }: { trace: any }) {
  if (!trace) return <div className="empty compact">暂无请求记录</div>;
  return (
    <div className="timeline">
      {trace.reason && (
        <div className="empty compact">
          {trace.reason === "no_record_or_trimmed"
            ? "无记录或记录已裁剪"
            : "链路暂时不可用"}
        </div>
      )}
      {(trace.stages || []).map((stage: any, i: number) => (
        <div className="stage" key={i}>
          {stage.status === "rejected" ? (
            <AlertCircle size={15} />
          ) : stage.status === "ok" ? (
            <Check size={15} />
          ) : (
            <Circle size={12} />
          )}
          <div>
            <strong>{stage.stage}</strong>
            <small>
              {stage.status} · {stage.reason || "—"}
            </small>
          </div>
          <span>
            {stage.duration_ms != null
              ? `${Number(stage.duration_ms).toFixed(1)} ms`
              : ""}
          </span>
        </div>
      ))}
      <details>
        <summary>请求详情</summary>
        <JsonViewer value={trace} />
      </details>
    </div>
  );
}
