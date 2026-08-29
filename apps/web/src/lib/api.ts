/**
 * AlphaCouncil API Client
 * Type-safe API layer for frontend-backend communication
 */

// Base configuration
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

// Type definitions matching backend models
export interface TradeRecord {
  trade_id: string;
  candidate_id?: string;
  committee_result_id?: string;
  trade_thesis_id?: string;
  risk_evaluation_id?: string;
  instrument_plan_id?: string;
  entry_execution_id?: string;
  position_id?: string;
  exit_execution_id?: string;
  symbol: string;
  instrument_type: string;
  direction: "LONG" | "SHORT";
  discovery_timestamp?: string;
  thesis_timestamp?: string;
  entry_timestamp?: string;
  exit_timestamp?: string;
  entry_price?: number;
  exit_price?: number;
  entry_quantity?: number;
  exit_quantity?: number;
  entry_notional?: number;
  exit_notional?: number;
  realized_pnl?: number;
  return_pct?: number;
  holding_duration_seconds?: number;
  mfe_amount?: number;
  mfe_pct?: number;
  mfe_r_multiple?: number;
  mae_amount?: number;
  mae_pct?: number;
  mae_r_multiple?: number;
  initial_risk_amount?: number;
  r_multiple?: number;
  risk_budget?: number;
  max_position_notional?: number;
  initial_stop?: number;
  exit_reason_codes: string[];
  committee_confidence?: number;
  committee_disagreement?: string;
  instrument_selection_score?: number;
  risk_decision?: string;
  constitution_version?: string;
  data_quality_flags: string[];
  created_at: string;
  updated_at: string;
  version: number;
  // Extended fields for UI
  status?: string;
  current_quantity?: number;
  current_price?: number;
  current_notional?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  mfe?: number;
  mae?: number;
  exit_state?: string;
}

export interface PerformanceSummary {
  total_trades: number;
  committee: {
    trade_count: number;
    wins: number;
    losses: number;
    breakevens: number;
    win_rate?: number;
    directional_accuracy?: number;
    mean_r_multiple?: number;
    median_r_multiple?: number;
    mean_return_pct?: number;
    mean_mfe_pct?: number;
    mean_mae_pct?: number;
    avg_holding_period_seconds?: number;
    mean_committee_confidence?: number;
  };
  calibration: {
    buckets: CalibrationBucket[];
    brier_score?: number;
    ece?: number;
    min_sample_size: number;
    overall_insight: string;
    total_samples: number;
  };
  disagreement: DisagreementAnalytics[];
  regime: RegimeAnalytics[];
  exit_reasons: ExitReasonAnalytics[];
  risk_reduction?: RiskReductionAnalytics;
  signal_attribution: SignalAttribution[];
  agent_performance: Record<string, AgentStats>;
}

export interface CalibrationBucket {
  bucket_low: number;
  bucket_high: number;
  sample_count: number;
  mean_predicted_confidence?: number;
  observed_success_rate?: number;
  calibration_gap?: number;
}

export interface DisagreementAnalytics {
  bucket: "LOW" | "MEDIUM" | "HIGH";
  count: number;
  win_rate?: number;
  directional_accuracy?: number;
  mean_r_multiple?: number;
  mean_return_pct?: number;
}

export interface RegimeAnalytics {
  regime: "STRONG_UP" | "UP" | "NEUTRAL" | "DOWN" | "STRONG_DOWN";
  count: number;
  win_rate?: number;
  mean_r_multiple?: number;
  directional_accuracy?: number;
}

export interface ExitReasonAnalytics {
  reason_category: "HARD_STOP" | "KILL_SWITCH" | "TAKE_PROFIT" | "TRAILING_STOP" | "MAX_HOLDING" | "THESIS_DETERIORATION" | "MAX_LOSS" | "RISK_REDUCTION" | "RECONCILIATION" | "MANUAL" | "UNKNOWN";
  count: number;
  mean_r_multiple?: number;
  mean_return_pct?: number;
  mean_mfe_capture?: number;
  mean_holding_duration_seconds?: number;
}

export interface RiskReductionAnalytics {
  approved_count: number;
  reduced_count: number;
  approved_win_rate?: number;
  reduced_win_rate?: number;
  approved_mean_r?: number;
  reduced_mean_r?: number;
  approved_mae?: number;
  reduced_mae?: number;
  approved_mfe?: number;
  reduced_mfe?: number;
}

export interface SignalAttribution {
  signal_name: string;
  count: number;
  mean_score_when_win?: number;
  mean_score_when_loss?: number;
  win_rate_above_median?: number;
  win_rate_below_median?: number;
}

export interface AgentStats {
  trades_evaluated: number;
  participations: number;
  abstentions: number;
  directional_accuracy?: number;
  mean_confidence?: number;
  brier_score?: number;
  accuracy_when_agreeing?: number;
  accuracy_when_disagreeing?: number;
}

export interface HistoricalContext {
  similar_trade_count: number;
  top_similar_trade_ids: string[];
  win_rate?: number;
  directional_accuracy?: number;
  mean_r_multiple?: number;
  median_r_multiple?: number;
  mean_return_pct?: number;
  mean_mfe_pct?: number;
  mean_mae_pct?: number;
  avg_holding_period_seconds?: number;
  committee_calibration?: PerformanceSummary["calibration"];
  agent_historical_statistics: Record<string, AgentStats>;
  warnings: string[];
  has_sufficient_samples: boolean;
}

export interface SimilarTradeResult {
  trade_id: string;
  similarity_score: number;
  matching_features: SimilarityComponent[];
  differing_features: SimilarityComponent[];
  outcome_type?: "WIN" | "LOSS" | "BREAKEVEN" | "UNKNOWN";
  return_pct?: number;
  r_multiple?: number;
  direction?: string;
  instrument_type?: string;
  committee_confidence?: number;
  disagreement?: string;
}

export interface SimilarityComponent {
  name: string;
  weight: number;
  score: number;
  max_possible: number;
  matching: boolean;
  details: string;
}

export interface CouncilRunRequest {
  max_candidates?: number;
  demo_mode?: boolean;
  universe_mode?: "curated" | "alpaca";
  symbols?: string[];
}

export interface CouncilRunResponse {
  run_id: string;
  status: CouncilRunStatus;
  message: string;
}

export interface CouncilRun {
  run_id: string;
  created_at: string;
  completed_at?: string;
  status: CouncilRunStatus;
  max_candidates: number;
  demo_mode: boolean;
  candidate_set?: Record<string, unknown>;
  candidate_analyses: CandidateAnalysis[];
  candidates_discovered: number;
  candidates_analyzed: number;
  candidates_approved: number;
  candidates_rejected: number;
  errors: string[];
  warnings: string[];
  total_runtime_ms: number;
  stage_timings: Record<string, number>;
}

export type CouncilRunStatus =
  | "STARTED"
  | "DISCOVERING"
  | "COMMITTEE"
  | "RISK"
  | "INSTRUMENT"
  | "EXECUTION_PLANNING"
  | "COMPLETE"
  | "PARTIAL"
  | "FAILED";

export interface CandidateAnalysis {
  symbol: string;
  candidate_rank?: number;
  opportunity_score?: number;
  direction?: string;
  committee_decision?: string;
  committee_confidence?: number;
  committee_disagreement?: string;
  agent_opinions: Record<string, unknown>;
  risk_decision?: string;
  risk_reason?: string;
  risk_budget?: number;
  max_position_notional?: number;
  instrument_type?: string;
  instrument_selection_reason?: string;
  execution_plan_id?: string;
  execution_authorized: boolean;
  dry_run: boolean;
  status: string;
  error?: string;
}

export interface CouncilRunEvent {
  event_type: CouncilRunEventType;
  timestamp: string;
  run_id: string;
  message: string;
  data: Record<string, unknown>;
}

export type CouncilRunEventType =
  | "run_started"
  | "market_scan_started"
  | "candidate_found"
  | "committee_started"
  | "agent_completed"
  | "committee_completed"
  | "risk_evaluation_started"
  | "risk_decision"
  | "instrument_selection_started"
  | "instrument_selected"
  | "execution_dry_run_started"
  | "execution_authorized"
  | "run_completed"
  | "run_failed";

export interface SystemHealth {
  status: "healthy" | "degraded" | "unhealthy";
  trading_mode: string;
  paper_trading: boolean;
  services: {
    discovery: string;
    committee: string;
    risk: string;
    instrument: string;
    execution: string;
    memory: string;
  };
}

export interface SystemConfig {
  trading_mode: string;
  enable_execution: boolean;
  enable_paper_execution: boolean;
  alpaca_live_trade: boolean;
  market_data_available: boolean;
  options_data_available: boolean;
  llm_available: boolean;
}

// API client functions
async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

// Trade endpoints
export const tradesApi = {
  list: (limit = 100) => fetchApi<TradeRecord[]>(`/memory/trades?limit=${limit}`),
  get: (tradeId: string) => fetchApi<TradeRecord>(`/memory/trades/${tradeId}`),
};

// Performance endpoints
export const performanceApi = {
  getSummary: () => fetchApi<PerformanceSummary>("/memory/performance"),
  getCalibration: () => fetchApi<PerformanceSummary["calibration"]>("/memory/calibration"),
  recomputeCalibration: () => fetchApi<PerformanceSummary["calibration"]>("/memory/calibration/recompute", { method: "POST" }),
};

export interface AgentPerformanceRecord {
  trade_id: string;
  agent_name: string;
  stance: string;
  confidence: number;
  participated: boolean;
  abstained: boolean;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  direction_correct?: boolean;
  calibration_target?: number;
  committee_agreement?: boolean;
  trade_profitable?: boolean;
  r_multiple?: number;
  created_at: string;
}

// Agent endpoints
export const agentsApi = {
  getPerformance: (agentName: string) => fetchApi<AgentPerformanceRecord[]>(`/memory/agents/${agentName}`),
};

// Analytics endpoints
export const analyticsApi = {
  getDisagreement: () => fetchApi<DisagreementAnalytics[]>("/memory/disagreement"),
  getExitReasons: () => fetchApi<ExitReasonAnalytics[]>("/memory/exits"),
  getHistoricalContext: (params: Record<string, unknown>) =>
    fetchApi<HistoricalContext>("/memory/context", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  getSimilarTrades: (params: Record<string, unknown>) =>
    fetchApi<SimilarTradeResult[]>("/memory/similar", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};

// Council endpoints
export const councilApi = {
  startRun: (request: CouncilRunRequest) =>
    fetchApi<CouncilRunResponse>("/council/run", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  getRun: (runId: string) => fetchApi<CouncilRun>(`/council/run/${runId}`),
  getEvents: (runId: string) => fetchApi<CouncilRunEvent[]>(`/council/run/${runId}/events`),
  getStatus: () => fetchApi<SystemHealth>("/council/status"),
};

// System endpoints
export const systemApi = {
  health: () => fetchApi<SystemHealth>("/health"),
  config: () => fetchApi<SystemConfig>("/config"),
};