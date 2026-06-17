import type { ReactNode } from "react";
import type { LongShort, Verdict, VerdictCode } from "./api/types";

const VERDICT_TONE: Record<VerdictCode, string> = {
  GOOD: "good",
  PROMISING: "info",
  WEAK: "warn",
  REJECT: "bad",
  INFRA_ONLY: "neutral",
};

export function VerdictBadge({ verdict, large }: { verdict: Verdict; large?: boolean }) {
  return (
    <span className={`verdict-badge ${VERDICT_TONE[verdict.code]} ${large ? "large" : ""}`}>
      {verdict.label}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: "high" | "medium" | "low" }) {
  return <span className={`confidence-badge ${confidence}`}>{confidence} confidence</span>;
}

export function MetricCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "good" | "bad" | "warn" | "neutral";
}) {
  return (
    <div className={`metric-card ${tone ?? ""}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  );
}

export function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return Number(value.toFixed(digits)).toString();
}

// Horizontal target bar: fill is the value position relative to `max`; a marker
// line shows the threshold. `lowerIsBetter` flips the pass colour (e.g. for DD).
export function ThresholdBar({
  value,
  threshold,
  max,
  lowerIsBetter,
}: {
  value: number | null;
  threshold: number;
  max: number;
  lowerIsBetter?: boolean;
}) {
  if (value === null) return <div className="threshold-bar empty">no data</div>;
  const pct = Math.max(2, Math.min(100, (value / max) * 100));
  const markPct = Math.max(0, Math.min(100, (threshold / max) * 100));
  const pass = lowerIsBetter ? value <= threshold : value >= threshold;
  return (
    <div className="threshold-bar">
      <div className={`threshold-fill ${pass ? "pass" : "fail"}`} style={{ width: `${pct}%` }} />
      <div className="threshold-mark" style={{ left: `${markPct}%` }} title={`target ${threshold}`} />
    </div>
  );
}

// Long vs short trade COUNTS (per-side P&L needs trade-level deals, which the
// summary report doesn't carry — so this never claims per-side profit).
export function LongShortBar({ data }: { data: LongShort }) {
  const longs = data.long_trades ?? 0;
  const shorts = data.short_trades ?? 0;
  const total = longs + shorts;
  if (!data.available || total === 0) {
    return <div className="muted" style={{ fontSize: 12.5 }}>Long/short counts unavailable for this report.</div>;
  }
  const longPct = (longs / total) * 100;
  return (
    <div>
      <div className="split-bar">
        <div className="split-seg long" style={{ width: `${longPct}%` }}>{longs > 0 ? "Long" : ""}</div>
        <div className="split-seg short" style={{ width: `${100 - longPct}%` }}>{shorts > 0 ? "Short" : ""}</div>
      </div>
      <div className="split-legend muted">
        <span>Long: {longs} ({fmt(data.long_share_pct, 0)}%)</span>
        <span>Short: {shorts} ({fmt(data.short_share_pct, 0)}%)</span>
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
        Counts only — per-side profit needs trade-level deals.
      </div>
    </div>
  );
}

// A small "data not available" panel used wherever trade-level charts would go.
export function UnavailablePanel({ title, note }: { title: string; note: string }) {
  return (
    <div className="unavailable-panel">
      <div className="unavailable-title">{title}</div>
      <div className="unavailable-note">{note}</div>
    </div>
  );
}
