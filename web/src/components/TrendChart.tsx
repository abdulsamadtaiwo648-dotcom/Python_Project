import { useEffect, useRef } from "react";
import type { Bucket } from "../analytics";

const compact = (v: number) => "₦" + new Intl.NumberFormat("en-NG", { notation: "compact", maximumFractionDigits: 1 }).format(v);

/** Income vs expenses bars, drawn on a canvas so it stays crisp at any width. */
export default function TrendChart({ buckets, limit }: { buckets: Bucket[]; limit: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const data = buckets.slice(-limit);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const box = canvas.getBoundingClientRect();
      const width = Math.floor(box.width), height = Math.floor(box.height) || 224;
      if (width < 20) return;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * scale);
      canvas.height = Math.floor(height * scale);
      const c = canvas.getContext("2d");
      if (!c) return;
      c.setTransform(scale, 0, 0, scale, 0, 0);
      c.clearRect(0, 0, width, height);
      if (!data.length) {
        c.fillStyle = "#64748b"; c.font = "13px Inter, system-ui, sans-serif"; c.textAlign = "center";
        c.fillText("No sales or expense data for this period yet.", width / 2, height / 2);
        return;
      }
      const pad = { top: 12, right: 12, bottom: 36, left: 48 };
      const pw = width - pad.left - pad.right, ph = height - pad.top - pad.bottom;
      const max = Math.max(1, ...data.flatMap((d) => [d.sales, d.expenses]));
      c.font = "12px Inter, system-ui, sans-serif"; c.textAlign = "right"; c.textBaseline = "middle";
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + ph - (ph * i) / 4;
        c.strokeStyle = "#f1f5f9"; c.lineWidth = 1; c.beginPath(); c.moveTo(pad.left, y); c.lineTo(width - pad.right, y); c.stroke();
        c.fillStyle = "#94a3b8"; c.fillText(compact((max * i) / 4), pad.left - 7, y);
      }
      const slot = pw / data.length, bw = Math.min(10, slot * 0.3);
      const bar = (x: number, y: number, w: number, h: number) => {
        if (h <= 0) return;
        const r = Math.min(4, w / 2, h);
        c.beginPath();
        if (c.roundRect) c.roundRect(x, y, w, h, [r, r, r, r]); else c.rect(x, y, w, h);
        c.fill();
      };
      data.forEach((d, i) => {
        const cx = pad.left + slot * (i + 0.5);
        const sh = Math.max(0, (d.sales / max) * ph), eh = Math.max(0, (d.expenses / max) * ph);
        c.fillStyle = "#1d4ed8"; bar(cx - bw - 1.5, pad.top + ph - sh, bw, sh);
        c.fillStyle = "#cbd5e1"; bar(cx + 1.5, pad.top + ph - eh, bw, eh);
        c.fillStyle = "#64748b"; c.textAlign = "center"; c.textBaseline = "top";
        c.fillText(d.label, cx, pad.top + ph + 9, slot - 2);
      });
    };
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [data]);

  const summary = data.length
    ? data.map((d) => `${d.label}: sales ${compact(d.sales)}, expenses ${compact(d.expenses)}`).join(". ")
    : "No sales or expense data for this period yet.";
  return (
    <>
      <canvas ref={ref} id="analytics-trend-chart" className="block h-64 w-full sm:h-80" aria-label="Sales and expenses trend chart" />
      <p className="sr-only" aria-live="polite">{summary}</p>
    </>
  );
}
