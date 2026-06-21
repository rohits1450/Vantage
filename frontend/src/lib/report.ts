import { runBacktest } from "./backtest";
import { loadMarketDataset } from "./cmc";
import { buildStrategySpec } from "./strategy";
import { ASSETS, RISK_PROFILES, StrategyRequest, StrategyResponse, TIMEFRAMES } from "./types";

export async function createStrategyReport(input: Partial<StrategyRequest> = {}): Promise<StrategyResponse> {
  const request = normalizeRequest(input);
  const dataset = await loadMarketDataset(request);
  const spec = buildStrategySpec(request, dataset.source, dataset.endpoint, dataset.candles.length);
  const result = runBacktest(dataset.candles, spec, request);

  const response: StrategyResponse = {
    request,
    dataset: {
      source: dataset.source,
      sourceLabel: dataset.sourceLabel,
      endpoint: dataset.endpoint,
      fallbackReason: dataset.fallbackReason,
      firstCandle: dataset.candles[0].time,
      lastCandle: dataset.candles[dataset.candles.length - 1].time,
      candleCount: dataset.candles.length
    },
    spec,
    metrics: result.metrics,
    equityCurve: result.equityCurve,
    trades: result.trades,
    summary: result.summary
  };

  // Fire-and-forget: forward to agent if configured and signal is strong.
  // Never awaited — never blocks the return value.
  forwardSignalToAgent(response);

  return response;
}

export function normalizeRequest(input: Partial<StrategyRequest> | null | undefined): StrategyRequest {
  const safeInput = input ?? {};
  const asset = safeInput.asset && ASSETS.includes(safeInput.asset) ? safeInput.asset : "BNB";
  const timeframe = safeInput.timeframe && TIMEFRAMES.includes(safeInput.timeframe) ? safeInput.timeframe : "4h";
  const riskProfile = safeInput.riskProfile && RISK_PROFILES.includes(safeInput.riskProfile) ? safeInput.riskProfile : "balanced";

  return {
    asset,
    timeframe,
    riskProfile,
    maxDrawdownPct: clamp(Number(safeInput.maxDrawdownPct ?? 18), 5, 45),
    startingEquity: clamp(Number(safeInput.startingEquity ?? 10_000), 1_000, 1_000_000),
    feeBps: clamp(Number(safeInput.feeBps ?? 10), 0, 100),
    slippageBps: clamp(Number(safeInput.slippageBps ?? 8), 0, 250),
    lookbackBars: Math.round(clamp(Number(safeInput.lookbackBars ?? 700), 100, 1000))
  };
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

// ─── Agent Signal Forwarding (fire-and-forget, never blocks the report) ───────

interface PendingSignal {
  payload: Record<string, unknown>;
  attempts: number;
}

// In-memory retry queue — capped at 10 items, 3 attempts max, 10s retry interval
const _pendingSignals: PendingSignal[] = [];
let _retryTimer: ReturnType<typeof setInterval> | null = null;

function _flushSignalQueue(): void {
  const ORCHESTRATOR_URL = process.env.AGENT_ORCHESTRATOR_URL;
  if (!ORCHESTRATOR_URL || _pendingSignals.length === 0) return;

  const item = _pendingSignals.shift();
  if (!item) return;

  fetch(`${ORCHESTRATOR_URL}/signal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item.payload),
    signal: AbortSignal.timeout(2000),
  }).catch(() => {
    // On failure: re-queue if we still have attempts left
    if (item.attempts < 3) {
      _pendingSignals.push({ payload: item.payload, attempts: item.attempts + 1 });
    }
  });
}

export function forwardSignalToAgent(report: StrategyResponse): void {
  const ORCHESTRATOR_URL = process.env.AGENT_ORCHESTRATOR_URL;
  if (!ORCHESTRATOR_URL) return; // No-op: agent layer not configured

  // Only forward strong signals (win rate >= 60% and positive return)
  const { metrics, spec } = report;
  const isStrongSignal = metrics.winRatePct >= 60 && metrics.totalReturnPct > 0;
  if (!isStrongSignal) return;

  const hasBottomingSignal = report.summary.some(
    (s) => s.toLowerCase().includes("bottoming") || s.toLowerCase().includes("bullish reversal")
  );

  const payload: Record<string, unknown> = {
    signal_id: `${spec.id}-${Date.now()}`,
    asset: spec.asset,
    direction: hasBottomingSignal ? "LONG" : "CLOSE",
    conviction: Math.min(10, Math.round(metrics.winRatePct / 10)),
    regime: "FROM_EDI_V2",
    risk_pct: spec.parameters.riskPerTradePct,
    slippage_bps: spec.parameters.slippageBps,
    generated_at: spec.generatedAt,
    portfolio_size_usd: report.request.startingEquity,
  };

  // Enqueue (cap at 10 to prevent memory bloat)
  if (_pendingSignals.length < 10) {
    _pendingSignals.push({ payload, attempts: 1 });
  }

  // Start retry timer if not already running
  if (!_retryTimer) {
    _retryTimer = setInterval(_flushSignalQueue, 10_000);
  }

  // Attempt immediately
  _flushSignalQueue();
}
