// Thin typed client over the localhost-only MT5 Research Agent HTTP API.
// The UI never duplicates backend logic - it only calls these endpoints.

import type {
  AiStatus,
  AppConfig,
  DetectResponse,
  EaCreateResult,
  EaInfo,
  HealthResponse,
  Job,
  LeaderboardResponse,
  OptimizerPreview,
  PlanResult,
  ReportStatus,
  RequestPreview,
  RunsResponse,
  SessionStatus,
  SetPreview,
} from "./types";

const DEFAULT_BASE = "http://127.0.0.1:8765";
const BASE_KEY = "mt5ra.apiBase";

export function getApiBase(): string {
  try {
    return localStorage.getItem(BASE_KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}

export function setApiBase(base: string): void {
  try {
    localStorage.setItem(BASE_KEY, base.replace(/\/+$/, ""));
  } catch {
    /* ignore storage failures */
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${getApiBase()}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let parsed: unknown = {};
  try {
    parsed = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`Non-JSON response (${response.status}) from ${path}`);
  }
  if (!response.ok) {
    const detail = (parsed as { error?: string }).error || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return parsed as T;
}

export const api = {
  health: () => request<HealthResponse>("GET", "/health"),
  config: () => request<{ ok: boolean; config: AppConfig }>("GET", "/config"),
  tools: () => request<{ ok: boolean; tools: string[] }>("GET", "/tools"),
  runs: () => request<RunsResponse>("GET", "/runs"),
  leaderboard: () => request<LeaderboardResponse>("GET", "/leaderboard"),
  aiStatus: () => request<AiStatus>("GET", "/ai/status"),
  report: (testId: string) => request<ReportStatus>("GET", `/reports/${encodeURIComponent(testId)}`),
  createResearchRequest: (requestPath: string) =>
    request<RequestPreview>("POST", "/research-requests", { request_path: requestPath }),
  planNext: (requestPath: string) =>
    request<PlanResult>("POST", "/planner/next", { request_path: requestPath }),
  createEa: (promptPath: string) => request<EaCreateResult>("POST", "/ea/create", { prompt_path: promptPath }),
  session: () => request<SessionStatus>("GET", "/session"),
  sessionStart: (confirm = false) => request<SessionStatus>("POST", "/session/start", { confirm }),
  sessionStop: (confirm = false) => request<SessionStatus>("POST", "/session/stop", { confirm }),
  detect: () => request<DetectResponse>("GET", "/detect"),
  detectTerminal: () => request<{ ok: boolean; terminal_path: string; found: boolean }>("GET", "/detect-terminal"),
  saveConfig: (body: Record<string, unknown>) => request<DetectResponse & { config_path: string }>("POST", "/config/save", body),
  eas: () => request<{ ok: boolean; eas: EaInfo[] }>("GET", "/eas"),
  setPreview: (body: Record<string, unknown>) => request<SetPreview>("POST", "/set-preview", body),
  optimizerPreview: (spec: Record<string, unknown>) =>
    request<OptimizerPreview>("POST", "/optimizer/preview", { spec }),
  jobs: () => request<{ ok: boolean; jobs: Job[] }>("GET", "/jobs"),
  job: (id: string) => request<{ ok: boolean; job: Job }>("GET", `/jobs/${encodeURIComponent(id)}`),
  submitJob: (type: string, params: Record<string, unknown>, title = "") =>
    request<{ ok: boolean; job: Job }>("POST", "/jobs", { type, params, title }),
  cancelJob: (id: string) => request<{ ok: boolean }>("POST", `/jobs/${encodeURIComponent(id)}/cancel`),
};
