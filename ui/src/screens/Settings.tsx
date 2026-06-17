import { useState } from "react";
import { api, getApiBase, setApiBase } from "../api/client";
import { useAsync } from "../hooks";
import { AsyncBoundary, Card, Field, PageHead, Spinner, StatusBadge } from "../components";
import { SessionControl } from "../SessionControl";

export function Settings() {
  const [base, setBase] = useState(getApiBase());
  const [saved, setSaved] = useState(false);
  const config = useAsync(() => api.config(), []);
  const ai = useAsync(() => api.aiStatus(), []);
  const health = useAsync(() => api.health().catch(() => null), []);

  const save = () => {
    setApiBase(base);
    setSaved(true);
    config.reload();
    ai.reload();
    setTimeout(() => setSaved(false), 1500);
  };

  const cfg = config.data?.config;
  const [terminalPath, setTerminalPath] = useState("");
  const [cfgMsg, setCfgMsg] = useState<string | null>(null);
  const [cfgBusy, setCfgBusy] = useState(false);

  const autoDetect = async () => {
    setCfgBusy(true); setCfgMsg(null);
    try {
      const res = await api.detectTerminal();
      setTerminalPath(res.terminal_path);
      setCfgMsg(res.found ? `Detected: ${res.terminal_path}` : "No MT5 terminal auto-detected. Paste the path to terminal64.exe.");
    } catch (err) {
      setCfgMsg(err instanceof Error ? err.message : String(err));
    } finally { setCfgBusy(false); }
  };
  const saveCfg = async () => {
    setCfgBusy(true); setCfgMsg(null);
    try {
      await api.saveConfig({ terminal_path: terminalPath });
      setCfgMsg("Saved. Re-detecting environment…");
      config.reload();
    } catch (err) {
      setCfgMsg(err instanceof Error ? err.message : String(err));
    } finally { setCfgBusy(false); }
  };

  return (
    <div>
      <PageHead title="Settings" subtitle="MT5 configuration, research session, API connection, and optional AI." />

      <Card title="MT5 terminal">
        <Field
          label="Path to terminal64.exe"
          value={terminalPath || (cfg?.terminal_path_configured ? "(configured)" : "")}
          onChange={setTerminalPath}
          placeholder="C:\\Program Files\\YourBroker MetaTrader 5\\terminal64.exe"
        />
        <div className="row-actions">
          <button className="btn ghost" onClick={autoDetect} disabled={cfgBusy}>Auto-detect</button>
          <button className="btn" onClick={saveCfg} disabled={cfgBusy || !terminalPath}>Save config</button>
        </div>
        {cfgMsg ? <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>{cfgMsg}</div> : null}
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          Saving writes <span className="mono">config.json</span> — no CLI needed. The desktop installer never modifies
          MT5 or your EAs.
        </div>
      </Card>

      <SessionControl />

      <Card title="API connection">
        <Field label="API base URL (localhost only)" value={base} onChange={setBase} placeholder="http://127.0.0.1:8765" />
        <div className="row-actions">
          <button className="btn" onClick={save}>Save</button>
          {saved ? <span className="badge pass">Saved</span> : null}
        </div>
      </Card>

      <Card title="Backend configuration">
        <AsyncBoundary state={config}>
          {(data) => (
            <div className="kv">
              <div className="k">Terminal configured</div>
              <div><StatusBadge status={data.config.terminal_path_configured ? "PASS" : "FAIL"} /></div>
              <div className="k">Portable mode</div>
              <div>{data.config.portable_mode ? "yes" : "no"}</div>
              <div className="k">Artifacts dir</div>
              <div className="mono">{data.config.artifacts_dir}</div>
              <div className="k">Results dir</div>
              <div className="mono">{data.config.results_dir}</div>
              <div className="k">Report strategy</div>
              <div>{data.config.report_path_strategy}</div>
              <div className="k">Max parallel MT5</div>
              <div>{data.config.max_parallel_mt5_processes}</div>
            </div>
          )}
        </AsyncBoundary>
      </Card>

      <Card title="AI provider (optional)">
        {ai.loading ? <Spinner /> : null}
        {ai.error ? <span className="muted">AI status unavailable.</span> : null}
        {ai.data ? (
          <div className="kv">
            <div className="k">Enabled</div>
            <div><StatusBadge status={ai.data.enabled ? "PASS" : "neutral"} /></div>
            <div className="k">Provider / model</div>
            <div>{ai.data.provider} · {ai.data.model || "-"}</div>
            <div className="k">Budget</div>
            <div>{ai.data.calls_used}/{ai.data.max_calls} calls · ${ai.data.est_cost_usd} used</div>
          </div>
        ) : null}
        <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>
          Configure with <span className="mono">ai-config</span>. API keys live in environment variables, never in
          config.json. The deterministic workflow runs fully without AI.
        </div>
      </Card>

      <Card title="Updates">
        <div className="kv">
          <div className="k">Current version</div>
          <div>{health.data ? `v${health.data.version}` : "—"}</div>
          <div className="k">Auto-update</div>
          <div><span className="badge neutral">prepared</span></div>
        </div>
        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          Auto-update is prepared but not enabled in this build (it needs a publisher signing key and a release
          endpoint). When enabled, updates never interrupt an active research run — the app waits until the queue is
          idle and asks first. See <span className="mono">docs/UPDATES.md</span>. For now, install a newer
          installer to upgrade in place; config and data are preserved.
        </div>
      </Card>
    </div>
  );
}
