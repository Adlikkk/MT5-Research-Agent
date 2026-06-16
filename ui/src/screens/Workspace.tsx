import { useState } from "react";
import { api } from "../api/client";
import { Card, ErrorLine, Field, Notice, PageHead } from "../components";
import type { PlanResult, RequestPreview } from "../api/types";

// Research Workspace: write a goal, edit constraints, preview the structured
// request, validate/plan it, and launch. Long runs go through the job queue so
// the app never freezes.
export function Workspace({ onJobStarted }: { onJobStarted: (jobId: string) => void }) {
  const [requestPath, setRequestPath] = useState("research_requests/us30_goal.md");
  const [goal, setGoal] = useState("Reach ~+250% over 5 years on US30 M15 with controlled drawdown.");
  const [targetReturn, setTargetReturn] = useState("250");
  const [maxDd, setMaxDd] = useState("25");
  const [minPf, setMinPf] = useState("1.2");
  const [minTrades, setMinTrades] = useState("250");
  const [splits, setSplits] = useState(true);
  const [preview, setPreview] = useState<RequestPreview | null>(null);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const validate = async () => {
    setBusy(true); setError(null); setPlan(null);
    try {
      setPreview(await api.createResearchRequest(requestPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };
  const planNext = async () => {
    setBusy(true); setError(null);
    try {
      setPlan(await api.planNext(requestPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };
  const launchSmoke = async () => {
    setBusy(true); setError(null);
    try {
      const res = await api.submitJob(
        "smoke",
        { ea: "Advisors\\US30_MultiStrategyLab_M15", symbol: "US30", timeframe: "M15", model: "1 minute OHLC", test_id: "UI-RESEARCH-SMOKE" },
        "Research entry smoke",
      );
      onJobStarted(res.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };
  const startResearch = async () => {
    setBusy(true); setError(null);
    try {
      const res = await api.submitJob("research", { request_path: requestPath }, `Research: ${requestPath}`);
      onJobStarted(res.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHead title="Research Workspace" subtitle="Describe a goal, set constraints, and launch. The engine plans and runs; you watch live." />
      <Notice>
        Robustness is required: split validation must pass before any candidate is called best. Profit alone never
        qualifies a candidate. No profitability guarantees.
      </Notice>

      <Card title="Goal">
        <Field label="Research goal" value={goal} onChange={setGoal} textarea />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
          <Field label="Target return %" value={targetReturn} onChange={setTargetReturn} />
          <Field label="Max drawdown %" value={maxDd} onChange={setMaxDd} />
          <Field label="Min profit factor" value={minPf} onChange={setMinPf} />
          <Field label="Min trades" value={minTrades} onChange={setMinTrades} />
        </div>
        <label className="field" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={splits} onChange={(e) => setSplits(e.target.checked)} style={{ width: "auto" }} />
          <span style={{ margin: 0 }}>Require split validation (recommended)</span>
        </label>
        <div className="pre" style={{ marginTop: 4 }}>{JSON.stringify(
          { goal, target_return_pct: Number(targetReturn), max_drawdown_pct: Number(maxDd), min_profit_factor: Number(minPf), min_trades: Number(minTrades), must_validate_splits: splits },
          null, 2,
        )}</div>
      </Card>

      <Card title="Request file">
        <Field label="Request markdown path" value={requestPath} onChange={setRequestPath} />
        <div className="row-actions">
          <button className="btn" onClick={startResearch} disabled={busy || !requestPath}>Start research</button>
          <button className="btn ghost" onClick={validate} disabled={busy || !requestPath}>Validate request</button>
          <button className="btn ghost" onClick={planNext} disabled={busy || !requestPath}>Plan next batch</button>
          <button className="btn ghost" onClick={launchSmoke} disabled={busy}>Launch entry smoke</button>
        </div>
        {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          "Start research" runs the deep goal-seeking loop as a background job — the app stays responsive and the
          inspector shows live progress. Results land in the Leaderboard and Reports.
        </div>
      </Card>

      {preview ? (
        <Card title="Structured preview">
          <div className="kv">
            <div className="k">Slug</div><div className="mono">{preview.slug || "-"}</div>
            <div className="k">EA</div><div>{preview.ea || "-"}</div>
            <div className="k">Symbol / TF</div><div>{preview.symbol || "-"} · {preview.timeframe || "-"}</div>
          </div>
          {preview.todos && preview.todos.length > 0 ? (
            <div className="err" style={{ marginTop: 10 }}>Needs work: {preview.todos.join("; ")}</div>
          ) : <div className="badge pass" style={{ marginTop: 10 }}>Ready</div>}
        </Card>
      ) : null}

      {plan ? (
        <Card title="Planned batch">
          <div className="kv">
            <div className="k">Plan</div><div className="mono">{plan.plan_path || "-"}</div>
            <div className="k">Experiment</div><div className="mono">{plan.experiment_path || "-"}</div>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
