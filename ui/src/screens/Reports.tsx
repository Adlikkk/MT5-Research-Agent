import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Card, EmptyState, ErrorLine, Field, PageHead, Spinner } from "../components";
import { Icon } from "../icons";
import {
  ConfidenceBadge,
  LongShortBar,
  MetricCard,
  ThresholdBar,
  UnavailablePanel,
  VerdictBadge,
  fmt,
} from "../report_ui";
import type { ReportAnalysis } from "../api/types";

export function Reports({ initialId }: { initialId: string }) {
  const [testId, setTestId] = useState(initialId);
  const [report, setReport] = useState<ReportAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.reportAnalysis(id);
      if (!data.ok) {
        setError(data.error === "TEST_ID_NOT_FOUND" ? `No stored run for "${id}".` : data.error || "Report not found.");
        setReport(null);
      } else {
        setReport(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialId) {
      setTestId(initialId);
      void load(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId]);

  return (
    <div>
      <PageHead title="Report" subtitle="What the test result actually means — metrics, a verdict, and what to test next." />

      <Card>
        <Field label="Test ID" value={testId} onChange={setTestId} placeholder="DemoEA_20260101T000000Z" />
        <div className="row-actions">
          <button className="btn" onClick={() => load(testId)} disabled={loading || !testId}>Load report</button>
        </div>
        {error ? <div style={{ marginTop: 12 }}><ErrorLine message={error} /></div> : null}
      </Card>

      {loading ? <Spinner /> : null}
      {report ? <ReportBody report={report} /> : null}

      {!report && !loading && !error ? (
        <EmptyState
          icon="reports"
          title="Open a run report"
          description="Enter a Test ID, or click a run from the Strategy Board or Runs list to see its verdict and analysis."
        />
      ) : null}
    </div>
  );
}

function ReportBody({ report }: { report: ReportAnalysis }) {
  const m = report.metrics;
  const da = report.data_available;
  const ddTone = m.drawdown_pct === null ? undefined : m.drawdown_pct <= 20 ? "good" : m.drawdown_pct > 30 ? "bad" : "warn";
  const pfTone = m.profit_factor === null ? undefined : m.profit_factor >= 1.35 ? "good" : m.profit_factor < 1.1 ? "bad" : "warn";

  return (
    <>
      <Card>
        <div className="report-header">
          <div>
            <div className="report-title">{report.ea || "—"}</div>
            <div className="report-sub muted">
              {report.symbol} {report.timeframe} · {report.period || "—"} · {report.model || "—"}
            </div>
            <div className="report-sub muted mono">{report.test_id}</div>
          </div>
          <div className="report-badges">
            <VerdictBadge verdict={report.verdict} large />
            <ConfidenceBadge confidence={report.verdict.confidence} />
          </div>
        </div>
        <div className="verdict-why">
          <div className="inspector-sub">Why this verdict</div>
          <ul className="reason-list">
            {report.verdict.reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      </Card>

      <div className="metric-grid">
        <MetricCard label="Net profit" value={fmt(m.net_profit)} />
        <MetricCard label="Return %" value={m.return_pct === null ? "—" : `${fmt(m.return_pct)}%`} />
        <MetricCard label="Profit factor" value={fmt(m.profit_factor)} tone={pfTone} />
        <MetricCard label="Max equity DD %" value={m.drawdown_pct === null ? "—" : `${fmt(m.drawdown_pct)}%`} tone={ddTone} />
        <MetricCard label="Trades" value={m.total_trades ?? "—"} />
        <MetricCard label="Win rate %" value={m.winrate_pct === null ? "—" : `${fmt(m.winrate_pct)}%`} />
        <MetricCard label="Recovery factor" value={fmt(m.recovery_factor)} />
        <MetricCard label="Expected payoff" value={fmt(m.expected_payoff)} />
        <MetricCard label="Avg win / loss" value={`${fmt(m.average_win)} / ${fmt(m.average_loss)}`} />
        <MetricCard label="Risk : reward" value={m.risk_reward === null ? "—" : `${fmt(m.risk_reward)} : 1`} />
      </div>

      <Card title="Targets">
        <div className="target-row">
          <span className="target-label">Profit factor vs 1.35</span>
          <ThresholdBar value={m.profit_factor} threshold={1.35} max={3} />
          <span className="target-val">{fmt(m.profit_factor)}</span>
        </div>
        <div className="target-row">
          <span className="target-label">Max DD vs 20%</span>
          <ThresholdBar value={m.drawdown_pct} threshold={20} max={50} lowerIsBetter />
          <span className="target-val">{m.drawdown_pct === null ? "—" : `${fmt(m.drawdown_pct)}%`}</span>
        </div>
        <div className="target-row">
          <span className="target-label">Trades vs 250</span>
          <ThresholdBar value={m.total_trades} threshold={250} max={600} />
          <span className="target-val">{m.total_trades ?? "—"}</span>
        </div>
      </Card>

      <Card title="Long vs Short">
        <LongShortBar data={report.long_short} />
      </Card>

      <Card title="Trade-level breakdowns">
        <div className="breakdown-grid">
          {!da.equity_curve ? <UnavailablePanel title="Equity / drawdown curve" note={report.trade_level_note} /> : null}
          {!da.weekday_breakdown ? <UnavailablePanel title="Weekday breakdown" note={report.trade_level_note} /> : null}
          {!da.monthly_breakdown ? <UnavailablePanel title="Monthly PnL" note={report.trade_level_note} /> : null}
          {!da.session_breakdown ? <UnavailablePanel title="Session / hour" note={report.trade_level_note} /> : null}
        </div>
      </Card>

      <Card title="Analysis">
        <AnalysisList icon="agent" title="Strengths" items={report.strengths} tone="good" empty="No standout strengths." />
        <AnalysisList icon="x" title="Weaknesses" items={report.weaknesses} tone="warn" empty="No major weaknesses flagged." />
        <AnalysisList icon="optimizer" title="Risk notes" items={report.risk_notes} tone="warn" empty="No specific risk notes." />
        {report.overfit_warnings.length ? (
          <AnalysisList icon="optimizer" title="Overfit warnings" items={report.overfit_warnings} tone="bad" empty="" />
        ) : null}
        {report.data_quality_warnings.length ? (
          <AnalysisList icon="logs" title="Data quality" items={report.data_quality_warnings} tone="neutral" empty="" />
        ) : null}
      </Card>

      <Card title="Recommended next test">
        <div className="next-test">
          <Icon name="research" size={16} />
          <span>{report.recommended_next_test}</span>
        </div>
      </Card>
    </>
  );
}

function AnalysisList({
  icon,
  title,
  items,
  tone,
  empty,
}: {
  icon: "agent" | "x" | "optimizer" | "logs";
  title: string;
  items: string[];
  tone: "good" | "warn" | "bad" | "neutral";
  empty: string;
}) {
  if (items.length === 0 && !empty) return null;
  return (
    <div className="analysis-block">
      <div className={`analysis-head ${tone}`}><Icon name={icon} size={14} /> {title}</div>
      {items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12.5 }}>{empty}</div>
      ) : (
        <ul className="analysis-items">{items.map((it, i) => <li key={i}>{it}</li>)}</ul>
      )}
    </div>
  );
}
