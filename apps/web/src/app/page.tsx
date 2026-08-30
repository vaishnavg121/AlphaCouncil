"use client";

import { useEffect, useState, useRef } from "react";
import {
  tradesApi,
  performanceApi,
  analyticsApi,
  councilApi,
  systemApi,
  type TradeRecord,
  type PerformanceSummary,
  type HistoricalContext,
  type SimilarTradeResult,
  type SystemHealth,
  type SystemConfig,
  type CouncilRun,
  type CouncilRunEvent,
  type CouncilRunStatus,
  type AgentOpinionSnapshot,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckCircle, Loader2, TrendingUp, Target, Shield, Zap, Brain, BarChart3, Activity, AlertCircle, Info, ArrowRight, DollarSign, TrendingUp as TrendingUpIcon } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { format } from "date-fns";

const STATUS_COLORS: Record<string, string> = {
  WIN: "bg-green-100 text-green-800",
  LOSS: "bg-red-100 text-red-800",
  BREAKEVEN: "bg-yellow-100 text-yellow-800",
  UNKNOWN: "bg-gray-100 text-gray-800",
};

const RUN_STATUS_COLORS: Record<CouncilRunStatus, string> = {
  STARTED: "bg-blue-100 text-blue-800",
  DISCOVERING: "bg-blue-100 text-blue-800",
  COMMITTEE: "bg-purple-100 text-purple-800",
  RISK: "bg-orange-100 text-orange-800",
  INSTRUMENT: "bg-cyan-100 text-cyan-800",
  EXECUTION_PLANNING: "bg-indigo-100 text-indigo-800",
  COMPLETE: "bg-green-100 text-green-800",
  PARTIAL: "bg-yellow-100 text-yellow-800",
  FAILED: "bg-red-100 text-red-800",
};

const AGENT_COLORS: Record<string, string> = {
  QUANT: "bg-blue-100 text-blue-800",
  BULL: "bg-green-100 text-green-800",
  BEAR: "bg-red-100 text-red-800",
  REGIME: "bg-purple-100 text-purple-800",
};

type DashboardStatus = "LOADING" | "SUCCESS" | "DEGRADED" | "ERROR";

function displayLabel(value?: string | null): string {
  if (!value) return "Not available";
  const words = value.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function safeDashboardError(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={STATUS_COLORS[status] || "bg-gray-100 text-gray-800"} variant="outline">
      {displayLabel(status)}
    </Badge>
  );
}

function RunStatusBadge({ status }: { status: CouncilRunStatus }) {
  return (
    <Badge className={RUN_STATUS_COLORS[status] || "bg-gray-100 text-gray-800"} variant="outline">
      {displayLabel(status)}
    </Badge>
  );
}

function AgentBadge({ agent, className }: { agent: string; className?: string }) {
  return (
    <Badge className={`${AGENT_COLORS[agent] || "bg-gray-100 text-gray-800"} ${className || ""}`} variant="outline">
      {agent}
    </Badge>
  );
}

// String-returning formatting functions
function formatCurrency(value?: number): string {
  if (value === undefined || value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value?: number): string {
  if (value === undefined || value === null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function formatRMultiple(value?: number): string {
  if (value === undefined || value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}R`;
}

function formatConfidence(value?: number): string {
  if (value === undefined || value === null) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

function formatNumber(value?: number, digits = 1): string {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

// Color helper for percent values
function getPercentColor(value?: number): string {
  if (value === undefined || value === null) return "text-gray-600";
  return value > 0 ? "text-green-600" : value < 0 ? "text-red-600" : "text-gray-600";
}

function getRMultipleColor(value?: number): string {
  if (value === undefined || value === null) return "text-gray-600";
  return value > 0 ? "text-green-600" : value < 0 ? "text-red-600" : "text-gray-600";
}

export default function Dashboard() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [historicalContext, setHistoricalContext] = useState<HistoricalContext | null>(null);
  const [similarTrades, _setSimilarTrades] = useState<SimilarTradeResult[]>([]); // eslint-disable-line @typescript-eslint/no-unused-vars
  const [councilRun, setCouncilRun] = useState<CouncilRun | null>(null);
  const [runEvents, setRunEvents] = useState<CouncilRunEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState("overview"); // eslint-disable-line @typescript-eslint/no-unused-vars
  const [councilStatus, setCouncilStatus] = useState<SystemHealth | null>(null); // eslint-disable-line @typescript-eslint/no-unused-vars
  const [dashboardStatus, setDashboardStatus] = useState<DashboardStatus>("LOADING");
  const [dashboardIssues, setDashboardIssues] = useState<string[]>([]);
  const mountedRef = useRef(true);

  const applyCanonicalRun = (run: CouncilRun) => {
    setCouncilRun(run);
    setActiveRunId(run.run_id);
    const candidateIds = run.candidate_analyses.map((candidate) => candidate.candidate_id);
    let storedCandidateId: string | null = null;
    try {
      storedCandidateId = window.localStorage.getItem("alphacouncil.selectedCandidateId");
    } catch {
      storedCandidateId = null;
    }
    setSelectedCandidateId((current) => {
      if (current && candidateIds.includes(current)) return current;
      if (storedCandidateId && candidateIds.includes(storedCandidateId)) return storedCandidateId;
      return candidateIds[0] || null;
    });
  };

  const selectCandidate = (candidateId: string) => {
    setSelectedCandidateId(candidateId);
    try {
      window.localStorage.setItem("alphacouncil.selectedCandidateId", candidateId);
    } catch {
      // Selection remains valid for this session when storage is unavailable.
    }
  };

  const loadDashboard = async () => {
    if (!mountedRef.current) return;
    try {
      const [healthResult, configResult, tradesResult, performanceResult, contextResult, councilResult, currentRunResult] = await Promise.allSettled([
        systemApi.health(),
        systemApi.config(),
        tradesApi.list(20),
        performanceApi.getSummary(),
        analyticsApi.getHistoricalContext({ direction: "LONG", instrument_type: "STOCK" }),
        councilApi.getStatus(),
        councilApi.getCurrentRun(),
      ]);
      if (!mountedRef.current) return;
      const issues: string[] = [];
      let criticalFailures = 0;

      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      else {
        issues.push(`System health: ${safeDashboardError(healthResult.reason)}`);
        criticalFailures += 1;
      }

      if (configResult.status === "fulfilled") setConfig(configResult.value);
      else {
        issues.push(`Safety configuration: ${safeDashboardError(configResult.reason)}`);
        criticalFailures += 1;
      }

      if (tradesResult.status === "fulfilled") setTrades(tradesResult.value);
      else issues.push(`Trade history: ${safeDashboardError(tradesResult.reason)}`);

      if (performanceResult.status === "fulfilled") setPerformance(performanceResult.value);
      else issues.push(`Performance: ${safeDashboardError(performanceResult.reason)}`);

      if (contextResult.status === "fulfilled") setHistoricalContext(contextResult.value);
      else issues.push(`Historical context: ${safeDashboardError(contextResult.reason)}`);

      if (councilResult.status === "fulfilled") setCouncilStatus(councilResult.value);
      else issues.push(`Council status: ${safeDashboardError(councilResult.reason)}`);

      if (currentRunResult.status === "fulfilled" && currentRunResult.value) {
        applyCanonicalRun(currentRunResult.value);
      } else if (currentRunResult.status === "rejected") {
        issues.push(`Current council run: ${safeDashboardError(currentRunResult.reason)}`);
      }

      setDashboardIssues(issues);
      setDashboardStatus(
        criticalFailures === 2 ? "ERROR" : issues.length > 0 ? "DEGRADED" : "SUCCESS",
      );
    } catch {
      if (mountedRef.current) {
        setDashboardIssues(["Dashboard loading failed unexpectedly"]);
        setDashboardStatus("ERROR");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadDashboard();
    const interval = setInterval(loadDashboard, 30000);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
    // The dashboard owns one polling lifecycle; request helpers intentionally use current state setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runCouncil = async (demoMode = true) => {
    try {
      const response = await councilApi.startRun({
        max_candidates: 5,
        demo_mode: demoMode,
        universe_mode: "curated",
      });
      setActiveRunId(response.run_id);
      setCouncilRun(null);
      setSelectedCandidateId(null);
      setRunEvents([]);
      pollRun(response.run_id);
    } catch (e) {
      console.error("Failed to start council run:", e);
      setDashboardIssues([`Council run: ${safeDashboardError(e)}`]);
      setDashboardStatus("DEGRADED");
    }
  };

  const pollRun = async (runId: string) => {
    try {
      const run = await councilApi.getRun(runId);
      applyCanonicalRun(run);
      const events = await councilApi.getEvents(runId);
      setRunEvents(events);
      if (run.status !== "COMPLETE" && run.status !== "PARTIAL" && run.status !== "FAILED") {
        setTimeout(() => pollRun(runId), 2000);
      }
    } catch (e) {
      console.error("Failed to poll run:", e);
      setDashboardIssues([`Council run status: ${safeDashboardError(e)}`]);
      setDashboardStatus("DEGRADED");
    }
  };

  const runInProgress = Boolean(
    activeRunId &&
      (!councilRun || !["COMPLETE", "PARTIAL", "FAILED"].includes(councilRun.status)),
  );
  const candidates = councilRun?.candidate_analyses ?? [];
  const selectedCandidate =
    candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ??
    candidates[0] ??
    null;

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-12 w-12 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-[1400px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <Target className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">AlphaCouncil</h1>
              <p className="text-xs text-gray-500">Adversarial AI Investment Committee</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <span className="px-2 py-1 rounded-full bg-green-100 text-green-800 font-medium">
                Trading Mode: {config?.trading_mode?.toUpperCase() || "PAPER"}
              </span>
              <span className="px-2 py-1 rounded-full bg-blue-100 text-blue-800 font-medium">
                Execution: {config?.enable_paper_execution ? "PAPER ENABLED" : "DRY RUN"}
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => runCouncil(true)}
              disabled={runInProgress}
            >
              <Zap className="w-4 h-4 mr-2" />
              Run Council (Demo)
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 py-6">
        <div
          className={`mb-4 rounded-lg border p-3 text-sm ${
            dashboardStatus === "SUCCESS"
              ? "border-green-200 bg-green-50 text-green-800"
              : dashboardStatus === "DEGRADED"
                ? "border-yellow-200 bg-yellow-50 text-yellow-800"
                : "border-red-200 bg-red-50 text-red-800"
          }`}
          role="status"
          data-testid="dashboard-status"
        >
          <strong>Dashboard: {dashboardStatus}</strong>
          {dashboardIssues.length > 0 && (
            <span className="ml-2">{dashboardIssues.join(" · ")}</span>
          )}
        </div>

        <div
          className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5"
          data-testid="system-dimensions"
        >
          <SystemDimension label="Backend" value={health?.services?.backend || health?.status} />
          <SystemDimension label="Alpaca" value={health?.services?.alpaca || "not_checked"} />
          <SystemDimension label="NVIDIA" value={health?.services?.nvidia || "not_required"} />
          <SystemDimension label="Trading Mode" value={config?.trading_mode || "paper"} />
          <SystemDimension
            label="Execution"
            value={config?.enable_paper_execution ? "paper_enabled" : "disabled"}
          />
        </div>

        {/* System Status Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
          <MetricCard
            title="Paper Equity"
            value={formatCurrency(100000)}
            icon={<DollarSign className="w-5 h-5 text-green-600" />}
            subtitle="PAPER ACCOUNT"
          />
          <MetricCard
            title="Daily P&L"
            value={formatCurrency(0)}
            icon={<TrendingUp className="w-5 h-5 text-gray-600" />}
            subtitle={formatPercent(0)}
          />
          <MetricCard
            title="Managed Positions"
            value={trades.filter(t => t.status === "OPEN").length.toString()}
            icon={<Activity className="w-5 h-5 text-blue-600" />}
            subtitle="Active"
          />
          <MetricCard
            title="Risk Utilization"
            value={formatPercent(0)}
            icon={<Shield className="w-5 h-5 text-orange-600" />}
            subtitle="Kill Switch: OFF"
          />
          <MetricCard
            title="Today's Trades"
            value={trades.length.toString()}
            icon={<TrendingUpIcon className="w-5 h-5 text-purple-600" />}
            subtitle={formatPercent(0) + " win rate"}
          />
          <MetricCard
            title="Backend"
            value={health?.status === "healthy" ? "Healthy" : "Degraded"}
            icon={<CheckCircle className="w-5 h-5 text-green-600" />}
            subtitle={`Alpaca: ${displayLabel(health?.services?.alpaca)}`}
          />
        </div>

        <Tabs defaultValue="overview" onValueChange={setSelectedTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-7">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
            <TabsTrigger value="committee">Committee</TabsTrigger>
            <TabsTrigger value="risk">Risk</TabsTrigger>
            <TabsTrigger value="execution">Execution</TabsTrigger>
            <TabsTrigger value="positions">Positions</TabsTrigger>
            <TabsTrigger value="memory">Memory</TabsTrigger>
          </TabsList>

          {/* OVERVIEW TAB */}
          <TabsContent value="overview" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {/* Portfolio Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <DollarSign className="w-5 h-5" />
                    Portfolio Summary
                  </CardTitle>
                  <CardDescription>PAPER TRADING ACCOUNT</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <StatRow label="Equity" value={formatCurrency(100000)} />
                    <StatRow label="Cash" value={formatCurrency(50000)} />
                    <StatRow label="Buying Power" value={formatCurrency(200000)} />
                    <StatRow label="Daily P&L" value={formatCurrency(0)} change={<span className={getPercentColor(0)}>{formatPercent(0)}</span>} />
                    <StatRow label="Unrealized P&L" value={formatCurrency(0)} />
                    <StatRow label="Positions" value={trades.filter(t => t.status === "OPEN").length.toString()} />
                  </div>
                </CardContent>
              </Card>

              {/* Risk Status */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="w-5 h-5" />
                    Risk Constitution
                  </CardTitle>
                  <CardDescription>Deterministic risk authority</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-2">
                    <RiskRow label="Kill Switch" value="INACTIVE" status="ok" />
                    <RiskRow label="Daily Loss Limit" value="OK" status="ok" />
                    <RiskRow label="Max Drawdown" value="OK" status="ok" />
                    <RiskRow label="Position Concentration" value="OK" status="ok" />
                    <RiskRow label="Gross Exposure" value="OK" status="ok" />
                    <RiskRow label="Max Positions" value="OK" status="ok" />
                  </div>
                </CardContent>
              </Card>

              {/* Recent Performance */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" />
                    Performance Snapshot
                  </CardTitle>
                  <CardDescription>Recent PAPER trades</CardDescription>
                </CardHeader>
                <CardContent>
                  {performance ? (
                    <div className="space-y-3">
                      <StatRow label="Total Trades" value={performance.total_trades.toString()} />
                      <StatRow label="Win Rate" value={<span className={getPercentColor(performance.committee.win_rate)}>{formatPercent(performance.committee.win_rate)}</span>} />
                      <StatRow label="Mean R" value={<span className={getRMultipleColor(performance.committee.mean_r_multiple)}>{formatRMultiple(performance.committee.mean_r_multiple)}</span>} />
                      <StatRow label="Median R" value={<span className={getRMultipleColor(performance.committee.median_r_multiple)}>{formatRMultiple(performance.committee.median_r_multiple)}</span>} />
                      <StatRow label="Mean Return" value={<span className={getPercentColor(performance.committee.mean_return_pct)}>{formatPercent(performance.committee.mean_return_pct)}</span>} />
                      <StatRow label="Calibration" value={<span className="capitalize">{performance.calibration.overall_insight.toLowerCase()}</span>} />
                    </div>
                  ) : (
                    <p className="text-gray-500 text-sm">No trades yet. Run a council to generate data.</p>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Active Council Run */}
            {councilRun && (
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="w-5 h-5" />
                    Canonical Council Run
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {councilRun.demo_mode && <Badge variant="outline">SYNTHETIC DEMO</Badge>}
                    <RunStatusBadge status={councilRun.status} />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="flex flex-wrap gap-4 text-sm">
                      <div>
                        <span className="text-gray-500">Run ID:</span>
                        <code className="ml-2 font-mono text-xs">{councilRun.run_id}</code>
                      </div>
                      <div>
                        <span className="text-gray-500">Candidates:</span>
                        <span className="ml-2 font-medium">
                          {councilRun.candidates_analyzed} analyzed / {councilRun.candidates_approved} approved
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Runtime:</span>
                        <span className="ml-2 font-mono">
                          {(councilRun.total_runtime_ms / 1000).toFixed(1)}s
                        </span>
                      </div>
                      {selectedCandidate && (
                        <div>
                          <span className="text-gray-500">Selected:</span>
                          <span className="ml-2 font-medium">{selectedCandidate.symbol}</span>
                        </div>
                      )}
                    </div>
                    {runEvents.length > 0 && (
                      <div className="max-h-64 overflow-y-auto">
                        <h4 className="font-medium mb-2">Activity Timeline</h4>
                        <div className="space-y-1">
                          {runEvents.slice(-10).map((event, i) => (
                            <EventRow key={i} event={event} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* OPPORTUNITIES TAB */}
          <TabsContent value="opportunities" className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Target className="w-5 h-5" />
                    Opportunity Discovery
                  </CardTitle>
                  <CardDescription>M2 candidates from the canonical CouncilRun</CardDescription>
                </div>
                {councilRun?.demo_mode && <Badge variant="outline">SYNTHETIC DEMO</Badge>}
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Symbol</TableHead>
                        <TableHead>Score</TableHead>
                        <TableHead>Direction</TableHead>
                        <TableHead>Trend</TableHead>
                        <TableHead>Momentum</TableHead>
                        <TableHead>RSI</TableHead>
                        <TableHead>Volatility</TableHead>
                        <TableHead>Liquidity</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {candidates.length > 0 ? (
                        candidates.map((candidate) => (
                          <TableRow
                            key={candidate.candidate_id}
                            className={
                              candidate.candidate_id === selectedCandidate?.candidate_id
                                ? "bg-blue-50"
                                : undefined
                            }
                          >
                            <TableCell className="font-mono font-medium">
                              <button
                                type="button"
                                className="text-blue-700 hover:underline"
                                onClick={() => selectCandidate(candidate.candidate_id)}
                                aria-pressed={candidate.candidate_id === selectedCandidate?.candidate_id}
                              >
                                {candidate.symbol}
                              </button>
                            </TableCell>
                            <TableCell className="font-mono">
                              {formatNumber(candidate.opportunity.opportunity_score.total)}
                            </TableCell>
                            <TableCell>
                              <Badge variant={candidate.direction === "BULLISH" ? "default" : "secondary"}>
                                {displayLabel(candidate.direction)}
                              </Badge>
                            </TableCell>
                            <TableCell>{formatNumber(candidate.opportunity.trend)}</TableCell>
                            <TableCell>{formatNumber(candidate.opportunity.momentum)}</TableCell>
                            <TableCell>{formatNumber(candidate.opportunity.rsi)}</TableCell>
                            <TableCell>{formatNumber(candidate.opportunity.volatility)}</TableCell>
                            <TableCell>{formatNumber(candidate.opportunity.liquidity)}</TableCell>
                            <TableCell>
                              <StatusBadge status={candidate.opportunity.status || "UNKNOWN"} />
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={9} className="text-center text-gray-500 py-8">
                            No opportunities discovered. Run a council to generate candidates.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* Opportunity Detail */}
            {selectedCandidate && (
              <Card>
                <CardHeader>
                  <CardTitle data-testid="selected-candidate">
                    {selectedCandidate.symbol} provenance pipeline
                  </CardTitle>
                  <CardDescription>
                    Candidate ID: {selectedCandidate.candidate_id}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    <PipelineStage title="M1 Market" status="complete" icon={<Activity />} />
                    <PipelineStage title="M2 Discovery" status="complete" icon={<Target />} />
                    <PipelineStage
                      title="M3 Committee"
                      status={selectedCandidate.committee_result ? "complete" : "pending"}
                      icon={<Brain />}
                    />
                    <PipelineStage
                      title="M4 Risk"
                      status={selectedCandidate.risk_evaluation ? "complete" : "pending"}
                      icon={<Shield />}
                    />
                    <PipelineStage
                      title="M5 Instrument"
                      status={selectedCandidate.instrument_plan ? "complete" : "stopped"}
                      icon={<BarChart3 />}
                    />
                    <PipelineStage
                      title="M6 Plan"
                      status={selectedCandidate.execution_plan ? "complete" : "stopped"}
                      icon={<Zap />}
                    />
                  </div>
                  {selectedCandidate.stop_reason_codes.length > 0 && (
                    <p className="mt-4 text-sm text-amber-700">
                      Pipeline stopped: {selectedCandidate.stop_reason_codes.map(displayLabel).join(", ")}
                    </p>
                  )}
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* COMMITTEE TAB */}
          <TabsContent value="committee" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Brain className="w-5 h-5" />
                      Current Council Decision
                    </CardTitle>
                    <CardDescription>
                      {selectedCandidate
                        ? `${selectedCandidate.symbol} · ${selectedCandidate.candidate_id}`
                        : "Run the council to produce a candidate decision."}
                    </CardDescription>
                  </div>
                  {councilRun?.demo_mode && <Badge variant="outline">SYNTHETIC DEMO</Badge>}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedCandidate?.committee_result ? (
                  <>
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
                      <StatBox label="Candidate" value={selectedCandidate.symbol} />
                      <StatBox
                        label="Opportunity Score"
                        value={formatNumber(selectedCandidate.opportunity_score)}
                      />
                      <StatBox
                        label="Decision"
                        value={displayLabel(selectedCandidate.committee_result.decision.decision)}
                      />
                      <StatBox
                        label="Confidence"
                        value={formatConfidence(selectedCandidate.committee_result.decision.committee_confidence)}
                      />
                      <StatBox
                        label="Disagreement"
                        value={displayLabel(selectedCandidate.committee_result.decision.final_disagreement)}
                      />
                    </div>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                      {selectedCandidate.committee_result.final_opinions.map((opinion) => (
                        <AgentCard key={opinion.agent_role} opinion={opinion} />
                      ))}
                    </div>
                    <div className="grid gap-3 md:grid-cols-3 text-sm">
                      <StatRow
                        label="Participating agents"
                        value={selectedCandidate.committee_result.decision.participating_agents.length}
                      />
                      <StatRow
                        label="Abstentions"
                        value={selectedCandidate.committee_result.decision.abstained_agents.length}
                      />
                      <StatRow
                        label="Reason codes"
                        value={selectedCandidate.committee_result.decision.decision_reasons
                          .map(displayLabel)
                          .join(", ")}
                      />
                    </div>
                  </>
                ) : (
                  <p className="text-gray-500">No current candidate committee result.</p>
                )}
              </CardContent>
            </Card>

            {/* Disagreement Analytics */}
            {performance && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    Historical Committee Analytics
                  </CardTitle>
                  <CardDescription>Outcomes by disagreement level</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Disagreement</TableHead>
                        <TableHead>Count</TableHead>
                        <TableHead>Win Rate</TableHead>
                        <TableHead>Directional Accuracy</TableHead>
                        <TableHead>Mean R</TableHead>
                        <TableHead>Mean Return</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {performance.disagreement.map((d) => (
                        <TableRow key={d.bucket}>
                          <TableCell>
                            <Badge variant={d.bucket === "HIGH" ? "destructive" : d.bucket === "MEDIUM" ? "secondary" : "outline"}>
                              {d.bucket}
                            </Badge>
                          </TableCell>
                          <TableCell>{d.count}</TableCell>
                          <TableCell><span className={getPercentColor(d.win_rate)}>{formatPercent(d.win_rate)}</span></TableCell>
                          <TableCell><span className={getPercentColor(d.directional_accuracy)}>{formatPercent(d.directional_accuracy)}</span></TableCell>
                          <TableCell><span className={getRMultipleColor(d.mean_r_multiple)}>{formatRMultiple(d.mean_r_multiple)}</span></TableCell>
                          <TableCell><span className={getPercentColor(d.mean_return_pct)}>{formatPercent(d.mean_return_pct)}</span></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}

            {/* Calibration */}
            {performance && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" />
                    Historical Confidence Calibration
                  </CardTitle>
                  <CardDescription>Brier: {performance.calibration.brier_score?.toFixed(4) || "—"} | ECE: {performance.calibration.ece?.toFixed(4) || "—"}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <h4 className="font-medium mb-2">Calibration Buckets</h4>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Bucket</TableHead>
                            <TableHead>Samples</TableHead>
                            <TableHead>Mean Confidence</TableHead>
                            <TableHead>Observed Accuracy</TableHead>
                            <TableHead>Gap</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {performance.calibration.buckets.map((b, i) => (
                            <TableRow key={i}>
                              <TableCell>{(b.bucket_low * 100).toFixed(0)}%–{(b.bucket_high * 100).toFixed(0)}%</TableCell>
                              <TableCell>{b.sample_count}</TableCell>
                              <TableCell>{formatConfidence(b.mean_predicted_confidence)}</TableCell>
                              <TableCell>{formatConfidence(b.observed_success_rate)}</TableCell>
                              <TableCell className={b.calibration_gap && b.calibration_gap > 0.1 ? "text-red-600" : "text-green-600"}>
                                {b.calibration_gap ? (b.calibration_gap * 100).toFixed(1) + "%" : "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                    <div>
                      <h4 className="font-medium mb-2">Overall Assessment</h4>
                      <div className="p-4 bg-gray-50 rounded-lg">
                        <Badge variant={performance.calibration.overall_insight === "OVERCONFIDENT" ? "destructive" : performance.calibration.overall_insight === "WELL_CALIBRATED" ? "default" : "secondary"}>
                          {displayLabel(performance.calibration.overall_insight)}
                        </Badge>
                        <p className="text-sm text-gray-600 mt-2">
                          {performance.calibration.total_samples} total samples • Min {performance.calibration.min_sample_size} per bucket
                        </p>
                        {performance.calibration.overall_insight === "INSUFFICIENT_DATA" && (
                          <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
                            <Info className="w-4 h-4 inline mr-1" />
                            Not enough data for reliable calibration. Need at least 20 samples per bucket.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* RISK TAB */}
          <TabsContent value="risk" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <CardTitle>Current Candidate Risk Decision</CardTitle>
                    <CardDescription>
                      {selectedCandidate
                        ? `${selectedCandidate.symbol} · M4 deterministic output`
                        : "No candidate selected"}
                    </CardDescription>
                  </div>
                  {selectedCandidate?.risk_evaluation && (
                    <StatusBadge status={selectedCandidate.risk_evaluation.decision} />
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedCandidate?.risk_evaluation ? (
                  <>
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                      <StatBox
                        label="Committee Proposal"
                        value={displayLabel(selectedCandidate.committee_decision)}
                      />
                      <StatBox
                        label="Committee Confidence"
                        value={formatConfidence(selectedCandidate.committee_confidence)}
                      />
                      <StatBox
                        label="Base Risk Budget"
                        value={formatCurrency(
                          selectedCandidate.risk_evaluation.risk_budget?.base_risk_budget,
                        )}
                      />
                      <StatBox
                        label="Final Risk Budget"
                        value={formatCurrency(
                          selectedCandidate.risk_evaluation.risk_budget?.adjusted_risk_budget,
                        )}
                      />
                      <StatBox
                        label="Max Position Notional"
                        value={formatCurrency(
                          selectedCandidate.risk_evaluation.risk_budget?.max_position_notional,
                        )}
                      />
                      <StatBox
                        label="Stop Reference"
                        value={formatCurrency(
                          selectedCandidate.risk_evaluation.risk_budget?.atr_stop_distance,
                        )}
                      />
                      <StatBox
                        label="Reason"
                        value={displayLabel(selectedCandidate.risk_evaluation.reason_code)}
                      />
                      <StatBox
                        label="M4 Version"
                        value={selectedCandidate.risk_evaluation.constitution_version}
                      />
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div>
                        <h4 className="font-medium mb-2">Hard Gates</h4>
                        <div className="space-y-2">
                          {selectedCandidate.risk_evaluation.checks
                            .filter((check) => check.rule_type === "HARD_GATE")
                            .map((check) => (
                              <RiskRow
                                key={check.rule_name}
                                label={check.rule_name}
                                value={check.passed ? "PASS" : displayLabel(check.reason_code)}
                                status={check.passed ? "ok" : "destructive"}
                              />
                            ))}
                        </div>
                      </div>
                      <div>
                        <h4 className="font-medium mb-2">Soft Reductions</h4>
                        <div className="space-y-2">
                          {selectedCandidate.risk_evaluation.checks
                            .filter((check) => check.rule_type === "SOFT_REDUCTION")
                            .map((check) => (
                              <RiskRow
                                key={check.rule_name}
                                label={check.rule_name}
                                value={
                                  check.passed
                                    ? "NONE"
                                    : `-${((1 - Number(check.reduction_factor ?? 1)) * 100).toFixed(0)}%`
                                }
                                status={check.passed ? "ok" : "warning"}
                              />
                            ))}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="rounded border border-amber-200 bg-amber-50 p-4 text-amber-800">
                    No M4 evaluation is available. {selectedCandidate?.stop_reason_codes.map(displayLabel).join(", ")}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="w-5 h-5" />
                  Risk Constitution
                </CardTitle>
                <CardDescription>Deterministic risk authority — AI cannot override</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
                  <AlertCircle className="w-4 h-4 mr-2 inline" />
                  <strong>M4 is the final risk authority.</strong> Historical memory provides context but cannot override current risk rules.
                </div>
                <div className="space-y-3">
                  <RiskRow label="Kill Switch" value="ENFORCED" status="ok" />
                  <RiskRow label="Daily Loss Limit" value="ENFORCED" status="ok" />
                  <RiskRow label="Max Drawdown" value="ENFORCED" status="ok" />
                  <RiskRow label="Position Concentration" value="ENFORCED" status="ok" />
                  <RiskRow label="Gross Exposure" value="ENFORCED" status="ok" />
                  <RiskRow label="Net Exposure" value="ENFORCED" status="ok" />
                  <RiskRow label="Max Positions" value="ENFORCED" status="ok" />
                  <RiskRow label="Correlation Redundancy" value="ENFORCED" status="ok" />
                </div>
                <Separator />
                <h4 className="font-medium mb-2">Soft Reductions</h4>
                <div className="space-y-2">
                  <RiskRow label="Volatility Reduction" value="AVAILABLE" status="ok" />
                  <RiskRow label="Liquidity Reduction" value="AVAILABLE" status="ok" />
                  <RiskRow label="Confidence Reduction" value="AVAILABLE" status="ok" />
                  <RiskRow label="Symbol Concentration" value="AVAILABLE" status="ok" />
                  <RiskRow label="Correlation Reduction" value="AVAILABLE" status="ok" />
                </div>
              </CardContent>
            </Card>

            {/* Risk Reduction Analytics */}
            {performance && performance.risk_reduction && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" />
                    Risk Reduction Analytics
                  </CardTitle>
                  <CardDescription>APPROVED vs REDUCED outcomes</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <StatBox label="Approved Count" value={performance.risk_reduction.approved_count} />
                    <StatBox label="Reduced Count" value={performance.risk_reduction.reduced_count} />
                    <StatBox label="Approved Win Rate" value={<span className={getPercentColor(performance.risk_reduction.approved_win_rate)}>{formatPercent(performance.risk_reduction.approved_win_rate)}</span>} />
                    <StatBox label="Reduced Win Rate" value={<span className={getPercentColor(performance.risk_reduction.reduced_win_rate)}>{formatPercent(performance.risk_reduction.reduced_win_rate)}</span>} />
                    <StatBox label="Approved Mean R" value={<span className={getRMultipleColor(performance.risk_reduction.approved_mean_r)}>{formatRMultiple(performance.risk_reduction.approved_mean_r)}</span>} />
                    <StatBox label="Reduced Mean R" value={<span className={getRMultipleColor(performance.risk_reduction.reduced_mean_r)}>{formatRMultiple(performance.risk_reduction.reduced_mean_r)}</span>} />
                    <StatBox label="Approved MAE" value={<span className={getPercentColor(performance.risk_reduction.approved_mae)}>{formatPercent(performance.risk_reduction.approved_mae)}</span>} />
                    <StatBox label="Reduced MAE" value={<span className={getPercentColor(performance.risk_reduction.reduced_mae)}>{formatPercent(performance.risk_reduction.reduced_mae)}</span>} />
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* EXECUTION TAB */}
          <TabsContent value="execution" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <CardTitle>Current Instrument / Execution Plan</CardTitle>
                    <CardDescription>
                      {selectedCandidate
                        ? `${selectedCandidate.symbol} · same canonical candidate selected across tabs`
                        : "No candidate selected"}
                    </CardDescription>
                  </div>
                  <div className="flex gap-2">
                    {councilRun?.demo_mode && <Badge variant="outline">SYNTHETIC DEMO</Badge>}
                    <Badge variant="secondary">PLAN ONLY</Badge>
                    <Badge variant="destructive">NOT SUBMITTED</Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedCandidate?.instrument_plan ? (
                  <>
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                      <StatBox
                        label="M5 Outcome"
                        value={displayLabel(selectedCandidate.instrument_plan.instrument_type)}
                      />
                      <StatBox
                        label="Direction"
                        value={displayLabel(selectedCandidate.instrument_plan.thesis_direction)}
                      />
                      <StatBox
                        label="Plan ID"
                        value={<span className="text-xs">{selectedCandidate.instrument_plan.plan_id}</span>}
                      />
                      <StatBox
                        label="Selection Reason"
                        value={displayLabel(
                          selectedCandidate.instrument_plan.no_trade_reason ||
                            selectedCandidate.instrument_plan.selection_reasons[0],
                        )}
                      />
                    </div>
                    {selectedCandidate.instrument_plan.equity_plan && (
                      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                        <StatRow
                          label="Side"
                          value={displayLabel(selectedCandidate.instrument_plan.equity_plan.side)}
                        />
                        <StatRow
                          label="Reference price"
                          value={formatCurrency(
                            selectedCandidate.instrument_plan.equity_plan.reference_price,
                          )}
                        />
                        <StatRow
                          label="Quantity ceiling"
                          value={formatNumber(
                            selectedCandidate.instrument_plan.equity_plan.estimated_quantity,
                            4,
                          )}
                        />
                        <StatRow
                          label="Notional ceiling"
                          value={formatCurrency(
                            selectedCandidate.instrument_plan.equity_plan.max_notional,
                          )}
                        />
                      </div>
                    )}
                    {selectedCandidate.instrument_plan.option_plan && (
                      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                        <StatRow label="Option" value={selectedCandidate.instrument_plan.option_plan.contract_symbol} />
                        <StatRow label="Type" value={displayLabel(selectedCandidate.instrument_plan.option_plan.option_type)} />
                        <StatRow label="Strike" value={formatCurrency(selectedCandidate.instrument_plan.option_plan.strike_price)} />
                        <StatRow label="Expiry" value={selectedCandidate.instrument_plan.option_plan.expiration_date} />
                        <StatRow label="DTE" value={selectedCandidate.instrument_plan.option_plan.days_to_expiry} />
                        <StatRow label="Contracts" value={selectedCandidate.instrument_plan.option_plan.planned_contracts} />
                        <StatRow label="Max loss" value={formatCurrency(selectedCandidate.instrument_plan.option_plan.maximum_loss)} />
                        <StatRow label="Spread" value={formatPercent(selectedCandidate.instrument_plan.option_plan.spread_pct)} />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="rounded border border-amber-200 bg-amber-50 p-4 text-amber-800">
                    No M5 instrument plan. Reason: {selectedCandidate?.stop_reason_codes.map(displayLabel).join(", ") || "No council run"}
                  </div>
                )}

                {selectedCandidate?.execution_plan ? (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <strong>M6 Dry-run Execution Plan</strong>
                      <StatusBadge status={selectedCandidate.execution_status} />
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                      <StatRow label="Plan ID" value={<span className="text-xs">{selectedCandidate.execution_plan.execution_plan_id}</span>} />
                      <StatRow label="Side" value={displayLabel(selectedCandidate.execution_plan.side)} />
                      <StatRow label="Quantity" value={formatNumber(selectedCandidate.execution_plan.quantity, 4)} />
                      <StatRow label="Order type" value={displayLabel(selectedCandidate.execution_plan.order_type)} />
                      <StatRow label="Limit price" value={formatCurrency(selectedCandidate.execution_plan.limit_price)} />
                      <StatRow label="TTL" value={`${Math.max(0, Math.round((new Date(selectedCandidate.execution_plan.expires_at).getTime() - new Date(selectedCandidate.execution_plan.created_at).getTime()) / 1000))}s`} />
                      <StatRow label="Authorization" value={selectedCandidate.execution_authorized ? "Authorized" : "Denied — execution disabled"} />
                      <StatRow label="Submission" value="Not submitted" />
                    </div>
                  </div>
                ) : selectedCandidate ? (
                  <div className="rounded border border-gray-200 bg-gray-50 p-4 text-gray-700">
                    <strong>No execution plan.</strong> Reason: {selectedCandidate.stop_reason_codes.concat(selectedCandidate.execution_reason_codes).map(displayLabel).join(", ") || "Upstream stage did not produce a plan"}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="w-5 h-5" />
                  Execution Control
                </CardTitle>
                <CardDescription>Safe paper execution with dry-run by default</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-blue-800">
                  <Info className="w-4 h-4 mr-2 inline" />
                  <strong>Default: DRY RUN.</strong> Paper execution requires explicit user authorization.
                  <br />
                  TRADING_MODE=PAPER • ENABLE_PAPER_EXECUTION={config?.enable_paper_execution ? "true" : "false"} • ALPACA_LIVE_TRADE={config?.alpaca_live_trade ? "true" : "false"}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <Card className="bg-gray-50">
                    <CardHeader>
                      <CardTitle>Execution Safety</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <SafetyRow label="Trading Mode" value="PAPER" status="ok" />
                      <SafetyRow label="Enable Execution" value={config?.enable_execution ? "true" : "false"} status={config?.enable_execution ? "warning" : "ok"} />
                      <SafetyRow label="Paper Execution" value={config?.enable_paper_execution ? "true" : "false"} status="ok" />
                      <SafetyRow label="Live Trading" value={config?.alpaca_live_trade ? "true" : "false"} status={config?.alpaca_live_trade ? "destructive" : "ok"} />
                      <SafetyRow label="Max Plan TTL" value="30s" status="ok" />
                      <SafetyRow label="Idempotency" value="Enabled" status="ok" />
                    </CardContent>
                  </Card>
                  <Card className="bg-gray-50">
                    <CardHeader>
                      <CardTitle>Plan Validity</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <p className="text-sm text-gray-600">Execution plans expire after 30 seconds.</p>
                      <p className="text-sm text-gray-600">Expired plans must be refreshed before submission.</p>
                      <Button variant="outline" size="sm" className="w-full">
                        Refresh Execution Plan
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              </CardContent>
            </Card>

            {/* Execution History */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="w-5 h-5" />
                  Execution History
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Plan ID</TableHead>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Side</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Limit</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Filled</TableHead>
                      <TableHead>Avg Price</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-gray-500 py-8">
                        {councilRun
                          ? "No orders submitted. Demo Mode creates plans but execution remains disabled."
                          : "No executions yet. Run the council to create a plan-only preview."}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* POSITIONS TAB */}
          <TabsContent value="positions" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="w-5 h-5" />
                  Managed Positions
                </CardTitle>
                <CardDescription>Positions managed by AlphaCouncil exit rules</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Side</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Entry</TableHead>
                      <TableHead>Current</TableHead>
                      <TableHead>P&L</TableHead>
                      <TableHead>P&L %</TableHead>
                      <TableHead>MFE</TableHead>
                      <TableHead>MAE</TableHead>
                      <TableHead>Stop</TableHead>
                      <TableHead>Holding</TableHead>
                      <TableHead>Exit Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {trades.filter(t => t.status === "OPEN").length > 0 ? (
                      trades.filter(t => t.status === "OPEN").map((trade) => (
                        <TableRow key={trade.trade_id}>
                          <TableCell className="font-mono font-medium">{trade.symbol}</TableCell>
                          <TableCell>
                            <Badge variant={trade.direction === "LONG" ? "default" : "secondary"}>
                              {trade.direction}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono">{trade.current_quantity?.toString() || "—"}</TableCell>
                          <TableCell className="font-mono">{formatCurrency(trade.entry_price)}</TableCell>
                          <TableCell className="font-mono">{formatCurrency(trade.current_price)}</TableCell>
                          <TableCell className="font-mono">{formatCurrency(trade.realized_pnl)}</TableCell>
                          <TableCell><span className={getPercentColor(trade.return_pct)}>{formatPercent(trade.return_pct)}</span></TableCell>
                          <TableCell><span className={getPercentColor(trade.mfe_pct)}>{formatPercent(trade.mfe_pct)}</span></TableCell>
                          <TableCell><span className={getPercentColor(trade.mae_pct)}>{formatPercent(trade.mae_pct)}</span></TableCell>
                          <TableCell className="font-mono">{formatCurrency(trade.initial_stop)}</TableCell>
                          <TableCell>{formatDuration(trade.holding_duration_seconds)}</TableCell>
                          <TableCell>
                            <StatusBadge status={trade.exit_state || "NONE"} />
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={12} className="text-center text-gray-500 py-8">
                          No managed positions. Demo Mode creates plans but does not submit orders.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Exit Rules */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="w-5 h-5" />
                  Exit Rule Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-6">
                  {[
                    { name: "Kill Switch", status: "NOT TRIGGERED", priority: 1 },
                    { name: "Hard Stop", status: "NOT TRIGGERED", priority: 2 },
                    { name: "Max Loss", status: "NOT TRIGGERED", priority: 3 },
                    { name: "Trailing Stop", status: "NOT TRIGGERED", priority: 4 },
                    { name: "Take Profit", status: "NOT TRIGGERED", priority: 5 },
                    { name: "Max Holding", status: "NOT TRIGGERED", priority: 6 },
                    { name: "Thesis Deterioration", status: "NOT TRIGGERED", priority: 7 },
                  ].map((rule) => (
                    <ExitRuleCard key={rule.name} rule={rule} />
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* MEMORY TAB */}
          <TabsContent value="memory" className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5" />
                  Trading Memory & Calibration
                </CardTitle>
                <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800 text-xs">
                  <Info className="w-3 h-3 mr-1 inline" />
                  All performance data represents <strong>PAPER TRADING</strong> only.
                </div>
              </CardHeader>
              <CardContent>
                {historicalContext?.similar_trade_count && historicalContext.similar_trade_count > 0 ? (
                  <div className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-4">
                      <StatBox label="Similar Trades" value={historicalContext.similar_trade_count} />
                      <StatBox label="Win Rate" value={<span className={getPercentColor(historicalContext.win_rate)}>{formatPercent(historicalContext.win_rate)}</span>} />
                      <StatBox label="Mean R" value={<span className={getRMultipleColor(historicalContext.mean_r_multiple)}>{formatRMultiple(historicalContext.mean_r_multiple)}</span>} />
                      <StatBox label="Median R" value={<span className={getRMultipleColor(historicalContext.median_r_multiple)}>{formatRMultiple(historicalContext.median_r_multiple)}</span>} />
                    </div>
                    {historicalContext.warnings.length > 0 && (
                      <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
                        <AlertTriangle className="w-4 h-4 mr-1 inline" />
                        {historicalContext.warnings.join("; ")}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-500">
                    Trading memory is populated only after completed trade lifecycles. Synthetic Demo Mode data is not added to paper-trading history.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Agent Scorecards */}
            {performance && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Brain className="w-5 h-5" />
                    Agent Scorecards
                  </CardTitle>
                  <CardDescription>Per-agent historical performance</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Agent</TableHead>
                        <TableHead>Evaluated</TableHead>
                        <TableHead>Participations</TableHead>
                        <TableHead>Abstentions</TableHead>
                        <TableHead>Directional Acc.</TableHead>
                        <TableHead>Mean Conf.</TableHead>
                        <TableHead>Brier</TableHead>
                        <TableHead>Acc. Agreeing</TableHead>
                        <TableHead>Acc. Disagreeing</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(performance.agent_performance).map(([agent, stats]) => (
                        <TableRow key={agent}>
                          <TableCell><AgentBadge agent={agent} /></TableCell>
                          <TableCell>{stats.trades_evaluated}</TableCell>
                          <TableCell>{stats.participations}</TableCell>
                          <TableCell>{stats.abstentions}</TableCell>
                          <TableCell><span className={getPercentColor(stats.directional_accuracy)}>{formatPercent(stats.directional_accuracy)}</span></TableCell>
                          <TableCell><span className={getPercentColor(stats.mean_confidence)}>{formatPercent(stats.mean_confidence)}</span></TableCell>
                          <TableCell className="font-mono">{stats.brier_score?.toFixed(4) || "—"}</TableCell>
                          <TableCell><span className={getPercentColor(stats.accuracy_when_agreeing)}>{formatPercent(stats.accuracy_when_agreeing)}</span></TableCell>
                          <TableCell><span className={getPercentColor(stats.accuracy_when_disagreeing)}>{formatPercent(stats.accuracy_when_disagreeing)}</span></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}

            {/* Similar Historical Trades */}
            {similarTrades.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ArrowRight className="w-5 h-5" />
                    Similar Historical Trades
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Trade ID</TableHead>
                        <TableHead>Similarity</TableHead>
                        <TableHead>Outcome</TableHead>
                        <TableHead>Return</TableHead>
                        <TableHead>R</TableHead>
                        <TableHead>Direction</TableHead>
                        <TableHead>Confidence</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {similarTrades.map((t, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono text-xs">{t.trade_id.slice(0, 12)}...</TableCell>
                          <TableCell className="font-mono">{(t.similarity_score * 100).toFixed(0)}%</TableCell>
                          <TableCell>
                            <StatusBadge status={t.outcome_type || "UNKNOWN"} />
                          </TableCell>
                          <TableCell><span className={getPercentColor(t.return_pct)}>{formatPercent(t.return_pct)}</span></TableCell>
                          <TableCell><span className={getRMultipleColor(t.r_multiple)}>{formatRMultiple(t.r_multiple)}</span></TableCell>
                          <TableCell>{t.direction}</TableCell>
                          <TableCell>{formatConfidence(t.committee_confidence)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

// Helper Components
function MetricCard({ title, value, icon, subtitle }: { title: string; value: string; icon: React.ReactNode; subtitle: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-500">{title}</p>
            <p className="text-2xl font-bold text-gray-900">{value}</p>
            <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
          </div>
          <div className="p-2 bg-gray-100 rounded-lg">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function SystemDimension({ label, value }: { label: string; value?: string }) {
  const safeValue = value || "unknown";
  const positive = ["healthy", "paper", "not_required"].includes(safeValue.toLowerCase());
  const neutral = ["disabled", "not_checked", "unavailable"].includes(safeValue.toLowerCase());
  return (
    <div className="flex items-center justify-between rounded-lg border bg-white px-3 py-2 text-sm">
      <span className="text-gray-500">{label}</span>
      <Badge variant={positive ? "default" : neutral ? "outline" : "secondary"}>
        {displayLabel(safeValue)}
      </Badge>
    </div>
  );
}

function StatRow({ label, value, change }: { label: string; value: React.ReactNode; change?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-gray-600">{label}</span>
      <div className="flex items-center gap-2 text-right">
        {value}
        {change && <span className="text-xs">{change}</span>}
      </div>
    </div>
  );
}

function RiskRow({ label, value, status }: { label: string; value: string; status: "ok" | "warning" | "destructive" }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-gray-600">{label}</span>
      <Badge variant={status === "ok" ? "default" : status === "warning" ? "secondary" : "destructive"} className="text-xs">
        {value}
      </Badge>
    </div>
  );
}

function SafetyRow({ label, value, status }: { label: string; value: string; status: "ok" | "warning" | "destructive" }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-gray-600">{label}</span>
      <Badge variant={status === "ok" ? "default" : status === "warning" ? "secondary" : "destructive"} className="text-xs">
        {value}
      </Badge>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="p-4 bg-gray-50 rounded-lg text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="font-mono font-medium text-lg">{value}</p>
    </div>
  );
}

function PipelineStage({
  title,
  status,
  icon,
}: {
  title: string;
  status: "pending" | "complete" | "stopped";
  icon: React.ReactNode;
}) {
  const complete = status === "complete";
  const stopped = status === "stopped";
  return (
    <div className="flex flex-col items-center gap-2 p-4 bg-gray-50 rounded-lg">
      <div className={`p-2 rounded-full ${complete ? "bg-green-100 text-green-600" : stopped ? "bg-amber-100 text-amber-600" : "bg-gray-100 text-gray-400"}`}>
        {icon}
      </div>
      <p className="text-xs font-medium text-center">{title}</p>
      <Badge variant={complete ? "default" : "outline"} className="text-xs">
        {displayLabel(status)}
      </Badge>
    </div>
  );
}

function AgentCard({ opinion }: { opinion: AgentOpinionSnapshot }) {
  const abstained = opinion.stance === "ABSTAIN";
  return (
    <Card>
      <CardContent className="py-5 space-y-2">
        <div className="flex items-center justify-between">
          <AgentBadge agent={opinion.agent_role} />
          <Badge variant="outline">{abstained ? "Abstained" : "Participated"}</Badge>
        </div>
        <p className="text-xl font-bold text-gray-900">{displayLabel(opinion.stance)}</p>
        <p className="text-sm text-gray-500">Confidence: {formatConfidence(opinion.confidence)}</p>
        <p className="text-xs text-gray-600">{opinion.abstain_reason || opinion.thesis}</p>
        <p className="text-xs text-gray-400">
          Evidence: {opinion.supporting_evidence_ids.length} supporting · {opinion.contradicting_evidence_ids.length} contradicting
        </p>
      </CardContent>
    </Card>
  );
}

function ExitRuleCard({ rule }: { rule: { name: string; status: string; priority: number } }) {
  return (
    <div className="p-3 bg-gray-50 rounded-lg border">
      <div className="flex items-center justify-between">
        <span className="font-medium text-sm">{rule.name}</span>
        <Badge variant="outline" className="text-xs">Priority {rule.priority}</Badge>
      </div>
      <p className="text-xs text-gray-500 mt-1">{rule.status}</p>
    </div>
  );
}

function EventRow({ event }: { event: CouncilRunEvent }) {
  return (
    <div className="flex items-center gap-2 text-xs py-1 border-b border-gray-100">
      <span className="text-gray-400 w-20">{format(new Date(event.timestamp), "HH:mm:ss")}</span>
      <Badge variant="outline" className="text-xs">{event.event_type}</Badge>
      <span className="text-gray-600 flex-1">{event.message}</span>
    </div>
  );
}
