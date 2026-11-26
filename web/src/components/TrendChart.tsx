import { useEffect, useRef } from "react";
import type { Bucket } from "../analytics";

const compact = (v: number) => "₦" + new Intl.NumberFormat("en-NG", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export const SERIES_COLORS = { sales: "#1d4ed8", moneyIn: "#059669", expenses: "#cbd5e1", net: "#0f172a" };

/**
 * Sales, money in and expenses as bars, and net cash flow (sales + money in − expenses) as a line.
 * The scale goes below zero when a period has a loss.
 */
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
        c.fillText("No sales, money in or expenses for this period yet.", width / 2, height / 2);
        return;
      }
      const pad = { top: 12, right: 12, bottom: 36, left: 56 };
      const pw = width - pad.left - pad.right, ph = height - pad.top - pad.bottom;
      const hi = Math.max(1, ...data.flatMap((d) => [d.sales, d.moneyIn, d.expenses, d.net]));
      const lo = Math.min(0, ...data.map((d) => d.net));
      const span = hi - lo;
      const yOf = (v: number) => pad.top + (ph * (hi - v)) / span;
      const zero = yOf(0);

      c.font = "12px Inter, system-ui, sans-serif"; c.textAlign = "right"; c.textBaseline = "middle";
      for (let i = 0; i <= 4; i++) {
        const value = lo + (span * i) / 4;
        const y = yOf(value);
        c.strokeStyle = "#f1f5f9"; c.lineWidth = 1; c.beginPath(); c.moveTo(pad.left, y); c.lineTo(width - pad.right, y); c.stroke();
        c.fillStyle = "#94a3b8"; c.fillText(compact(value), pad.left - 7, y);
      }
      const slot = pw / data.length, bw = Math.min(8, slot * 0.2);
      const bar = (x: number, value: number) => {
        const top = yOf(value), h = Math.abs(zero - top);
        if (h <= 0) return;
        const r = Math.min(3, bw / 2, h);
        c.beginPath();
        const y = Math.min(zero, top);
        if (c.roundRect) c.roundRect(x, y, bw, h, [r, r, r, r]); else c.rect(x, y, bw, h);
        c.fill();
      };
      data.forEach((d, i) => {
        const cx = pad.left + slot * (i + 0.5);
        c.fillStyle = SERIES_COLORS.sales; bar(cx - bw - 2, d.sales);
        c.fillStyle = SERIES_COLORS.moneyIn; bar(cx, d.moneyIn);
        c.fillStyle = SERIES_COLORS.expenses; bar(cx + bw + 2, d.expenses);
        c.fillStyle = "#64748b"; c.textAlign = "center"; c.textBaseline = "top";
        c.fillText(d.label, cx, pad.top + ph + 9, slot - 2);
      });
      // Net cash flow: a line across the buckets, with a dot at each.
      c.strokeStyle = SERIES_COLORS.net; c.lineWidth = 2; c.beginPath();
      data.forEach((d, i) => {
        const x = pad.left + slot * (i + 0.5), y = yOf(d.net);
        if (i === 0) c.moveTo(x, y); else c.lineTo(x, y);
      });
      c.stroke();
      data.forEach((d, i) => {
        const x = pad.left + slot * (i + 0.5), y = yOf(d.net);
        c.fillStyle = SERIES_COLORS.net; c.beginPath(); c.arc(x, y, 3, 0, Math.PI * 2); c.fill();
      });
    };
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [data]);

  const summary = data.length
    ? data.map((d) => `${d.label}: sales ${compact(d.sales)}, money in ${compact(d.moneyIn)}, expenses ${compact(d.expenses)}, net ${compact(d.net)}`).join(". ")
    : "No sales, money in or expenses for this period yet.";
  return (
    <>
      <canvas ref={ref} id="analytics-trend-chart" className="block h-64 w-full sm:h-80" aria-label="Sales, money in, expenses and net cash flow chart" />
      <p className="sr-only" aria-live="polite">{summary}</p>
    </>
  );
}
