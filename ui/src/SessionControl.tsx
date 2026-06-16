import { useState } from "react";
import { api } from "./api/client";
import { useAsync } from "./hooks";
import { Card, ErrorLine, StatusBadge } from "./components";
import type { SessionStatus } from "./api/types";

// "Research Session" control: keep one MT5 terminal open across many tests
// instead of restarting it per test. Start / status / Stop, plus process state.
export function SessionControl({ onChange }: { onChange?: (active: boolean) => void }) {
  const status = useAsync(() => api.session(), []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = () => {
    status.reload();
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      let result: SessionStatus = await api.sessionStart(false);
      if (!result.ok && result.require_confirm) {
        if (window.confirm(`${result.message}\n\nAdopt the already-running terminal?`)) {
          result = await api.sessionStart(true);
        }
      }
      setNotice(result.message || "Research session started.");
      onChange?.(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const stop = async () => {
    if (!window.confirm("Stop the configured research MT5 terminal? Unrelated MT5 terminals are never touched.")) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.sessionStop(true);
      setNotice(result.message || "Research session stopped.");
      onChange?.(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const data = status.data;
  const active = !!data?.session_active;

  return (
    <Card title="Research Session">
      <p className="muted" style={{ marginTop: 0, fontSize: 12.5 }}>
        Keep one MT5 terminal open across a research session instead of restarting it per test. Session runs reuse the
        open terminal via GUI; large parameter sweeps use optimizer fast-mode. The app never silently restarts MT5.
      </p>
      <div className="kv">
        <div className="k">Session</div>
        <div><StatusBadge status={active ? "PASS" : "neutral"} /> {active ? "running" : "stopped"}</div>
        <div className="k">MT5 process</div>
        <div>{data?.process_running ? "running" : "not running"}</div>
        <div className="k">Terminal</div>
        <div className="mono">{data?.configured_terminal_path || "-"}</div>
        {data?.session?.pid ? (
          <>
            <div className="k">PID / mode</div>
            <div>{data.session.pid} · {data.session.mode}</div>
          </>
        ) : null}
      </div>
      <div className="row-actions" style={{ marginTop: 12 }}>
        <button className="btn" onClick={start} disabled={busy || active}>Start research terminal</button>
        <button className="btn ghost" onClick={stop} disabled={busy || !data?.process_running}>Stop session</button>
        <button className="btn ghost" onClick={refresh} disabled={busy}>Refresh</button>
      </div>
      {notice ? <div className="badge pass" style={{ marginTop: 10 }}>{notice}</div> : null}
      {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
    </Card>
  );
}
