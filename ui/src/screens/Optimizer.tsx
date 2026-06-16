import { useState } from "react";
import { api } from "../api/client";
import { Card, ErrorLine, Field, Notice, PageHead } from "../components";
import type { OptimizerPreview } from "../api/types";

interface RangeRow {
  name: string;
  start: string;
  step: string;
  stop: string;
}

// Optimizer: configure a parameter sweep, preview the grid size, and (with a
// real terminal) run it as a job. Optimizer fast-mode = one launch, many combos.
export function Optimizer() {
  const [ea, setEa] = useState("Advisors\\US30_MultiStrategyLab_M15");
  const [symbol, setSymbol] = useState("US30");
  const [timeframe, setTimeframe] = useState("M15");
  const [ranges, setRanges] = useState<RangeRow[]>([
    { name: "TP_R", start: "1.0", step: "0.5", stop: "3.0" },
    { name: "ATR_Mult", start: "1.0", step: "0.5", stop: "2.5" },
  ]);
  const [preview, setPreview] = useState<OptimizerPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, key: keyof RangeRow, val: string) =>
    setRanges((prev) => prev.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)));

  const buildSpec = () => ({
    test_id: "UI-OPT",
    ea,
    symbol,
    timeframe,
    period_from: "2020.01.01",
    period_to: "2025.01.01",
    deposit: 10000,
    algorithm: "fast_genetic",
    criterion: "balance_max",
    ranges: ranges
      .filter((r) => r.name.trim())
      .map((r) => ({ name: r.name.trim(), start: Number(r.start), step: Number(r.step), stop: Number(r.stop) })),
  });

  const doPreview = async () => {
    setError(null);
    try {
      const res = await api.optimizerPreview(buildSpec());
      if (!res.ok) {
        setError(res.error || "Invalid optimization spec.");
        setPreview(null);
        return;
      }
      setPreview(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div>
      <PageHead title="Optimizer" subtitle="Configure a parameter sweep. One MT5 launch evaluates many combinations." />
      <Notice>
        Optimizer fast-mode is the preferred way to test many combinations — it does not restart MT5 per combo. Top
        passes still require split validation before any candidate is called robust.
      </Notice>

      <Card title="Target">
        <Field label="EA (Expert= value)" value={ea} onChange={setEa} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Field label="Symbol" value={symbol} onChange={setSymbol} />
          <Field label="Timeframe" value={timeframe} onChange={setTimeframe} />
        </div>
      </Card>

      <Card title="Parameter ranges">
        <table>
          <thead>
            <tr><th>Name</th><th>Start</th><th>Step</th><th>Stop</th></tr>
          </thead>
          <tbody>
            {ranges.map((r, i) => (
              <tr key={i}>
                <td><input type="text" value={r.name} onChange={(e) => update(i, "name", e.target.value)} /></td>
                <td><input type="text" value={r.start} onChange={(e) => update(i, "start", e.target.value)} /></td>
                <td><input type="text" value={r.step} onChange={(e) => update(i, "step", e.target.value)} /></td>
                <td><input type="text" value={r.stop} onChange={(e) => update(i, "stop", e.target.value)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row-actions" style={{ marginTop: 10 }}>
          <button className="btn" onClick={doPreview}>Preview grid + .set</button>
          <button
            className="btn ghost"
            onClick={() => setRanges((p) => [...p, { name: "", start: "1", step: "1", stop: "2" }])}
          >
            Add range
          </button>
        </div>
        {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
      </Card>

      {preview ? (
        <Card title="Preview">
          <div className="kv">
            <div className="k">Algorithm</div>
            <div>{preview.algorithm} (Optimization={preview.algorithm_code})</div>
            <div className="k">Grid size (slow-complete)</div>
            <div><strong>{preview.grid_combinations}</strong> combinations</div>
          </div>
          <pre className="pre" style={{ marginTop: 12 }}>{preview.set_text}</pre>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            To run: save this spec and launch from the CLI (`run-optimization &lt;spec&gt; --run`) or submit an
            optimization job once a terminal is configured. Live optimization requires a real MT5 terminal.
          </div>
        </Card>
      ) : null}
    </div>
  );
}
