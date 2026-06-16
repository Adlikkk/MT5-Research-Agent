// Shapes returned by the localhost MT5 Research Agent API (mt5_research_agent/api.py).

export interface HealthResponse {
  ok: boolean;
  version: string;
  service: string;
}

export interface AppConfig {
  terminal_path_configured: boolean;
  portable_mode: boolean;
  artifacts_dir: string;
  results_dir: string;
  report_path_strategy: string;
  max_parallel_mt5_processes: number;
}

export interface RunRow {
  test_id: string;
  run_status: string;
  ea: string;
  symbol: string;
  timeframe?: string;
  pass_fail: "PASS" | "FAIL";
  created_at: string;
}

export interface RunsResponse {
  ok: boolean;
  count: number;
  runs: RunRow[];
}

export interface LeaderboardResponse extends RunsResponse {
  leaderboard_csv: string;
}

export interface AiStatus {
  ok: boolean;
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  max_calls: number;
  max_cost_usd: number;
  calls_used: number;
  est_cost_usd: number;
}

export interface ReportStatus {
  ok: boolean;
  test_id?: string;
  latest_status?: string;
  decision_reason?: string;
  parsed_metrics?: Record<string, unknown>;
  per_rule_results?: Array<Record<string, unknown>>;
  likely_diagnosis?: string;
  error?: string;
}

export interface RequestPreview {
  ok: boolean;
  slug?: string;
  ea?: string;
  symbol?: string;
  timeframe?: string;
  parameter_keys?: string[];
  todos?: string[];
  error?: string;
}

export interface PlanResult {
  ok: boolean;
  plan_path?: string;
  experiment_path?: string;
  error?: string;
}

export interface EaCreateResult {
  ok?: boolean;
  error?: string;
  [key: string]: unknown;
}

export interface SessionInfo {
  pid?: number | null;
  terminal_path?: string;
  started_at?: string;
  status?: string;
  mode?: string;
}

export interface SessionStatus {
  ok: boolean;
  session_active: boolean;
  tracked: boolean;
  process_running: boolean;
  session: SessionInfo | null;
  configured_terminal_path?: string | null;
  message?: string;
  require_confirm?: boolean;
}

export interface DetectCheck {
  label: string;
  status: "PASS" | "WARN" | "FAIL";
  ok: boolean;
  detail: string;
}

export interface DetectResponse {
  ok: boolean;
  checks: DetectCheck[];
}

export interface EaInfo {
  name: string;
  ex5: string;
  expert_value: string;
}

export interface SetPreview {
  ok: boolean;
  set_text: string;
  task: Record<string, unknown>;
}

export interface OptimizerPreview {
  ok: boolean;
  test_id?: string;
  algorithm?: string;
  algorithm_code?: number;
  criterion?: string;
  criterion_code?: number;
  grid_combinations?: number;
  set_text?: string;
  error?: string;
}

export interface Job {
  id: string;
  type: string;
  title: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  message: string;
  logs: string[];
  result: Record<string, unknown> | null;
  error: string;
  created_at: string;
  started_at: string;
  finished_at: string;
  cancel_requested: boolean;
}
