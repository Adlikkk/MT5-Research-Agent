import { useState } from "react";
import { api } from "../api/client";
import { Card, ErrorLine, Field, Notice, PageHead } from "../components";
import type { EaCreateResult } from "../api/types";

export function EaLab() {
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
        subtitle="Generate a safe-by-default EA from a prompt. Compile, smoke-test, improve, and revert stay on the CLI."
      />
      <Notice>
        Generated EAs default to one position, no martingale/grid, ATR stops, and session/spread filters. They are
        written to a sandboxed Experts folder, so your own EAs are never touched.
      </Notice>

      <Card title="Create EA from prompt">
        <Field label="EA prompt markdown path" value={promptPath} onChange={setPromptPath} placeholder="research_requests/ea_prompt.md" />
        <div className="row-actions">
          <button className="btn" onClick={create} disabled={busy || !promptPath}>
            Generate EA
          </button>
        </div>
        {error ? <div style={{ marginTop: 12 }}><ErrorLine message={error} /></div> : null}
      </Card>

      {result ? (
        <Card title="Result">
          <pre className="pre">{JSON.stringify(result, null, 2)}</pre>
        </Card>
      ) : null}

      <Card title="Next steps (CLI)">
        <div className="kv">
          <div className="k">Compile</div>
          <div className="mono">compile-ea-lab &lt;ea_name&gt;</div>
          <div className="k">Smoke test</div>
          <div className="mono">smoke-test-ea &lt;ea_name&gt; --symbol US30 --timeframe M15 --run</div>
          <div className="k">Improve</div>
          <div className="mono">improve-ea &lt;ea_name&gt; --goal &lt;request.md&gt;</div>
          <div className="k">Versions</div>
          <div className="mono">ea-version-history &lt;ea_name&gt; · revert-ea &lt;ea_name&gt; --to-version N</div>
        </div>
      </Card>
    </div>
  );
}
