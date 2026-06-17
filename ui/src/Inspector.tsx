import { useEffect, useState } from "react";
import { api } from "./api/client";
import { JobBadge, ProgressBar } from "./components";
import { Icon } from "./icons";
import type { Job } from "./api/types";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

function elapsed(job: Job): string {
  const start = job.started_at || job.created_at;
  if (!start) return "—";
  const startMs = Date.parse(start);
  if (Number.isNaN(startMs)) return "—";
  const endMs = job.finished_at ? Date.parse(job.finished_at) : Date.now();
  const secs = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

// Right-side inspector: current job, live activity stream, progress, elapsed
// time, and result/decision. Driven by the polled job list so it stays live.
export function Inspector({ job, onClose }: { job: Job | null; onClose?: () => void }) {
  // Re-render once a second so the elapsed clock ticks while a job runs.
  const [, setTick] = useState(0);
  const active = !!job && !TERMINAL.has(job.status);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [active]);

  return (
    <aside className="inspector">
      <div className="inspector-head">
        <span>Inspector</span>
        {onClose ? (
          <button className="icon-btn small" title="Hide inspector" onClick={onClose}>
            <Icon name="x" size={14} />
          </button>
        ) : null}
      </div>

      {!job ? (
        <div className="inspector-body">
          <div className="empty-state compact">
            <div className="empty-state-icon"><Icon name="logs" size={22} /></div>
            <div className="empty-state-title">No active job</div>
            <div className="empty-state-desc">
              Start a research run, optimization, or smoke test and live progress will appear here.
            </div>
          </div>
        </div>
      ) : (
        <div className="inspector-body">
          <div className="insp-job-title">{job.title}</div>
          <div className="insp-meta">
            <JobBadge status={job.status} />
            <span className="insp-elapsed">
              <Icon name="refresh" size={12} /> {elapsed(job)}
            </span>
          </div>

          <div style={{ margin: "12px 0 6px" }}>
            <ProgressBar value={job.progress} />
          </div>
          {job.message ? <div className="insp-step">{job.message}</div> : null}

          {active ? (
            <button className="btn ghost full" onClick={() => api.cancelJob(job.id).catch(() => undefined)}>
              <Icon name="x" size={14} /> Cancel job
            </button>
          ) : null}

          {job.error ? <div className="err" style={{ marginTop: 10 }}>⚠ {job.error}</div> : null}

          <div className="inspector-sub" style={{ marginTop: 16 }}>Live activity</div>
          <div className="activity-stream">
            {job.logs.length === 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>Waiting for the first step…</div>
            ) : (
              job.logs.slice(-50).map((line, i, arr) => (
                <div key={i} className={`activity-line ${i === arr.length - 1 && active ? "current" : ""}`}>
                  <span className="activity-dot" />
                  <span>{line}</span>
                </div>
              ))
            )}
          </div>

          {job.result ? (
            <div style={{ marginTop: 14 }}>
              <div className="inspector-sub">Result</div>
              <pre className="pre">{JSON.stringify(job.result, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      )}
    </aside>
  );
}
