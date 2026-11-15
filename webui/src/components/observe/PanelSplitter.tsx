// Resizable panel divider with pointer and keyboard controls.
import { useRef } from "react";
export function PanelSplitter({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const start = useRef({ x: 0, width: 0 });
  const update = (v: number) => onChange(Math.max(280, Math.min(560, v)));
  return (
    <div
      role="separator"
      aria-label="调整上下文面板宽度"
      aria-orientation="vertical"
      aria-valuenow={value}
      aria-valuemin={280}
      aria-valuemax={560}
      tabIndex={0}
      className="splitter"
      onDoubleClick={() => update(360)}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, width: value };
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId))
          update(start.current.width + start.current.x - e.clientX);
      }}
      onPointerUp={(e) => e.currentTarget.releasePointerCapture(e.pointerId)}
      onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          update(
            e.key === "Home"
              ? 560
              : e.key === "End"
                ? 280
                : value + (e.key === "ArrowLeft" ? 24 : -24),
          );
        }
      }}
    />
  );
}
