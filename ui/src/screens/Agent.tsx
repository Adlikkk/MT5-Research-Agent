import { useState } from "react";
import { api } from "../api/client";
import { ErrorLine, PageHead } from "../components";
import { Icon } from "../icons";
import type { AgentGoals, AgentMode, AgentPlan } from "../api/types";

// The Agent tab is the primary entry point: the user describes a goal in plain
// language, the backend parses it into an editable plan (goal chips), and a
// single "Start research" action launches the proven research job — no CLI, no
// raw JSON unless the user opens Advanced.

const MODES: { id: AgentMode; label: string; hint: string }[] = [
  { id: "research_existing", label: "Research existing EA", hint: "Sweep & validate an EA you already have" },
  { id: "create_new", label: "Create new EA", hint: "Scaffold a new strategy from a description" },
  { id: "optimize", label: "Optimize parameters", hint: "Tune parameters toward your targets" },
  { id: "diagnose", label: "Diagnose failed run", hint: "Explain why a run failed its rules" },
  { id: "report", label: "Generate report", hint: "Summarize results into a report" },
];

const EXAMPLE =
  "Test XAUUSD H1 until PF is near 1.5, max DD 20%, minimum 300 trades, split validation required";

// Editable goal fields, in display order. `bool` is the split-validation toggle.
const GOAL_FIELDS: { key: keyof AgentGoals; label: string; kind: "text" | "number" | "bool" }[] = [
  { key: "symbol", label: "Symbol", kind: "text" },
  { key: "timeframe", label: "Timeframe", kind: "text" },
  { key: "target_profit_factor", label: "Target PF", kind: "number" },
  { key: "target_return_pct", label: "Target return %", kind: "number" },
  { key: "max_drawdown_pct", label: "Max DD %", kind: "number" },
  { key: "min_trades", label: "Min trades", kind: "number" },
  { key: "max_tests", label: "Max tests", kind: "number" },
  { key: "max_runtime_minutes", label: "Max runtime (min)", kind: "number" },
];

export function Agent({ onJobStarted }: { onJobStarted: (jobId: string) => void }) {
  const [prompt, setPrompt] = useState(EXAMPLE);
  const [mode, setMode] = useState<AgentMode>("research_existing");
  // Until the user clicks a mode pill, the prompt's own wording decides the mode
  // (auto-detect). An explicit pick overrides detection on the next preview.
  const [modeTouched, setModeTouched] = useState(false);
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [goals, setGoals] = useState<AgentGoals | null>(null);
  const [requestPath, setRequestPath] = useState("research_requests/us30_goal.md");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const previewPlan = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.agentParse(prompt, modeTouched ? mode : undefined);
      setPlan(result);
      setGoals(result.goals);
      setMode(result.mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const updateGoal = (key: keyof AgentGoals, value: string | number | boolean | null) => {
    setGoals((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const startResearch = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.submitJob(
        "research",
        { request_path: requestPath, goals },
        plan?.summary || "Agent research",
      );
      onJobStarted(res.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="agent">
      <PageHead
        title="Agent"
        subtitle="Describe what you want in plain language. The agent turns it into a research plan you can edit, then runs it for you."
      />

      <div className="agent-prompt card">
        <textarea
          className="agent-textarea"
          value={prompt}
          placeholder={EXAMPLE}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div className="agent-modes">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={`mode-pill ${mode === m.id ? "active" : ""}`}
              title={m.hint}
              onClick={() => { setMode(m.id); setModeTouched(true); }}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="row-actions">
          <button className="btn ghost" onClick={previewPlan} disabled={busy || !prompt.trim()}>
            <Icon name="agent" size={15} /> Preview plan
          </button>
          <button className="btn" onClick={startResearch} disabled={busy || !goals}>
            <Icon name="play" size={15} /> Start research
          </button>
        </div>
        {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
      </div>

      {plan && goals ? (
        <div className="card agent-plan">
          <div className="agent-plan-summary">
            <Icon name="research" size={16} />
            <span>{plan.summary}</span>
          </div>

          <div className="chip-grid">
            {GOAL_FIELDS.map((f) => (
              <label key={f.key} className="goal-chip">
                <span className="goal-chip-label">{f.label}</span>
                <input
                  type={f.kind === "number" ? "number" : "text"}
                  value={goals[f.key] === null || goals[f.key] === undefined ? "" : String(goals[f.key])}
                  placeholder="—"
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") return updateGoal(f.key, null);
                    updateGoal(f.key, f.kind === "number" ? Number(raw) : raw);
                  }}
                />
              </label>
            ))}
            <label className="goal-chip toggle">
              <span className="goal-chip-label">Split validation</span>
              <button
                className={`toggle-btn ${goals.split_validation ? "on" : ""}`}
                onClick={() => updateGoal("split_validation", !goals.split_validation)}
                type="button"
              >
                {goals.split_validation ? "Required" : "Off"}
              </button>
            </label>
          </div>

          <label className="field" style={{ marginTop: 14 }}>
            <span>Research request file (the proven engine runs this; your goals refine its constraints)</span>
            <input type="text" value={requestPath} onChange={(e) => setRequestPath(e.target.value)} />
          </label>

          <button className="link-btn" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "Hide" : "Show"} advanced (raw plan)
          </button>
          {showAdvanced ? <pre className="pre">{JSON.stringify({ mode, goals }, null, 2)}</pre> : null}

          <div className="agent-safety">
            Strategy Tester only · no live trading. A candidate is only “best” after split validation passes — profit
            alone never qualifies it.
          </div>
        </div>
      ) : null}
    </div>
  );
}
