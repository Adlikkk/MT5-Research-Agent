import { api } from "./api/client";
import { JobBadge, ProgressBar } from "./components";
import type { Job } from "./api/types";

// Right-side inspector: shows the current/active job, its live progress, logs,
// and result/decision. Driven by the polled job list so it stays live.
export function Inspector({ job }: { job: Job | null }) {
  if (!job) {
    return (
      <aside className="inspector">
        <div className="inspector-head">Inspector</div>
        <div className="empty">No active job. Start a smoke test, optimization, or research run.</div>
      </aside>
    );
  }

  const active = !["succeeded", "failed", "cancelled"].includes(job.status);

  return (
    <aside className="inspector">
      <div className="inspector-head">Inspector</div>
      <div className="inspector-body">
        <div className="kv">
          <div className="k">Job</div>
          <div>{job.title}</div>
          <div className="k">Status</div>
          <div><JobBadge status={job.status} /></div>
        </div>
        <div style={{ margin: "12px 0" }}>
          <ProgressBar value={job.progress} />
        </div>
        {job.message ? <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{job.message}</div> : null}
        {active ? (
          <button className="btn ghost" onClick={() => api.cancelJob(job.id).catch(() => undefined)}>
            Cancel job
          </button>
        ) : null}

        {job.error ? <div className="err" style={{ marginTop: 10 }}>⚠ {job.error}</div> : null}

        {job.result ? (
          <div style={{ marginTop: 14 }}>
            <div className="inspector-sub">Result</div>
            <pre className="pre">{JSON.stringify(job.result, null, 2)}</pre>
          </div>
        ) : null}

        <div style={{ marginTop: 14 }}>
          <div className="inspector-sub">Activity ({job.logs.length})</div>
          <div className="log-stream">
            {job.logs.length === 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>No log lines yet.</div>
            ) : (
              job.logs.slice(-40).map((line, i) => (
                <div key={i} className="log-line">{line}</div>
              ))
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
