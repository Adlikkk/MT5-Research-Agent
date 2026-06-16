import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import { useAsync, useJobPolling, isJobActive } from "./hooks";
import { isTauri, registerCloseGuard, destroyWindow } from "./tauri";
import { Inspector } from "./Inspector";
import { Dashboard } from "./screens/Dashboard";
import { Onboarding } from "./screens/Onboarding";
import { Workspace } from "./screens/Workspace";
import { ParameterEditor } from "./screens/ParameterEditor";
import { Optimizer } from "./screens/Optimizer";
import { Queue } from "./screens/Queue";
import { Leaderboard } from "./screens/Leaderboard";
import { Reports } from "./screens/Reports";
import { EaLab } from "./screens/EaLab";
import { Settings } from "./screens/Settings";

export type ScreenId =
  | "dashboard"
  | "onboarding"
  | "workspace"
  | "params"
  | "optimizer"
  | "runs"
  | "leaderboard"
  | "reports"
  | "ealab"
  | "settings";

const NAV: { id: ScreenId; label: string; group?: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "onboarding", label: "Setup" },
  { id: "workspace", label: "Research Workspace" },
  { id: "params", label: "Parameter Editor" },
  { id: "optimizer", label: "Optimizer" },
  { id: "runs", label: "Runs / Queue" },
  { id: "leaderboard", label: "Leaderboard" },
  { id: "reports", label: "Reports" },
  { id: "ealab", label: "EA Lab" },
  { id: "settings", label: "Settings" },
];

export function App() {
  const [screen, setScreen] = useState<ScreenId>("dashboard");
  const [reportId, setReportId] = useState<string>("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const health = useAsync(() => api.health(), []);
  const { jobs } = useJobPolling(1500);

  const sessionActive = jobs.some((j) => j.type === "session_start" && j.status === "succeeded");

  // The inspector follows the selected job, else the most recent active one.
  const inspectedJob = useMemo(() => {
    const byId = selectedJobId ? jobs.find((j) => j.id === selectedJobId) : undefined;
    if (byId) return byId;
    return jobs.find((j) => isJobActive(j)) || jobs[0] || null;
  }, [jobs, selectedJobId]);

  const sessionActiveRef = useRef(false);
  const liveSession = useAsync(() => api.session().catch(() => null), []);
  sessionActiveRef.current = !!liveSession.data?.session_active;
  const [showClosePrompt, setShowClosePrompt] = useState(false);
  const [closeBusy, setCloseBusy] = useState(false);

  useEffect(() => {
    if (isTauri()) return;
    const handler = (event: BeforeUnloadEvent) => {
      if (sessionActiveRef.current) {
        event.preventDefault();
        event.returnValue = "A research MT5 terminal is still running. Stop it from Settings first.";
        return event.returnValue;
      }
      return undefined;
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

  useEffect(() => {
    let unlisten = () => {};
    registerCloseGuard(() => sessionActiveRef.current, () => setShowClosePrompt(true)).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten();
  }, []);

  const stopAndExit = async () => {
    setCloseBusy(true);
    try {
      await api.sessionStop(true).catch(() => undefined);
      await destroyWindow();
    } finally {
      setCloseBusy(false);
      setShowClosePrompt(false);
    }
  };
  const leaveRunningAndExit = async () => {
    setShowClosePrompt(false);
    await destroyWindow();
  };

  const openReport = (testId: string) => {
    setReportId(testId);
    setScreen("reports");
  };
  const onJobStarted = (jobId: string) => {
    setSelectedJobId(jobId);
    setScreen("runs");
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>MT5 Research Agent</h1>
          <span>Strategy Tester only · local</span>
        </div>
        {NAV.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${screen === item.id ? "active" : ""}`}
            onClick={() => setScreen(item.id)}
          >
            <span className="nav-dot" />
            {item.label}
          </button>
        ))}
        <div className="sidebar-foot">
          {sessionActiveRef.current || sessionActive ? (
            <div className="badge pass" style={{ marginBottom: 8 }}>● research session running</div>
          ) : null}
          <div>{health.data ? `API v${health.data.version} · connected` : "API offline"}</div>
        </div>
      </aside>

      <main className="main">
        {!health.loading && health.error ? (
          <div className="banner down">
            <strong>API offline.</strong>
            <span className="muted">
              Start it with <span className="mono">python -m mt5_research_agent serve-api</span> (or the desktop shell
              starts it for you), then set the address in Settings.
            </span>
          </div>
        ) : null}

        {screen === "dashboard" && <Dashboard jobs={jobs} onGo={setScreen} />}
        {screen === "onboarding" && <Onboarding onJobStarted={onJobStarted} />}
        {screen === "workspace" && <Workspace onJobStarted={onJobStarted} />}
        {screen === "params" && <ParameterEditor />}
        {screen === "optimizer" && <Optimizer />}
        {screen === "runs" && <Queue jobs={jobs} onSelect={setSelectedJobId} />}
        {screen === "leaderboard" && <Leaderboard onOpenReport={openReport} />}
        {screen === "reports" && <Reports initialId={reportId} />}
        {screen === "ealab" && <EaLab />}
        {screen === "settings" && <Settings />}
      </main>

      <Inspector job={inspectedJob} />

      {showClosePrompt ? (
        <div className="modal-backdrop">
          <div className="modal">
            <h3>Research MT5 terminal is still running</h3>
            <p className="muted">
              Do you want to stop the configured research terminal before closing? Unrelated MT5 terminals are never
              touched.
            </p>
            <div className="row-actions" style={{ marginTop: 16 }}>
              <button className="btn" onClick={stopAndExit} disabled={closeBusy}>Stop terminal and exit</button>
              <button className="btn ghost" onClick={leaveRunningAndExit} disabled={closeBusy}>Leave terminal running</button>
              <button className="btn ghost" onClick={() => setShowClosePrompt(false)} disabled={closeBusy}>Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
