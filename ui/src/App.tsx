import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import { useAsync, useBackendStatus, useJobPolling, isJobActive } from "./hooks";
import { isTauri, registerCloseGuard, destroyWindow } from "./tauri";
import { Icon, type IconName } from "./icons";
import { StatusPill } from "./components";
import { Inspector } from "./Inspector";
import { Agent } from "./screens/Agent";
import { Dashboard } from "./screens/Dashboard";
import { Onboarding } from "./screens/Onboarding";
import { Workspace } from "./screens/Workspace";
import { ParameterEditor } from "./screens/ParameterEditor";
import { Optimizer } from "./screens/Optimizer";
import { Queue } from "./screens/Queue";
import { StrategyBoard } from "./screens/StrategyBoard";
import { Reports } from "./screens/Reports";
import { EaLab } from "./screens/EaLab";
import { Settings } from "./screens/Settings";

export type ScreenId =
  | "agent"
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

interface NavItem {
  id: ScreenId;
  label: string;
  icon: IconName;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Workspace",
    items: [
      { id: "agent", label: "Agent", icon: "agent" },
      { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    ],
  },
  {
    section: "Build",
    items: [
      { id: "onboarding", label: "Setup", icon: "setup" },
      { id: "workspace", label: "Research", icon: "research" },
      { id: "params", label: "Parameters", icon: "params" },
      { id: "optimizer", label: "Optimizer", icon: "optimizer" },
      { id: "ealab", label: "EA Lab", icon: "ealab" },
    ],
  },
  {
    section: "Results",
    items: [
      { id: "runs", label: "Runs", icon: "runs" },
      { id: "leaderboard", label: "Strategy Board", icon: "leaderboard" },
      { id: "reports", label: "Report", icon: "reports" },
    ],
  },
  {
    section: "System",
    items: [{ id: "settings", label: "Settings", icon: "settings" }],
  },
];

const SCREEN_TITLES: Record<ScreenId, string> = {
  agent: "Agent",
  dashboard: "Dashboard",
  onboarding: "Setup",
  workspace: "Research",
  params: "Parameters",
  optimizer: "Optimizer",
  runs: "Runs",
  leaderboard: "Strategy Board",
  reports: "Report",
  ealab: "EA Lab",
  settings: "Settings",
};

function usePersistentFlag(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : raw === "1";
    } catch {
      return initial;
    }
  });
  const set = (v: boolean) => {
    setValue(v);
    try {
      localStorage.setItem(key, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  };
  return [value, set];
}

export function App() {
  const [screen, setScreen] = useState<ScreenId>("agent");
  const [reportId, setReportId] = useState<string>("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = usePersistentFlag("mt5ra.sidebarCollapsed", false);
  const [inspectorCollapsed, setInspectorCollapsed] = usePersistentFlag("mt5ra.inspectorCollapsed", false);

  const health = useAsync(() => api.health(), []);
  const backend = useBackendStatus(2500);
  const { jobs } = useJobPolling(1500);
  const liveSession = useAsync(() => api.session().catch(() => null), []);

  const activeJobs = jobs.filter((j) => isJobActive(j));
  const sessionActive = !!liveSession.data?.session_active;
  const mt5Running = !!liveSession.data?.process_running;

  // The inspector follows the selected job, else the most recent active one.
  const inspectedJob = useMemo(() => {
    const byId = selectedJobId ? jobs.find((j) => j.id === selectedJobId) : undefined;
    if (byId) return byId;
    return jobs.find((j) => isJobActive(j)) || jobs[0] || null;
  }, [jobs, selectedJobId]);

  const sessionActiveRef = useRef(false);
  sessionActiveRef.current = sessionActive;
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
    setInspectorCollapsed(false);
    setScreen("runs");
  };

  const apiTone = backend.state === "online" ? "good" : backend.state === "offline" ? "bad" : "idle";
  const apiLabel = backend.state === "online" ? "API" : backend.state === "offline" ? "API offline" : "Connecting";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-left">
          <button
            className="icon-btn"
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          >
            <Icon name={sidebarCollapsed ? "chevron-right" : "chevron-left"} />
          </button>
          <div className="app-mark">
            <Icon name="agent" size={16} />
            <span>MT5 Research Agent</span>
          </div>
          <span className="topbar-screen">{SCREEN_TITLES[screen]}</span>
        </div>

        <div className="topbar-right">
          <StatusPill
            tone={apiTone}
            label={apiLabel}
            value={health.data ? `v${health.data.version}` : undefined}
            title="Local research backend"
          />
          <StatusPill
            tone={mt5Running ? "good" : "idle"}
            label="MT5"
            value={mt5Running ? "Running" : "Idle"}
            title="MetaTrader 5 process"
          />
          <StatusPill
            tone={sessionActive ? "good" : "idle"}
            label="Session"
            value={sessionActive ? "Active" : "—"}
            title="Research session"
          />
          <StatusPill
            tone={activeJobs.length ? "good" : "idle"}
            label="Jobs"
            value={activeJobs.length ? String(activeJobs.length) : "0"}
            title="Active background jobs"
            onClick={() => setScreen("runs")}
          />
          <StatusPill tone="idle" label="Up to date" title="Manual updates via GitHub Releases" />
          <button
            className={`icon-btn ${inspectorCollapsed ? "" : "active"}`}
            title={inspectorCollapsed ? "Show inspector" : "Hide inspector"}
            onClick={() => setInspectorCollapsed(!inspectorCollapsed)}
          >
            <Icon name="panel-right" />
          </button>
        </div>
      </header>

      <div
        className="shell-body"
        data-sb={sidebarCollapsed ? "0" : "1"}
        data-insp={inspectorCollapsed ? "0" : "1"}
      >
        <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
          <nav className="nav">
            {NAV.map((group) => (
              <div className="nav-group" key={group.section}>
                {!sidebarCollapsed ? <div className="nav-section">{group.section}</div> : null}
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    className={`nav-item ${screen === item.id ? "active" : ""}`}
                    onClick={() => setScreen(item.id)}
                    title={item.label}
                  >
                    <Icon name={item.icon} />
                    {!sidebarCollapsed ? <span>{item.label}</span> : null}
                  </button>
                ))}
              </div>
            ))}
          </nav>
          {!sidebarCollapsed ? (
            <div className="sidebar-foot">Strategy Tester only · no live trading</div>
          ) : null}
        </aside>

        <main className="main">
          {screen === "agent" && <Agent onJobStarted={onJobStarted} />}
          {screen === "dashboard" && <Dashboard jobs={jobs} onGo={setScreen} onOpenReport={openReport} />}
          {screen === "onboarding" && <Onboarding onJobStarted={onJobStarted} />}
          {screen === "workspace" && <Workspace onJobStarted={onJobStarted} />}
          {screen === "params" && <ParameterEditor />}
          {screen === "optimizer" && <Optimizer />}
          {screen === "runs" && <Queue jobs={jobs} onSelect={setSelectedJobId} />}
          {screen === "leaderboard" && <StrategyBoard onOpenReport={openReport} />}
          {screen === "reports" && <Reports initialId={reportId} />}
          {screen === "ealab" && <EaLab />}
          {screen === "settings" && <Settings />}
        </main>

        {!inspectorCollapsed ? (
          <Inspector job={inspectedJob} onClose={() => setInspectorCollapsed(true)} />
        ) : null}
      </div>

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
