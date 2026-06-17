// Thin typed client over the localhost-only MT5 Research Agent HTTP API.
// The UI never duplicates backend logic - it only calls these endpoints.

import type {
  AgentPlan,
  AiStatus,
  AppConfig,
  DetectResponse,
  EaCreateResult,
  EaInfo,
  HealthResponse,
  Job,
  LatestRun,
  LeaderboardResponse,
  OptimizerPreview,
  PlanResult,
  ReportAnalysis,
  ReportStatus,
  StrategyBoard,
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

// Distinguishes "the backend socket isn't answering yet" (offline / still
// starting) from a real HTTP error the server returned. The UI uses `kind` to
// show "Starting backend..." with a retry instead of a raw "Failed to fetch".
export type ApiErrorKind = "offline" | "http" | "parse";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(message: string, kind: ApiErrorKind, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

export function isOffline(err: unknown): boolean {
  return err instanceof ApiError && err.kind === "offline";
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  retries = 2,
): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(`${getApiBase()}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      // Network-level failure ("Failed to fetch"): backend not up yet. Retry a
      // couple of times with backoff before surfacing an offline error.
      lastErr = new ApiError("Backend is not responding", "offline");
      if (attempt < retries) {
        await sleep(250 * (attempt + 1));
        continue;
      }
      throw lastErr;
    }

    const text = await response.text();
    let parsed: unknown = {};
    try {
      parsed = text ? JSON.parse(text) : {};
    } catch {
      throw new ApiError(`Non-JSON response (${response.status}) from ${path}`, "parse", response.status);
    }
    if (!response.ok) {
      const detail = (parsed as { error?: string }).error || `HTTP ${response.status}`;
      throw new ApiError(detail, "http", response.status);
    }
    return parsed as T;
  }
  throw lastErr ?? new ApiError("Backend is not responding", "offline");
}

// Lightweight, no-retry health probe used by the shell's status poller.
export async function pingHealth(): Promise<boolean> {
  try {
    await request<HealthResponse>("GET", "/health", undefined, 0);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  health: () => request<HealthResponse>("GET", "/health"),
  config: () => request<{ ok: boolean; config: AppConfig }>("GET", "/config"),
  tools: () => request<{ ok: boolean; tools: string[] }>("GET", "/tools"),
  runs: () => request<RunsResponse>("GET", "/runs"),
  leaderboard: () => request<LeaderboardResponse>("GET", "/leaderboard"),
  aiStatus: () => request<AiStatus>("GET", "/ai/status"),
  report: (testId: string) => request<ReportStatus>("GET", `/reports/${encodeURIComponent(testId)}`),
  reportAnalysis: (testId: string) =>
    request<ReportAnalysis>("GET", `/reports/${encodeURIComponent(testId)}/analysis`),
  latestRun: () => request<LatestRun>("GET", "/latest-run"),
  strategyBoard: () => request<StrategyBoard>("GET", "/strategy-board"),
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
  agentParse: (prompt: string, mode?: string) =>
    request<AgentPlan>("POST", "/agent/parse", { prompt, mode }),
};
