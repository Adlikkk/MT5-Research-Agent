import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Card, PageHead, Stat, StatusBadge } from "../components";
import { Icon } from "../icons";
import { VerdictBadge, ConfidenceBadge, fmt } from "../report_ui";
import type { ScreenId } from "../App";
import type { Job } from "../api/types";

export function Dashboard({
  jobs,
  onGo,
  onOpenReport,
}: {
  jobs: Job[];
  onGo: (s: ScreenId) => void;
  onOpenReport: (testId: string) => void;
}) {
  const session = useAsync(() => api.session().catch(() => null), []);
  const runs = useAsync(() => api.runs().catch(() => null), []);
  const latest = useAsync(() => api.latestRun().catch(() => null), []);

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const recent = runs.data?.runs?.slice(0, 35) ?? [];
  const mt5Missing = session.data !== null && !session.data?.configured_terminal_path;
  const latestRun = latest.data?.has_run ? latest.data : null;

  return (
    <div>
      <PageHead title="Dashboard" subtitle="Your MT5 research at a glance. Strategy Tester only — no live trading." />

      {mt5Missing ? (
        <div className="warn-card">
          <Icon name="setup" size={18} />
          <div>
            <strong>MetaTrader 5 isn’t configured yet.</strong>
            <div className="muted" style={{ fontSize: 12.5 }}>
              Point the agent at your terminal so it can run Strategy Tester research.
            </div>
          </div>
          <button className="btn" onClick={() => onGo("onboarding")}>Open Setup</button>
        </div>
      ) : null}

      <div className="card-grid">
        <Stat
          label="Research session"
          value={<StatusBadge status={session.data?.session_active ? "PASS" : "neutral"} />}
        />
        <Stat label="Active jobs" value={active.length} />
        <Stat label="Stored runs" value={runs.data?.count ?? "—"} />
        <Stat label="MT5 process" value={session.data?.process_running ? "running" : "idle"} />
      </div>

      <Card title="Latest test">
        {latestRun && latestRun.verdict ? (
          <div>
            <div className="report-header">
              <div>
                <div className="report-title">{latestRun.ea || "—"}</div>
                <div className="report-sub muted">
                  {latestRun.symbol} {latestRun.timeframe} · {latestRun.period || "—"}
                </div>
                <div className="report-sub muted mono">{latestRun.test_id}</div>
              </div>
              <div className="report-badges">
                <VerdictBadge verdict={latestRun.verdict} large />
                <ConfidenceBadge confidence={latestRun.verdict.confidence} />
              </div>
            </div>
            <div className="latest-metrics">
              <span>PF <strong>{fmt(latestRun.metrics?.profit_factor)}</strong></span>
              <span>DD <strong>{latestRun.metrics?.drawdown_pct === null || latestRun.metrics?.drawdown_pct === undefined ? "—" : `${fmt(latestRun.metrics.drawdown_pct)}%`}</strong></span>
              <span>Trades <strong>{latestRun.metrics?.total_trades ?? "—"}</strong></span>
              <span>Return <strong>{latestRun.metrics?.return_pct === null || latestRun.metrics?.return_pct === undefined ? "—" : `${fmt(latestRun.metrics.return_pct)}%`}</strong></span>
            </div>
            {latestRun.decision_reason ? (
              <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{latestRun.decision_reason}</div>
            ) : null}
            <div className="pill-row">
              <button className="btn" onClick={() => latestRun.test_id && onOpenReport(latestRun.test_id)}>
                <Icon name="reports" size={15} /> Open full report
              </button>
              <button className="btn ghost" onClick={() => onGo("leaderboard")}>
                <Icon name="leaderboard" size={15} /> Strategy Board
              </button>
              <button className="btn ghost" onClick={() => onGo("agent")}>
                <Icon name="agent" size={15} /> Run next test
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
              No tests yet. Start with the agent or run a first smoke test to validate your setup.
            </div>
            <div className="pill-row">
              <button className="btn" onClick={() => onGo("agent")}><Icon name="agent" size={15} /> Start Agent</button>
              <button className="btn ghost" onClick={() => onGo("onboarding")}><Icon name="setup" size={15} /> Run First Smoke</button>
            </div>
          </div>
        )}
      </Card>

      <Card title="Quick actions">
        <div className="pill-row">
          <button className="btn ghost" onClick={() => onGo("agent")}><Icon name="agent" size={15} /> Ask the agent</button>
          <button className="btn ghost" onClick={() => onGo("onboarding")}><Icon name="setup" size={15} /> Setup</button>
          <button className="btn ghost" onClick={() => onGo("optimizer")}><Icon name="optimizer" size={15} /> Optimize</button>
          <button className="btn ghost" onClick={() => onGo("reports")}><Icon name="reports" size={15} /> Report</button>
        </div>
      </Card>

      <Card title="Active research jobs">
        {active.length === 0 ? (
          <div className="muted" style={{ fontSize: 13 }}>
            No active jobs. <button className="link-btn" onClick={() => onGo("agent")}>Start with the agent</button>{" "}
            or <button className="link-btn" onClick={() => onGo("onboarding")}>run a first smoke test</button>.
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

      <Card title="Recent run activity">
        {recent.length === 0 ? (
          <div className="muted" style={{ fontSize: 13 }}>No runs yet — your research history will appear here.</div>
        ) : (
          <>
            <div className="heatmap">
              {recent.map((r) => (
                <div
                  key={r.test_id}
                  className={`heat-cell ${r.pass_fail === "PASS" ? "pass" : r.pass_fail === "FAIL" ? "fail" : ""}`}
                  title={`${r.test_id} · ${r.pass_fail}`}
                  onClick={() => onGo("runs")}
                />
              ))}
            </div>
            <div className="heat-legend muted">
              <span><span className="heat-cell pass inline" /> pass</span>
              <span><span className="heat-cell fail inline" /> fail</span>
              <span><span className="heat-cell inline" /> other</span>
            </div>
          </>
        )}
      </Card>

    </div>
  );
}
