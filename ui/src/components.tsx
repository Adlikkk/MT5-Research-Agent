import type { ReactNode } from "react";

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="card">
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export function PassFail({ value }: { value: string }) {
  const pass = value === "PASS";
  return <span className={`badge ${pass ? "pass" : "fail"}`}>{value}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const good = ["PASS", "REPORT_FOUND", "ok", "OPTIMIZATION_PARSED"].includes(status);
  const bad = ["FAIL", "PROCESS_FAILED", "REPORT_MISSING", "TERMINAL_ALREADY_RUNNING"].includes(status);
  const cls = good ? "pass" : bad ? "fail" : "neutral";
  return <span className={`badge ${cls}`}>{status || "-"}</span>;
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  textarea,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  textarea?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {textarea ? (
        <textarea value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input type="text" value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

export function Spinner() {
  return <div className="spinner">Loading…</div>;
}

export function ErrorLine({ message }: { message: string }) {
  return <div className="err">⚠ {message}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>;
}

export function PageHead({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="page-head">
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </div>
  );
}

export function JobBadge({ status }: { status: string }) {
  const cls = status === "succeeded" ? "pass" : status === "failed" ? "fail" : "neutral";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function ProgressBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="progress">
      <div className="progress-fill" style={{ width: `${pct}%` }} />
      <span className="progress-label">{pct}%</span>
    </div>
  );
}
