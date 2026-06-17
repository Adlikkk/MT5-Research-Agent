import { useState } from "react";
import { api } from "../api/client";
import { Card, ErrorLine, Field, Notice, PageHead, Segmented } from "../components";
import type { EaCreateResult } from "../api/types";

type Tab = "create" | "strategy" | "risk" | "filters" | "execution" | "source" | "compile" | "versions";

const TABS: { id: Tab; label: string }[] = [
  { id: "create", label: "Create" },
  { id: "strategy", label: "Strategy" },
  { id: "risk", label: "Risk" },
  { id: "filters", label: "Filters" },
  { id: "execution", label: "Execution" },
  { id: "source", label: "Source" },
  { id: "compile", label: "Compile" },
  { id: "versions", label: "Versions" },
];

// Safe-by-default settings the generator applies. Shown read-only so the user
// understands the guardrails without leaving the app.
const DEFAULTS: Record<Exclude<Tab, "create" | "source" | "compile" | "versions">, [string, string][]> = {
  strategy: [
    ["Position model", "Single position at a time"],
    ["Entry", "Indicator/condition based (no averaging)"],
    ["Direction", "Long & short symmetric"],
  ],
  risk: [
    ["Martingale / grid", "Disabled"],
    ["Stop loss", "ATR-based, always set"],
    ["Risk per trade", "Fixed fraction (configurable)"],
  ],
  filters: [
    ["Session filter", "Enabled (configurable hours)"],
    ["Spread filter", "Enabled (max spread cap)"],
    ["News window", "Optional"],
  ],
  execution: [
    ["Order type", "Strategy Tester only — no live order_send"],
    ["Slippage guard", "Enabled"],
    ["Fill policy", "Broker default"],
  ],
};

export function EaLab() {
  const [tab, setTab] = useState<Tab>("create");
  const [promptPath, setPromptPath] = useState("research_requests/ea_prompt.md");
  const [result, setResult] = useState<EaCreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.createEa(promptPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead
        title="EA Lab"
        subtitle="Generate a safe-by-default EA from a prompt, then review the guardrails it applies."
      />
      <Segmented value={tab} options={TABS} onChange={setTab} />

      {tab === "create" ? (
        <>
          <Notice>
            Generated EAs default to one position, no martingale/grid, ATR stops, and session/spread filters. They are
            written to a sandboxed Experts folder, so your own EAs are never touched.
          </Notice>
          <Card title="Create EA from prompt">
            <Field
              label="EA prompt markdown path"
              value={promptPath}
              onChange={setPromptPath}
              placeholder="research_requests/ea_prompt.md"
            />
            <div className="row-actions">
              <button className="btn" onClick={create} disabled={busy || !promptPath}>Generate EA</button>
            </div>
            {error ? <div style={{ marginTop: 12 }}><ErrorLine message={error} /></div> : null}
          </Card>
          {result ? (
            <Card title="Result">
              <pre className="pre">{JSON.stringify(result, null, 2)}</pre>
            </Card>
          ) : null}
        </>
      ) : null}

      {tab === "strategy" || tab === "risk" || tab === "filters" || tab === "execution" ? (
        <Card title={`${TABS.find((t) => t.id === tab)?.label} defaults`}>
          <div className="kv">
            {DEFAULTS[tab].map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <div className="k">{k}</div>
                <div>{v}</div>
              </div>
            ))}
          </div>
          <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>
            These guardrails are baked into every generated EA. Describe overrides in your prompt — the generator keeps
            the safety defaults unless you explicitly relax them.
          </div>
        </Card>
      ) : null}

      {tab === "source" || tab === "compile" || tab === "versions" ? (
        <Card title={`${TABS.find((t) => t.id === tab)?.label} · Advanced CLI fallback`}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
            {tab === "source"
              ? "Generated .mq5 source lives in the sandboxed Experts folder. Open it in MetaEditor to review."
              : tab === "compile"
                ? "Compilation runs MetaEditor headlessly. This step is currently exposed through the CLI."
                : "Version history and revert are managed by the CLI so changes stay auditable."}
          </div>
          <div className="kv">
            {tab === "compile" ? (
              <>
                <div className="k">Compile</div>
                <div className="mono">compile-ea-lab &lt;ea_name&gt;</div>
                <div className="k">Smoke test</div>
                <div className="mono">smoke-test-ea &lt;ea_name&gt; --symbol US30 --timeframe M15 --run</div>
              </>
            ) : tab === "versions" ? (
              <>
                <div className="k">History</div>
                <div className="mono">ea-version-history &lt;ea_name&gt;</div>
                <div className="k">Revert</div>
                <div className="mono">revert-ea &lt;ea_name&gt; --to-version N</div>
                <div className="k">Improve</div>
                <div className="mono">improve-ea &lt;ea_name&gt; --goal &lt;request.md&gt;</div>
              </>
            ) : (
              <>
                <div className="k">Location</div>
                <div className="mono">&lt;Experts&gt;/Advisors/&lt;ea_name&gt;.mq5</div>
              </>
            )}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
