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

export type VerdictCode = "GOOD" | "PROMISING" | "WEAK" | "REJECT" | "INFRA_ONLY";

export interface Verdict {
  code: VerdictCode;
  label: string;
  confidence: "high" | "medium" | "low";
  reasons: string[];
}

export interface ReportMetrics {
  net_profit: number | null;
  return_pct: number | null;
  profit_factor: number | null;
  drawdown_pct: number | null;
  recovery_factor: number | null;
  expected_payoff: number | null;
  total_trades: number | null;
  winrate_pct: number | null;
  average_win: number | null;
  average_loss: number | null;
  risk_reward: number | null;
  long_trades: number | null;
  short_trades: number | null;
}

export interface LongShort {
  available: boolean;
  pnl_available: boolean;
  long_trades: number | null;
  short_trades: number | null;
  long_share_pct: number | null;
  short_share_pct: number | null;
}

export interface DataAvailability {
  summary_metrics: boolean;
  long_short_counts: boolean;
  long_short_pnl: boolean;
  equity_curve: boolean;
  drawdown_curve: boolean;
  monthly_breakdown: boolean;
  weekday_breakdown: boolean;
  session_breakdown: boolean;
}

export interface ReportAnalysis {
  ok: boolean;
  error?: string;
  test_id?: string;
  ea?: string;
  symbol?: string;
  timeframe?: string;
  period?: string;
  model?: string;
  deposit?: number | null;
  run_status?: string;
  decision_reason?: string;
  per_rule_results?: Array<Record<string, unknown>>;
  created_at?: string;
  verdict: Verdict;
  metrics: ReportMetrics;
  split_status: "passed" | "failed" | "pending";
  strengths: string[];
  weaknesses: string[];
  risk_notes: string[];
  overfit_warnings: string[];
  data_quality_warnings: string[];
  recommended_next_test: string;
  long_short: LongShort;
  data_available: DataAvailability;
  trade_level_note: string;
}

export interface LatestRun extends Partial<ReportAnalysis> {
  ok: boolean;
  has_run: boolean;
}

export interface CandidateCard {
  test_id: string;
  ea: string;
  symbol: string;
  timeframe: string;
  run_kind: string;
  score: number;
  verdict: Verdict;
  profit_factor: number | null;
  drawdown_pct: number | null;
  total_trades: number | null;
  return_pct: number | null;
  validation_status: "passed" | "failed" | "pending";
  passed: boolean;
  reason: string;
  created_at: string;
}

export interface StrategyBoard {
  ok: boolean;
  champion: CandidateCard | null;
  challengers: CandidateCard[];
  survivors: CandidateCard[];
  rejected: CandidateCard[];
  counts: { champion: number; challengers: number; survivors: number; rejected: number };
}

export type AgentMode =
  | "research_existing"
  | "create_new"
  | "optimize"
  | "diagnose"
  | "report";

export interface AgentGoals {
  symbol: string | null;
  timeframe: string | null;
  target_profit_factor: number | null;
  target_return_pct: number | null;
  max_drawdown_pct: number | null;
  min_trades: number | null;
  max_tests: number | null;
  max_runtime_minutes: number | null;
  split_validation: boolean;
}

export interface AgentChip {
  key: keyof AgentGoals;
  label: string;
  value: string | number | boolean;
  kind: "text" | "number" | "bool";
}

export interface AgentPlan {
  ok: boolean;
  mode: AgentMode;
  mode_label: string;
  goals: AgentGoals;
  chips: AgentChip[];
  summary: string;
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
