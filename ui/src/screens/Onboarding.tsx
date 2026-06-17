import { useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../hooks";
import { AsyncBoundary, Card, ErrorLine, Field, Notice, PageHead } from "../components";

// Setup wizard: detect the MT5 environment (PASS/WARN/FAIL), pick an EA, and run
// a first smoke test as an async job (the app stays responsive).
export function Onboarding({ onJobStarted }: { onJobStarted: (jobId: string) => void }) {
  const detect = useAsync(() => api.detect(), []);
  const eas = useAsync(() => api.eas().catch(() => ({ ok: false, eas: [] })), []);
  const [ea, setEa] = useState("");
  const [symbol, setSymbol] = useState("US30");
  const [timeframe, setTimeframe] = useState("M15");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const eaList = eas.data?.eas || [];
  const effectiveEa = ea || eaList[0]?.name || "";

  const runFirstSmoke = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.submitJob(
        "smoke",
        { ea: effectiveEa, symbol, timeframe, model: "1 minute OHLC", test_id: "UI-FIRST-SMOKE" },
        `First smoke: ${effectiveEa} ${symbol} ${timeframe}`,
      );
      onJobStarted(res.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead title="Setup" subtitle="Detect your MT5 environment and run a first smoke test — no commands required." />
      <Notice>
        The smoke test uses the fast <span className="mono">1 minute OHLC</span> model to validate your setup
        (infrastructure), not strategy quality. It launches MT5 once and shuts it down.
      </Notice>

      <Card title="MT5 environment">
        <AsyncBoundary state={detect}>
          {(data) => (
            <table>
              <tbody>
                {data.checks.map((c) => (
                  <tr key={c.label}>
                    <td style={{ width: 64 }}>
                      <span className={`badge ${c.status === "PASS" ? "pass" : c.status === "FAIL" ? "fail" : "neutral"}`}>
                        {c.status}
                      </span>
                    </td>
                    <td>{c.label}</td>
                    <td className="mono muted">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncBoundary>
        <div className="row-actions" style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={detect.reload}>Re-detect</button>
        </div>
      </Card>

      <Card title="First smoke test">
        {eaList.length > 0 ? (
          <label className="field">
            <span>EA (detected in your Experts folder)</span>
            <select value={effectiveEa} onChange={(e) => setEa(e.target.value)}>
              {eaList.map((item) => (
                <option key={item.name} value={item.name}>{item.name}</option>
              ))}
            </select>
          </label>
        ) : (
          <Field label="EA name" value={ea} onChange={setEa} placeholder="YourCompiledEA" />
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Field label="Symbol" value={symbol} onChange={setSymbol} />
          <Field label="Timeframe" value={timeframe} onChange={setTimeframe} />
        </div>
        <div className="row-actions" style={{ marginTop: 6 }}>
          <button className="btn" onClick={runFirstSmoke} disabled={busy || !effectiveEa}>
            Run first smoke test
          </button>
        </div>
        {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          The run appears in the inspector and the Runs/Queue screen. The app stays responsive while it runs.
        </div>
      </Card>
    </div>
  );
}
