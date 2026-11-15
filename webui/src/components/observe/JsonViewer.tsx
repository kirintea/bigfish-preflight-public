// JSON inspector with formatting and clipboard actions.
import { useState } from "react";
import { Copy } from "lucide-react";
export function JsonViewer({ value }: { value: unknown }) {
  const [formatted, setFormatted] = useState(true);
  const [copied, setCopied] = useState(false);
  let text: string;
  try {
    text = JSON.stringify(value ?? null, null, formatted ? 2 : undefined);
  } catch {
    text = String(value);
  }
  return (
    <div className="json-view">
      <div className="json-tools">
        <div className="segmented">
          <button
            className={formatted ? "active" : ""}
            onClick={() => setFormatted(true)}
          >
            格式化
          </button>
          <button
            className={!formatted ? "active" : ""}
            onClick={() => setFormatted(false)}
          >
            原始
          </button>
        </div>
        <button
          title={copied ? "已复制" : "复制 JSON"}
          aria-label="复制 JSON"
          className="icon"
          onClick={() =>
            navigator.clipboard?.writeText(text).then(() => setCopied(true))
          }
        >
          <Copy size={14} />
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}
