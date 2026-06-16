import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Card, PageHead, Stat, StatusBadge } from "../components";
import type { ScreenId } from "../App";
import type { Job } from "../api/types";

export function Dashboard({ jobs, onGo }: { jobs: Job[]; onGo: (s: ScreenId) => void }) {
  const session = useAsync(() => api.session().catch(() => null), []);
  const runs = useAsync(() => api.runs().catch(() => null), []);
  const board = useAsync(() => api.leaderboard().catch(() => null), []);

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const lastRun = runs.data?.runs?.[0];
  const best = board.data?.runs?.find((r) => r.pass_fail === "PASS") || board.data?.runs?.[0];

  return (
    <div>
      <PageHead title="Dashboard" subtitle="Your MT5 research at a glance. Strategy Tester only — no live trading." />

      <div className="card-grid">
        <Stat
          label="Research session"
          value={<StatusBadge status={session.data?.session_active ? "PASS" : "neutral"} />}
        />
        <Stat label="Active jobs" value={active.length} />
        <Stat label="Stored runs" value={runs.data?.count ?? "—"} />
        <Stat label="MT5 process" value={session.data?.process_running ? "running" : "idle"} />
      </div>

      <Card title="Active research jobs">
        {active.length === 0 ? (
          <div className="muted" style={{ fontSize: 13 }}>
            No active jobs. <button className="btn ghost" onClick={() => onGo("workspace")}>Start research</button>{" "}
            or <button className="btn ghost" onClick={() => onGo("onboarding")}>run a first smoke test</button>.
          </div>
        ) : (
          <table>
            <tbody>
              {active.map((j) => (
                <tr key={j.id}>
                  <td>{j.title}</td>
                  <td><StatusBadge status={j.status} /></td>
                  <td className="muted">{Math.round(j.progress * 100)}%</td>
                  <td className="muted">{j.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="card-grid">
        <Card title="Last run">
          {lastRun ? (
            <div className="kv">
              <div className="k">Test ID</div>
              <div className="mono row-click" onClick={() => onGo("runs")}>{lastRun.test_id}</div>
              <div className="k">Status</div>
              <div><StatusBadge status={lastRun.run_status} /></div>
            </div>
          ) : <div className="muted" style={{ fontSize: 13 }}>No runs yet.</div>}
        </Card>
        <Card title="Best candidate">
          {best ? (
            <div className="kv">
              <div className="k">Test ID</div>
              <div className="mono row-click" onClick={() => onGo("leaderboard")}>{best.test_id}</div>
              <div className="k">Pass/Fail</div>
              <div><StatusBadge status={best.pass_fail} /></div>
            </div>
          ) : <div className="muted" style={{ fontSize: 13 }}>No leaderboard entries yet.</div>}
        </Card>
      </div>
    </div>
  );
}
