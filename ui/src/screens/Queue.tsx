import { api } from "../api/client";
import { Card, EmptyState, JobBadge, PageHead, ProgressBar } from "../components";
import type { Job } from "../api/types";

// Runs / Queue: live view of every job (queued/running/done/failed). Driven by
// the polled job list, so it updates while MT5 work runs without freezing.
export function Queue({ jobs, onSelect }: { jobs: Job[]; onSelect: (id: string) => void }) {
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");

  return (
    <div>
      <PageHead title="Runs / Queue" subtitle="Every job, live. Long MT5 tests run asynchronously — the app never freezes." />
      {active.length > 0 ? (
        <div className="notice">{active.length} job(s) running or queued. The UI stays responsive.</div>
      ) : null}
      <Card>
        {jobs.length === 0 ? (
          <EmptyState
            icon="runs"
            title="No jobs yet"
            description="Smoke tests, optimizations, and research runs appear here with live progress. Start one from the Agent or Setup tab."
          />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Type</th>
                <th>Status</th>
                <th style={{ width: 160 }}>Progress</th>
                <th>Message</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="row-click" onClick={() => onSelect(j.id)}>
                  <td>{j.title}</td>
                  <td className="muted">{j.type}</td>
                  <td><JobBadge status={j.status} /></td>
                  <td><ProgressBar value={j.progress} /></td>
                  <td className="muted">{j.message || "—"}</td>
                  <td>
                    {j.status === "queued" || j.status === "running" ? (
                      <button
                        className="btn ghost"
                        onClick={(e) => {
                          e.stopPropagation();
                          api.cancelJob(j.id).catch(() => undefined);
                        }}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
