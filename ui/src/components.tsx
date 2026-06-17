import type { ReactNode } from "react";
import type { AsyncState } from "./hooks";
import { Icon, type IconName } from "./icons";

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

// Rich empty / call-to-action state used across screens so no screen ever shows
// a bare error or a blank panel.
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon ? (
        <div className="empty-state-icon">
          <Icon name={icon} size={26} />
        </div>
      ) : null}
      <div className="empty-state-title">{title}</div>
      {description ? <div className="empty-state-desc">{description}</div> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}

// Wraps an async fetch so loading / backend-starting / error / empty states are
// rendered consistently — the key guard against raw "Failed to fetch" surfacing
// as a page's main content.
export function AsyncBoundary<T>({
  state,
  children,
  isEmpty,
  empty,
  loadingLabel = "Loading…",
}: {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loadingLabel?: string;
}) {
  if (state.loading && state.data === null) {
    return <div className="spinner">{loadingLabel}</div>;
  }
  if (state.error && state.data === null) {
    const starting = state.errorKind === "offline";
    return (
      <div className={`async-fault ${starting ? "starting" : ""}`}>
        <div className="async-fault-title">
          {starting ? "Starting backend…" : "Couldn’t load this view"}
        </div>
        <div className="async-fault-desc">
          {starting
            ? "Waiting for the local research backend to respond. This is normal for a few seconds after launch."
            : state.error}
        </div>
        <button className="btn ghost" onClick={state.reload}>
          <Icon name="refresh" size={15} /> Retry
        </button>
      </div>
    );
  }
  if (state.data !== null) {
    if (isEmpty && empty && isEmpty(state.data)) {
      return <>{empty}</>;
    }
    return <>{children(state.data)}</>;
  }
  return null;
}

// Segmented pill control for in-screen sub-navigation (EA Lab, Parameters).
export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (id: T) => void;
}) {
  return (
    <div className="segmented">
      {options.map((opt) => (
        <button
          key={opt.id}
          className={`segment ${value === opt.id ? "active" : ""}`}
          onClick={() => onChange(opt.id)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export type PillTone = "good" | "warn" | "bad" | "idle";

export function StatusPill({
  icon,
  label,
  value,
  tone = "idle",
  title,
  onClick,
}: {
  icon?: IconName;
  label: string;
  value?: string;
  tone?: PillTone;
  title?: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag className={`status-pill ${tone} ${onClick ? "clickable" : ""}`} title={title} onClick={onClick}>
      <span className={`pill-dot ${tone}`} />
      {icon ? <Icon name={icon} size={14} /> : null}
      <span className="pill-label">{label}</span>
      {value ? <span className="pill-value">{value}</span> : null}
    </Tag>
  );
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
