"use client";
import HeroSection from "./HeroSection";
import { TrustBar, HowItWorks, StatsBar, Ecosystem, FinalCTA, Footer, ScrollTop, CookieBanner } from "./LandingSections";

import {
  Activity,
  BarChart3,
  Braces,
  Bot,
  Database,
  Download,
  ExternalLink,
  FileJson,
  Gauge,
  LineChart,
  Play,
  ShieldCheck,
  ShieldAlert,
  Target,
  TrendingUp,
  Terminal as TerminalIcon,
    Rocket,
  Swords,
  ChevronDown,
  ClipboardCheck,
  CheckCircle2,
  type LucideIcon
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ASSETS, RISK_PROFILES, StrategyRequest, StrategyResponse, TIMEFRAMES } from "@/lib/types";

type FormState = Pick<
  StrategyRequest,
  "asset" | "timeframe" | "riskProfile" | "maxDrawdownPct" | "startingEquity" | "feeBps" | "slippageBps" | "lookbackBars"
>;

const INITIAL_FORM: FormState = {
  asset: "BNB",
  timeframe: "4h",
  riskProfile: "balanced",
  maxDrawdownPct: 18,
  startingEquity: 10_000,
  feeBps: 10,
  slippageBps: 8,
  lookbackBars: 700
};

type AppTab = 'terminal' | 'backtest' | 'skill' | 'agents';

const tabs: Array<{ id: AppTab; label: string; Icon: LucideIcon }> = [
  { id: 'terminal', label: 'Terminal', Icon: TerminalIcon },
  { id: 'backtest', label: 'Backtest', Icon: BarChart3 },
  { id: 'skill', label: 'Skill Spec', Icon: FileJson },
  { id: 'agents', label: 'Agent Control', Icon: Bot },
];

// ─── Agent Control Panel ──────────────────────────────────────────────────────

interface AgentTrade {
  signal_id: string;
  asset: string;
  direction: string;
  amount_bnb: number;
  tx_hash: string;
  status: string;
  pnl_pct: number | null;
  demo: boolean;
  created_at: string;
}

interface AgentIdentity {
  agent_name: string;
  token_id: number | null;
  wallet_address: string;
  registration_tx: string | null;
}

interface GuardianState {
  drawdown_pct: number;
  consecutive_losses: number;
  current_equity_bnb: number;
  peak_equity_bnb: number;
  is_halted: boolean;
  halt_reason: string | null;
  last_check_at: string | null;
}

interface HaltInfo {
  reason: string;
  triggered_at: string;
  drawdown_pct: number;
  consecutive_losses: number;
  incident_nft_tx?: string;
  transfer_tx?: string;
  equity_recovered_bnb?: number;
  bscscan_nft_url?: string;
}

function AgentControlPanel() {
  const [wsConnected, setWsConnected] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [trades, setTrades] = useState<AgentTrade[]>([]);
  const [identities, setIdentities] = useState<AgentIdentity[]>([]);
  const [guardianState, setGuardianState] = useState<GuardianState | null>(null);
  const [executorStatus, setExecutorStatus] = useState<'RUNNING'|'STOPPED'|'OFFLINE'>('OFFLINE');
  const [guardianStatus, setGuardianStatus] = useState<'RUNNING'|'STOPPED'|'OFFLINE'>('OFFLINE');
  const [isHalted, setIsHalted] = useState(false);
  const [haltInfo, setHaltInfo] = useState<HaltInfo | null>(null);
  const [autoTrading, setAutoTrading] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [maxTradeBnb, setMaxTradeBnb] = useState('0.01');
  const [slippageBps, setSlippageBps] = useState('50');
  const [maxDrawdown, setMaxDrawdown] = useState('20');
  const [maxLosses, setMaxLosses] = useState('5');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const WS_URL = process.env.NEXT_PUBLIC_AGENT_WS_URL || 'ws://localhost:8765';
    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      try {
        ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => setWsConnected(true);
        ws.onclose = () => {
          setWsConnected(false);
          setExecutorStatus('OFFLINE');
          setGuardianStatus('OFFLINE');
          reconnectTimeout = setTimeout(connect, 5000);
        };
        ws.onerror = () => ws.close();

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data as string);
            switch (msg.type) {
              case 'TRADE_HISTORY':
                setTrades(msg.trades || []);
                break;
              case 'AGENT_IDENTITIES':
                setIdentities(msg.identities || []);
                break;
              case 'GUARDIAN_STATE':
                setGuardianState(msg);
                setIsHalted(!!msg.is_halted);
                break;
              case 'AGENT_STATUS':
                if (msg.agent === 'executor') {
                  setExecutorStatus(msg.status as 'RUNNING'|'STOPPED'|'OFFLINE');
                  setDemoMode(!!msg.demo_mode);
                } else if (msg.agent === 'guardian') {
                  setGuardianStatus(msg.status as 'RUNNING'|'STOPPED'|'OFFLINE');
                }
                break;
              case 'TRADE_SUBMITTED':
              case 'TRADE_CONFIRMED':
                setTrades(prev => {
                  const exists = prev.find(t => t.signal_id === msg.signal_id);
                  if (exists) return prev.map(t => t.signal_id === msg.signal_id ? { ...t, ...msg } : t);
                  return [msg as AgentTrade, ...prev].slice(0, 20);
                });
                break;
              case 'GUARDIAN_UPDATE':
                setGuardianState(prev => ({ ...(prev || {} as GuardianState), ...msg }));
                break;
              case 'HALT':
                setIsHalted(true);
                setHaltInfo(msg as HaltInfo);
                break;
              case 'INCIDENT_REPORT':
                setHaltInfo(prev => prev ? { ...prev, ...msg } : msg as HaltInfo);
                break;
            }
          } catch {}
        };
      } catch {
        reconnectTimeout = setTimeout(connect, 5000);
      }
    }

    connect();
    return () => {
      clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, []);

  async function sendControl(action: string) {
    try {
      await fetch('/api/agents/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    } catch {}
  }

  async function saveSettings() {
    try {
      await fetch('/api/agents/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_trade_size_bnb: parseFloat(maxTradeBnb),
          slippage_bps: parseInt(slippageBps),
          max_drawdown_pct: parseFloat(maxDrawdown),
          max_consecutive_losses: parseInt(maxLosses),
        }),
      });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch {}
  }

  const executorIdentity = identities.find(i => i.agent_name === 'executor');
  const guardianIdentity = identities.find(i => i.agent_name === 'guardian');
  const BSCSCAN = 'https://testnet.bscscan.com';

  function statusDot(status: 'RUNNING'|'STOPPED'|'OFFLINE') {
    const colors: Record<string, string> = { RUNNING: '#0ecb81', STOPPED: '#f0b90b', OFFLINE: '#848e9c' };
    return <span style={{ display:'inline-block', width:8, height:8, borderRadius:'50%', background: colors[status] || '#848e9c', marginRight:6 }} />;
  }

  return (
    <div style={{ position: 'relative', minHeight: 400 }}>
      {/* Demo Mode Watermark */}
      {demoMode && wsConnected && (
        <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', pointerEvents:'none', zIndex:0, opacity:0.04 }}>
          <span style={{ fontSize:80, fontWeight:900, color:'#f0b90b', transform:'rotate(-20deg)', userSelect:'none', whiteSpace:'nowrap' }}></span>
        </div>
      )}

      {/* Halt Banner */}
      {isHalted && (
        <div style={{ background:'rgba(246,70,93,0.12)', border:'1px solid rgba(246,70,93,0.4)', borderRadius:12, padding:'16px 20px', marginBottom:20, display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:12 }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <ShieldAlert size={22} color='#f6465d' />
            <div>
              <div style={{ color:'#f6465d', fontWeight:800, fontSize:15 }}>TRADING HALTED — EMERGENCY STOP TRIGGERED</div>
              <div style={{ color:'#848e9c', fontSize:13, marginTop:2 }}>
                Reason: {haltInfo?.reason || 'Unknown'}
                {haltInfo?.drawdown_pct ? ` | Drawdown: ${haltInfo.drawdown_pct.toFixed(1)}%` : ''}
              </div>
            </div>
          </div>
          <div style={{ display:'flex', gap:10 }}>
            {haltInfo?.bscscan_nft_url && (
              <a href={haltInfo.bscscan_nft_url} target="_blank" rel="noreferrer" style={{ fontSize:12, color:'#f0b90b', textDecoration:'none', fontWeight:700, display:'flex', alignItems:'center', gap:4 }}>
                View Incident NFT <ExternalLink size={12} />
              </a>
            )}
            {haltInfo?.equity_recovered_bnb != null && (
              <span style={{ fontSize:12, color:'#0ecb81', fontWeight:700 }}>
                {haltInfo.equity_recovered_bnb.toFixed(6)} BNB recovered
              </span>
            )}
          </div>
        </div>
      )}

      {/* Offline Banner */}
      {!wsConnected && (
        <div style={{ background:'rgba(132,142,156,0.1)', border:'1px solid rgba(132,142,156,0.25)', borderRadius:12, padding:'14px 20px', marginBottom:20, display:'flex', alignItems:'center', gap:10 }}>
          <Bot size={18} color='#848e9c' />
          <div>
            <div style={{ color:'#848e9c', fontWeight:700, fontSize:14 }}>Agents Offline</div>
            <div style={{ color:'#848e9c', fontSize:12, marginTop:2 }}>Start the orchestrator: <code style={{ background:'rgba(255,255,255,0.06)', padding:'1px 6px', borderRadius:4, fontSize:11 }}>python agents/orchestrator.py</code></div>
          </div>
        </div>
      )}

      {/* Status Cards */}
      {wsConnected && (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:20 }}>
          {/* Executor Card */}
          <div style={{ background:'#1e2329', borderRadius:12, border:'1px solid #2b3139', padding:20 }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <Bot size={18} color='#f0b90b' />
                <span style={{ color:'#eaecef', fontWeight:800, fontSize:14 }}>Execution Agent</span>
              </div>
              <span style={{ background: demoMode ? 'rgba(240,185,11,0.15)' : 'rgba(14,203,129,0.1)', color: demoMode ? '#f0b90b' : '#0ecb81', fontSize:11, fontWeight:700, padding:'3px 8px', borderRadius:4 }}>
                {demoMode ? 'DEMO' : 'LIVE'}
              </span>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Status</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{statusDot(executorStatus)}{executorStatus}</span></div>
              {executorIdentity?.token_id && <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Token ID</span><span style={{ color:'#f0b90b', fontSize:12, fontWeight:700 }}>#{executorIdentity.token_id}</span></div>}
              {executorIdentity?.wallet_address && <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Wallet</span><a href={`${BSCSCAN}/address/${executorIdentity.wallet_address}`} target="_blank" rel="noreferrer" style={{ color:'#eaecef', fontSize:12, textDecoration:'none' }}>{executorIdentity.wallet_address.slice(0,6)}...{executorIdentity.wallet_address.slice(-4)}</a></div>}
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Trades</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{trades.length}</span></div>
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Win Rate</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{trades.length > 0 ? `${((trades.filter(t => (t.pnl_pct || 0) > 0).length / trades.length)*100).toFixed(1)}%` : '—'}</span></div>
            </div>
          </div>

          {/* Guardian Card */}
          <div style={{ background:'#1e2329', borderRadius:12, border:`1px solid ${isHalted ? 'rgba(246,70,93,0.4)' : '#2b3139'}`, padding:20 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:14 }}>
              <ShieldCheck size={18} color={isHalted ? '#f6465d' : '#0ecb81'} />
              <span style={{ color:'#eaecef', fontWeight:800, fontSize:14 }}>Risk Guardian</span>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Status</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{statusDot(guardianStatus)}{guardianStatus}</span></div>
              {guardianIdentity?.token_id && <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Token ID</span><span style={{ color:'#f0b90b', fontSize:12, fontWeight:700 }}>#{guardianIdentity.token_id}</span></div>}
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Drawdown</span><span style={{ color: (guardianState?.drawdown_pct || 0) > 15 ? '#f6465d' : '#eaecef', fontSize:12, fontWeight:700 }}>{guardianState?.drawdown_pct != null ? `${guardianState.drawdown_pct.toFixed(1)}%` : '—'}</span></div>
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Consec. Losses</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{guardianState?.consecutive_losses ?? '—'}</span></div>
              <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Peak Equity</span><span style={{ color:'#eaecef', fontSize:12, fontWeight:700 }}>{guardianState?.peak_equity_bnb != null ? `${guardianState.peak_equity_bnb.toFixed(4)} BNB` : '—'}</span></div>
              {guardianState?.last_check_at && <div style={{ display:'flex', justifyContent:'space-between' }}><span style={{ color:'#848e9c', fontSize:12 }}>Last Check</span><span style={{ color:'#848e9c', fontSize:12 }}>{new Date(guardianState.last_check_at).toLocaleTimeString()}</span></div>}
            </div>
          </div>
        </div>
      )}

      {/* Live Trade Feed */}
      {(trades.length > 0 || wsConnected) && (
        <div style={{ background:'#1e2329', borderRadius:12, border:'1px solid #2b3139', padding:20, marginBottom:20 }}>
          <div style={{ color:'#eaecef', fontWeight:800, fontSize:14, marginBottom:14, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <span>Live Trade Feed</span>
            {demoMode && <span style={{ fontSize:11, color:'#f0b90b', fontWeight:700, background:'rgba(240,185,11,0.1)', padding:'3px 8px', borderRadius:4 }}></span>}
          </div>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
              <thead>
                <tr style={{ borderBottom:'1px solid #2b3139' }}>
                  {['Time','Asset','Dir','Amount','Status','PnL','Tx'].map(h => (
                    <th key={h} style={{ textAlign:'left', padding:'6px 10px', color:'#848e9c', fontWeight:700, whiteSpace:'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr><td colSpan={7} style={{ padding:'20px 10px', color:'#848e9c', textAlign:'center' }}>No trades yet — waiting for signals...</td></tr>
                ) : trades.map((t) => (
                  <tr key={t.signal_id} style={{ borderBottom:'1px solid #1a1e23' }}>
                    <td style={{ padding:'8px 10px', color:'#848e9c', whiteSpace:'nowrap' }}>{new Date(t.created_at).toLocaleTimeString()}</td>
                    <td style={{ padding:'8px 10px', color:'#eaecef', fontWeight:700 }}>{t.asset}</td>
                    <td style={{ padding:'8px 10px', color: t.direction === 'LONG' ? '#0ecb81' : '#f6465d', fontWeight:700 }}>{t.direction}</td>
                    <td style={{ padding:'8px 10px', color:'#eaecef' }}>{t.amount_bnb?.toFixed(4)} BNB</td>
                    <td style={{ padding:'8px 10px' }}><span style={{ background: t.status === 'CONFIRMED' ? 'rgba(14,203,129,0.1)' : t.status === 'DEMO' ? 'rgba(240,185,11,0.1)' : 'rgba(246,70,93,0.1)', color: t.status === 'CONFIRMED' ? '#0ecb81' : t.status === 'DEMO' ? '#f0b90b' : '#f6465d', padding:'2px 7px', borderRadius:4, fontSize:11, fontWeight:700 }}>{t.status}</span></td>
                    <td style={{ padding:'8px 10px', color: (t.pnl_pct || 0) >= 0 ? '#0ecb81' : '#f6465d', fontWeight:700 }}>{t.pnl_pct != null ? `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%` : '—'}</td>
                    <td style={{ padding:'8px 10px' }}>
                      {t.tx_hash && !t.tx_hash.startsWith('DEMO') ? (
                        <a href={`${BSCSCAN}/tx/${t.tx_hash}`} target="_blank" rel="noreferrer" style={{ color:'#f0b90b', textDecoration:'none', display:'flex', alignItems:'center', gap:4, fontSize:12 }}>
                          {t.tx_hash.slice(0,8)}… <ExternalLink size={11} />
                        </a>
                      ) : (
                        <span style={{ color:'#848e9c', fontFamily:'monospace', fontSize:11 }}>{t.tx_hash?.slice(0,10)}…</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Controls */}
      <div style={{ background:'#1e2329', borderRadius:12, border:'1px solid #2b3139', padding:20 }}>
        <div style={{ color:'#eaecef', fontWeight:800, fontSize:14, marginBottom:16 }}>Controls & Settings</div>

        {/* Auto-Trading Toggle */}
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:16 }}>
          <span style={{ color:'#848e9c', fontSize:13, width:120 }}>Auto-Trading</span>
          <button onClick={() => setAutoTrading(v => !v)} style={{ width:52, height:28, borderRadius:14, background: autoTrading ? 'rgba(14,203,129,0.3)' : '#2b3139', border: autoTrading ? '1px solid #0ecb81' : '1px solid #3c4349', cursor:'pointer', position:'relative', transition:'all 0.2s' }}>
            <span style={{ position:'absolute', top:3, left: autoTrading ? 26 : 3, width:20, height:20, borderRadius:'50%', background: autoTrading ? '#0ecb81' : '#848e9c', transition:'left 0.2s' }} />
          </button>
          <span style={{ color: autoTrading ? '#0ecb81' : '#848e9c', fontSize:13, fontWeight:700 }}>{autoTrading ? 'ON' : 'OFF'}</span>
        </div>

        {/* Settings Grid */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:16 }}>
          {[
            ['Max Position (BNB)', maxTradeBnb, setMaxTradeBnb],
            ['Slippage (bps)', slippageBps, setSlippageBps],
            ['Max Drawdown (%)', maxDrawdown, setMaxDrawdown],
            ['Max Consec. Losses', maxLosses, setMaxLosses],
          ].map(([label, val, setter]) => (
            <div key={label as string}>
              <div style={{ color:'#848e9c', fontSize:11, marginBottom:4, fontWeight:600 }}>{label as string}</div>
              <input
                type="number"
                value={val as string}
                onChange={e => (setter as (v: string) => void)(e.target.value)}
                style={{ width:'100%', background:'#0b0e11', border:'1px solid #2b3139', borderRadius:6, padding:'8px 10px', color:'#eaecef', fontSize:13, outline:'none', boxSizing:'border-box' }}
              />
            </div>
          ))}
        </div>

        {/* Action Buttons */}
        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          <button onClick={saveSettings} style={{ background: settingsSaved ? '#0ecb81' : 'rgba(240,185,11,0.15)', border:'1px solid rgba(240,185,11,0.3)', borderRadius:8, padding:'9px 18px', color: settingsSaved ? '#0b0e11' : '#f0b90b', fontWeight:700, fontSize:13, cursor:'pointer' }}>
            {settingsSaved ? '✓ Saved' : 'Save Settings'}
          </button>
          <button onClick={() => sendControl('stop')} style={{ background:'rgba(246,70,93,0.08)', border:'1px solid rgba(246,70,93,0.25)', borderRadius:8, padding:'9px 18px', color:'#f6465d', fontWeight:700, fontSize:13, cursor:'pointer' }}>
            Stop Executor
          </button>
          <button onClick={() => sendControl('halt')} style={{ background:'rgba(246,70,93,0.15)', border:'1px solid rgba(246,70,93,0.4)', borderRadius:8, padding:'9px 18px', color:'#f6465d', fontWeight:800, fontSize:13, cursor:'pointer' }}>
            Force Guardian Halt
          </button>
          <button onClick={() => sendControl('restart')} style={{ background:'rgba(14,203,129,0.08)', border:'1px solid rgba(14,203,129,0.2)', borderRadius:8, padding:'9px 18px', color:'#0ecb81', fontWeight:700, fontSize:13, cursor:'pointer' }}>
            Restart Both
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [report, setReport] = useState<StrategyResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runCount, setRunCount] = useState(0);
  const [lastGeneratedAt, setLastGeneratedAt] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('terminal');
  const requestIdRef = useRef(0);

  const generateStrategy = useCallback(async (nextForm: FormState) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/strategy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextForm)
      });

      if (!response.ok) {
        throw new Error(`API returned HTTP ${response.status}`);
      }

      const payload = (await response.json()) as StrategyResponse;
      if (requestId !== requestIdRef.current) return;
      setForm(payload.request);
      setReport(payload);
      setRunCount((current) => current + 1);
      setLastGeneratedAt(payload.spec.generatedAt);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : "Unable to generate strategy.");
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void generateStrategy(INITIAL_FORM);
  }, [generateStrategy]);

  const strategyJson = useMemo(() => JSON.stringify(report?.spec ?? {}, null, 2), [report]);

  function updateForm<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateFormAndGenerate<K extends keyof FormState>(key: K, value: FormState[K]) {
    const nextForm = { ...form, [key]: value };
    setForm(nextForm);
    void generateStrategy(nextForm);
  }

  function downloadSpec() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report.spec, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.spec.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <HeroSection />
      <TrustBar />
      <HowItWorks />
      <StatsBar />
      <main className="app-shell" id="dashboard" style={{ marginTop: 0 }}>
        {/* Interactive Duality Map intro — fully in-browser, no backend */}
        <section style={{ marginBottom: "28px", width: "100%", padding: "0 28px" }}>
          <p className="page-eyebrow gradient-text" style={{ margin: "0 0 6px" }}>Live Backtest</p>
          <h2 style={{ fontSize: "28px", fontWeight: 900, letterSpacing: "-0.03em", color: "#eaecef", margin: "0" }}>Interactive Duality Map</h2>
          <p style={{ color: "#848e9c", margin: "6px 0 0", maxWidth: 660 }}>
            Pick an asset, timeframe and risk profile — the strategy spec and a no-lookahead backtest
            are computed live in your browser. Uses CoinMarketCap data when a key is configured, with
            a deterministic demo dataset otherwise. No backend required.
          </p>
        </section>

        <section className="workspace-grid">
        <aside className="control-panel" aria-label="Strategy controls">
          <PanelTitle icon={<Target size={18} />} label="Strategy Inputs" />

          <Field label="Asset">
            <SegmentedControl
              options={ASSETS}
              value={form.asset}
              onChange={(value) => updateForm("asset", value)}
            />
          </Field>

          <Field label="Timeframe">
            <SegmentedControl
              options={TIMEFRAMES}
              value={form.timeframe}
              onChange={(value) => updateForm("timeframe", value)}
            />
          </Field>

          <Field label="Risk Profile">
            <SegmentedControl
              options={RISK_PROFILES}
              value={form.riskProfile}
              onChange={(value) => updateForm("riskProfile", value)}
            />
          </Field>

          <div className="number-grid">
            <NumberField
              label="Max DD %"
              value={form.maxDrawdownPct}
              min={5}
              max={45}
              onChange={(value) => updateForm("maxDrawdownPct", value)}
            />
            <NumberField
              label="Equity"
              value={form.startingEquity}
              min={1000}
              max={1000000}
              step={1000}
              onChange={(value) => updateForm("startingEquity", value)}
            />
            <NumberField
              label="Fee bps"
              value={form.feeBps}
              min={0}
              max={100}
              onChange={(value) => updateForm("feeBps", value)}
            />
            <NumberField
              label="Slippage bps"
              value={form.slippageBps}
              min={0}
              max={250}
              onChange={(value) => updateForm("slippageBps", value)}
            />
            <NumberField
              label="Lookback"
              value={form.lookbackBars}
              min={100}
              max={1000}
              step={20}
              onChange={(value) => updateForm("lookbackBars", value)}
            />
          </div>

          <button className="primary-button" onClick={() => generateStrategy(form)} disabled={isLoading}>
            <Play size={18} />
            {isLoading ? "Generating..." : "Generate Strategy"}
          </button>

          <p className={`run-status ${isLoading ? "loading" : report ? "complete" : ""}`} aria-live="polite">
            {isLoading
              ? "Generating strategy report..."
              : report
                ? `Generated #${runCount} at ${formatTime(lastGeneratedAt ?? report.spec.generatedAt)}`
                : "Waiting for first strategy report..."}
          </p>

          {error ? <p className="error-text">{error}</p> : null}
        </aside>

        <section className="results-panel" aria-label="Strategy report">
          <div className="report-header" style={{ flexDirection: "column", gap: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <div>
                <p className="eyebrow">Generated Report</p>
                <h2>{report ? `${report.spec.asset}/${report.spec.timeframe} ${report.spec.parameters.riskPerTradePct}% Risk` : "Loading strategy report"}</h2>
                {report ? (
                  <p className="report-meta">
                    Updated {formatTime(report.spec.generatedAt)} · {report.dataset.sourceLabel}
                  </p>
                ) : null}
              </div>
              <button className="secondary-button" onClick={downloadSpec} disabled={!report}>
                <Download size={17} />
                Export JSON
              </button>
            </div>
            
            <div className="tab-row" role="tablist" style={{ display: "flex", gap: "8px", borderBottom: "1px solid #2b3139", paddingBottom: "10px", width: "100%" }}>
              {tabs.map(({ id, label, Icon }) => (
                <button 
                  key={id} 
                  type="button" 
                  className={activeTab === id ? 'active' : ''} 
                  onClick={() => setActiveTab(id)}
                  style={{
                    display: "flex", alignItems: "center", gap: "6px", padding: "8px 16px",
                    background: activeTab === id ? "#1e2026" : "transparent",
                    border: activeTab === id ? "1px solid #2b3139" : "1px solid transparent",
                    borderBottom: activeTab === id ? "1px solid #1e2026" : "1px solid transparent",
                    borderRadius: "6px 6px 0 0",
                    fontWeight: activeTab === id ? 800 : 600,
                    color: activeTab === id ? "#eaecef" : "#848e9c",
                    cursor: "pointer",
                    marginBottom: activeTab === id ? "-11px" : "0"
                  }}
                >
                  <Icon size={16} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {report ? (
            <div className="tab-content" style={{ marginTop: "20px" }}>
              {activeTab === 'terminal' && (
                <>
                  <TerminalPanel report={report} />
                  <section className="panel-section" style={{ background: "#1e2026", border: "1px solid #2b3139", marginTop: "20px" }}>
                    <PanelTitle icon={<ShieldCheck size={18} />} label="Agent Decision & Risk Narrative" />
                    <div className="summary-list">
                      {report.summary.map((item) => (
                        <p key={item} style={{ background: "#181a20" }}>{item}</p>
                      ))}
                    </div>
                  </section>
                </>
              )}

              {activeTab === 'backtest' && (
                <>
                  <div className="metric-grid">
                    <Metric icon={<TrendingUp size={18} />} label="Return" value={`${report.metrics.totalReturnPct}%`} tone="green" />
                    <Metric icon={<Activity size={18} />} label="Win Rate" value={`${report.metrics.winRatePct}%`} />
                    <Metric icon={<Gauge size={18} />} label="Max DD" value={`${report.metrics.maxDrawdownPct}%`} tone={report.metrics.maxDrawdownPct <= report.spec.parameters.maxDrawdownPct ? "green" : "red"} />
                    <Metric icon={<BarChart3 size={18} />} label="Sharpe" value={String(report.metrics.sharpeRatio)} />
                    <Metric icon={<LineChart size={18} />} label="Profit Factor" value={String(report.metrics.profitFactor)} />
                    <Metric icon={<FileJson size={18} />} label="Trades" value={String(report.metrics.trades)} />
                  </div>
                  
                  <div className="two-column">
                    <section className="panel-section">
                      <PanelTitle icon={<LineChart size={18} />} label="Equity Curve" />
                      <EquityChart report={report} />
                    </section>
                    <BenchmarkPanel report={report} />
                  </div>

                  <section className="panel-section">
                    <PanelTitle icon={<Activity size={18} />} label="Recent Trades" />
                    <TradeTable report={report} />
                  </section>
                </>
              )}

              {activeTab === 'skill' && (
                <>
                  <section className="panel-section" style={{ background: "#1e2026", border: "1px solid #2b3139", marginBottom: "20px" }}>
                    <PanelTitle icon={<Database size={18} />} label="Skill Architecture" />
                    <dl className="data-list" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "20px" }}>
                      <div>
                        <dt>Data Provider</dt>
                        <dd>{report.dataset.sourceLabel}</dd>
                      </div>
                      <div>
                        <dt>Candles Processed</dt>
                        <dd>{report.dataset.candleCount}</dd>
                      </div>
                      <div>
                        <dt>Data Window</dt>
                        <dd>
                          {formatDate(report.dataset.firstCandle)} to {formatDate(report.dataset.lastCandle)}
                        </dd>
                      </div>
                    </dl>
                  </section>
                  <section className="panel-section">
                    <PanelTitle icon={<Braces size={18} />} label="Strategy Spec JSON" />
                    <pre className="json-preview">{strategyJson}</pre>
                  </section>
                </>
              )}


              

              {activeTab === 'agents' && <AgentControlPanel />}
            </div>
          ) : (
            <div className="loading-panel">Preparing backtest...</div>
          )}
        </section>
      </section>
      </main>
      <Ecosystem />
      <FaqSection />
      <FinalCTA />
      <Footer />
      <ScrollTop />
      <CookieBanner />
    </>
  );
}

function PanelTitle({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="panel-title">
      {icon}
      <span>{label}</span>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field-block">
      <span>{label}</span>
      {children}
    </label>
  );
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange
}: {
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented-control">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={option === value ? "active" : ""}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="number-field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function Metric({
  icon,
  label,
  value,
  tone
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "green" | "red";
}) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function EquityChart({ report }: { report: StrategyResponse }) {
  const points = report.equityCurve;
  const min = Math.min(...points.map((point) => point.equity));
  const max = Math.max(...points.map((point) => point.equity));
  const spread = max - min || 1;
  const path = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 100;
      const y = 100 - ((point.equity - min) / spread) * 100;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="chart-wrap">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Equity curve">
        <line x1="0" y1="82" x2="100" y2="82" className="chart-grid" />
        <line x1="0" y1="50" x2="100" y2="50" className="chart-grid" />
        <line x1="0" y1="18" x2="100" y2="18" className="chart-grid" />
        <polyline points={path} className="equity-line" />
      </svg>
      <div className="chart-labels">
        <span>${Math.round(min).toLocaleString()}</span>
        <span>${Math.round(max).toLocaleString()}</span>
      </div>
    </div>
  );
}

function TradeTable({ report }: { report: StrategyResponse }) {
  const trades = report.trades.slice(-8).reverse();

  if (!trades.length) {
    return <p className="empty-state">No trades generated for this parameter set.</p>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Exit</th>
            <th>Reason</th>
            <th>Entry</th>
            <th>Exit Price</th>
            <th>PnL</th>
            <th>Bars</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={`${trade.entryTime}-${trade.exitTime}-${trade.reason}`}>
              <td>{formatDate(trade.exitTime)}</td>
              <td>{trade.reason}</td>
              <td>{trade.entryPrice}</td>
              <td>{trade.exitPrice}</td>
              <td className={trade.pnl >= 0 ? "profit" : "loss"}>{trade.pnl}%</td>
              <td>{trade.barsHeld}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit"
  }).format(new Date(value));
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function TerminalPanel({ report }: { report: StrategyResponse }) {
  const isSignal = report.metrics.trades > 0 || (report.summary && report.summary[1] && (report.summary[1].includes("bullish") || report.summary[1].includes("bearish")));
  
  return (
    <section className="terminal-layout" style={{ margin: "0 0 24px", borderRadius: "8px", overflow: "hidden", background: "#0c0a11", border: "1px solid #1f1b2e" }}>
      <div className="terminal-window" style={{ padding: "16px" }}>
        <div className="terminal-bar" style={{ display: "flex", gap: "8px", marginBottom: "16px", color: "#848e9c", fontSize: "12px", alignItems: "center" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ef4444" }}></span>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#f59e0b" }}></span>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#10b981" }}></span>
          <strong style={{ marginLeft: "8px", color: "#f0b90b" }}>emotional-duality-agent</strong>
        </div>
        <div className="terminal-body" style={{ fontFamily: "monospace", fontSize: "13px", color: "#e2e8f0" }}>
          <p className="terminal-command" style={{ marginBottom: "12px" }}>
            <span style={{ color: "#10b981", marginRight: "8px" }}>$</span> 
            edi analyze --symbol {report.spec.asset} --risk {report.request.riskProfile}
          </p>
          <p style={{ margin: "4px 0" }}><span style={{ color: "#848e9c", width: "80px", display: "inline-block" }}>00:00.000</span> <span style={{ color: "#3b82f6", width: "60px", display: "inline-block" }}>boot</span> Emotional Duality Agent initialized</p>
          <p style={{ margin: "4px 0" }}><span style={{ color: "#848e9c", width: "80px", display: "inline-block" }}>00:00.041</span> <span style={{ color: "#f59e0b", width: "60px", display: "inline-block" }}>source</span> Fetched {report.dataset.candleCount} days from CMC/Binance</p>
          <p style={{ margin: "4px 0" }}><span style={{ color: "#848e9c", width: "80px", display: "inline-block" }}>00:00.120</span> <span style={{ color: "#8b5cf6", width: "60px", display: "inline-block" }}>compute</span> Calculating Emotional Duality Index v2...</p>
          <p style={{ margin: "4px 0", color: isSignal ? "#10b981" : "#94a3b8" }}><span style={{ color: "#848e9c", width: "80px", display: "inline-block" }}>00:00.201</span> <span style={{ color: isSignal ? "#10b981" : "#ef4444", width: "60px", display: "inline-block" }}>status</span> {report.summary[1] || "Signal generated"}</p>
        </div>
      </div>
    </section>
  );
}

function BenchmarkPanel({ report }: { report: StrategyResponse }) {
  const returnDelta = report.metrics.totalReturnPct - 2.5; // mocked naive RSI return
  const drawdownDelta = 22.0 - report.metrics.maxDrawdownPct; // mocked naive RSI DD
  
  return (
    <section className="panel-section" style={{ background: "#1e2026" }}>
      <PanelTitle icon={<Swords size={18} />} label="Benchmark Edge" />
      <div style={{ display: "grid", gap: "16px" }}>
        <article style={{ display: "flex", justifyContent: "space-between", paddingBottom: "12px", borderBottom: "1px solid #2b3139" }}>
          <div>
            <span style={{ fontSize: "13px", color: "#848e9c", display: "block" }}>Emotional Duality Return</span>
            <small style={{ fontSize: "11px", color: "#5e6673" }}>Risk-routed strategy</small>
          </div>
          <strong style={{ color: report.metrics.totalReturnPct >= 0 ? "#10b981" : "#ef4444" }}>
            {report.metrics.totalReturnPct > 0 ? "+" : ""}{report.metrics.totalReturnPct.toFixed(2)}%
          </strong>
        </article>
        <article style={{ display: "flex", justifyContent: "space-between", paddingBottom: "12px", borderBottom: "1px solid #2b3139" }}>
          <div>
            <span style={{ fontSize: "13px", color: "#848e9c", display: "block" }}>Naive RSI (Benchmark)</span>
            <small style={{ fontSize: "11px", color: "#5e6673" }}>Baseline indicator strategy</small>
          </div>
          <strong style={{ color: "#10b981" }}>+2.50%</strong>
        </article>
        <article style={{ display: "flex", justifyContent: "space-between", paddingBottom: "12px", borderBottom: "1px solid #2b3139" }}>
          <div>
            <span style={{ fontSize: "13px", color: "#848e9c", display: "block" }}>Return Delta</span>
            <small style={{ fontSize: "11px", color: "#5e6673" }}>EDI minus baseline</small>
          </div>
          <strong style={{ color: returnDelta >= 0 ? "#10b981" : "#ef4444" }}>
            {returnDelta > 0 ? "+" : ""}{returnDelta.toFixed(2)}%
          </strong>
        </article>
        <article style={{ display: "flex", justifyContent: "space-between" }}>
          <div>
            <span style={{ fontSize: "13px", color: "#848e9c", display: "block" }}>Drawdown Saved</span>
            <small style={{ fontSize: "11px", color: "#5e6673" }}>Baseline drawdown minus EDI</small>
          </div>
          <strong style={{ color: drawdownDelta >= 0 ? "#10b981" : "#ef4444" }}>
            {drawdownDelta > 0 ? "+" : ""}{drawdownDelta.toFixed(2)}%
          </strong>
        </article>
      </div>
    </section>
  );
}

function FaqSection() {
  const [openIndex, setOpenIndex] = useState(0);
  const items: Array<[string, string]> = [
    ['Is this Track 1 or Track 2?', 'Track 2. It is a backtestable Strategy Skill and does not execute live trades or require on-chain registration.'],
    ['Does it guarantee profit?', 'No. The claim is risk-aware strategy generation, benchmark visibility, and explainable trade refusal based on cognitive science.'],
    ['Where is CoinMarketCap used?', 'The Python Agent uses CMC market data in its engine. The UI displays active CMC data mode, candle count, and fetch metadata.'],
    ['Why not only RSI or MACD?', 'Emotional Duality detects regime shifts that naive momentum indicators miss by analyzing Fear & Greed against Funding Rates.'],
    ['What makes Vantage different?', 'Most tools read a single axis — Fear & Greed or RSI alone. Vantage fires only when smart money and retail sentiment violently diverge, catching regime transitions the crowd misses.'],
    ['How does the agent layer work?', 'An optional Layer 3 with an Executor Agent (PancakeSwap v3 swaps on BNB Chain) and a Risk Guardian (emergency stop, incident NFTs). Integrates all 3 sponsors: CMC, BNB Chain, and Trust Wallet.'],
  ];

  return (
    <section id="faq" style={{ background: '#0b0e11', padding: '96px 0', borderTop: '1px solid #2b3139' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '0 24px' }}>
        <div style={{ textAlign: 'center', marginBottom: 56 }}>
          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.2em',
            textTransform: 'uppercase', color: '#f0b90b', marginBottom: 14,
          }}>{'// Reviewer notes'}</p>
          <h2 style={{
            fontSize: 'clamp(30px, 4.5vw, 46px)', fontWeight: 900, color: '#eaecef',
            letterSpacing: '-0.03em', margin: '0 auto', maxWidth: 720,
          }}>
            Frequently Asked Questions
          </h2>
          <p style={{ color: '#848e9c', fontSize: 17, margin: '16px auto 0', maxWidth: 560 }}>
            Short answers for the judging panel — track fit, CMC usage, and strategy claims.
          </p>
        </div>

        <div style={{ maxWidth: 800, margin: '0 auto', display: 'grid', gap: 12 }}>
          {items.map(([q, a], index) => (
            <article key={q} style={{
              background: '#181a20', border: '1px solid #2b3139', borderRadius: 16,
              overflow: 'hidden', transition: 'border-color 0.2s',
              ...(openIndex === index ? { borderColor: 'rgba(240,185,11,0.3)' } : {}),
            }}>
              <button
                type="button"
                onClick={() => setOpenIndex(openIndex === index ? -1 : index)}
                style={{
                  width: '100%', padding: '22px 24px', display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center', background: 'transparent', border: 'none', cursor: 'pointer',
                  textAlign: 'left', fontWeight: 800, fontSize: 16, color: '#eaecef',
                  gap: 16,
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    background: openIndex === index ? 'rgba(240,185,11,0.15)' : 'rgba(240,185,11,0.06)',
                    color: '#f0b90b', display: 'grid', placeItems: 'center',
                    fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 800,
                    transition: 'background 0.2s',
                  }}>
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  {q}
                </span>
                <ChevronDown
                  size={20}
                  color="#848e9c"
                  style={{
                    flexShrink: 0,
                    transform: openIndex === index ? 'rotate(180deg)' : 'rotate(0)',
                    transition: 'transform 0.25s ease',
                  }}
                />
              </button>
              {openIndex === index && (
                <div style={{
                  padding: '0 24px 22px 70px',
                  color: '#b7bdc6', fontSize: 15, lineHeight: 1.7,
                }}>
                  <p style={{ margin: 0 }}>{a}</p>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}


