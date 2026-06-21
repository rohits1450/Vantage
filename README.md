# Vantage — AI Agent Skill

A CoinMarketCap AI Agent Skill that detects crypto market regime transitions using three signal layers — **derivatives positioning**, **on-chain flow**, and **market sentiment** — and outputs fully backtestable trading strategy specifications.

[![CMC MCP](https://img.shields.io/badge/CMC-MCP%20Powered-blue)](https://mcp.coinmarketcap.com)
[![Next.js](https://img.shields.io/badge/Next.js-15.0-black)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org/)
[![BNB Chain](https://img.shields.io/badge/BNB%20Chain-Testnet-F0B90B)](https://www.bnbchain.org/)

---


## 🧠 What It Does (Emotional Duality)

Most tools read a single axis like RSI or Fear & Greed. Vantage looks for **Emotional Duality** — when smart money and retail sentiment violently diverge.

It uses a 6-signal weighted scoring matrix:
1. **Leverage Sentiment** (Funding rates, OI) — 25%
2. **Smart Money** (Whale %, exchange net flow) — 25%
3. **Technical Bias** (RSI, MACD, EMA50) — 20%
4. **Narrative Heat** (Trending sectors) — 10%
5. **Fear & Greed** — 10%
6. **News Sentiment** — 10%

**Divergence Detection:** If retail is extremely greedy (high funding) but whales are distributing, it triggers a **TOPPING_SIGNAL**. If retail is panicked (negative funding) but whales are accumulating, it triggers a **BOTTOMING_SIGNAL**.

---

## 🏗 System Architecture (3 Layers)

Vantage is built in 3 independent layers to prove out the full agentic lifecycle:

### Layer 1: Strategy Engine (The CMC Skill)
Located in `vantage-backend/`. Connects to CoinMarketCap via the MCP protocol. Processes the 6-signal matrix and generates the backtestable JSON strategy specification.

### Layer 2: Interactive Dashboard
Located in `frontend/`. A Next.js application that provides:
- Live strategy generation UI
- In-browser backtest engine (no lookahead bias)
- Interactive equity curves and trade tables
- Agent Control panel

### Layer 3: Agent Layer (Bonus Integration)
Located in `agents/`. A Python-based autonomous trading system that actually executes the strategies on-chain.
- **Orchestrator:** Connects to the frontend via WebSockets.
- **Executor Agent:** Processes signals, runs a 5-step safety check (gas, slippage, wallet balance), and executes swaps on PancakeSwap v3 (BSC Testnet).
- **Risk Guardian:** Runs 24/7. Tracks mark-to-market equity. If drawdown >20%, it hits an emergency stop, revokes ERC-20 approvals, moves funds to cold storage, and mints an **Incident Report NFT (ERC-8004)**.

---

## 📂 Project Structure

```text
Vantage/
├── README.md               # This file
├── frontend/               # Layer 2: Next.js Dashboard & Backtest Engine
│   ├── src/app/            # UI components and pages
│   ├── src/lib/            # Backtest logic and API routes
│   └── package.json
├── vantage-backend/        # Layer 1: Strategy Engine & CMC MCP
│   ├── src/index.ts        # Entry point
│   ├── src/mcp-client.ts   # CMC MCP connection + 8 tool wrappers
│   ├── src/regime-engine.ts# Scoring matrix + divergence logic
│   └── src/strategy-spec.ts# Spec generator
└── agents/                 # Layer 3: Python Agent Layer
    ├── orchestrator.py     # WS/HTTP server & signal queue
    ├── executor.py         # PancakeSwap execution agent
    ├── guardian.py         # Risk monitor & emergency stop
    ├── state_db.py         # Shared SQLite state
    └── requirements.txt
```

---

## 🚀 Quick Start

### 1. Start the Frontend (Dashboard)
```bash
cd frontend
npm install
npm run dev
# Running at http://localhost:3000
```

### 2. Start the Agent Orchestrator (Optional)
```bash
cd agents
# Setup python virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Start the orchestrator (runs on WS:8765, HTTP:8766)
python orchestrator.py
```
---

## 📋 Strategy Output Schema

Every generated strategy spec includes:
- **Strategy Metadata:** Name, timestamp, asset, timeframe, regime, conviction score
- **Entry Rules:** Exact primary trigger + confirmation conditions + price zone
- **Exit Rules:** TP1, TP2, stop loss, trailing stop, time stop
- **Position Sizing:** Base allocation, conviction multiplier, final %, max risk
- **Invalidation:** Specific conditions that nullify the strategy
- **Backtest Parameters:** Lookback, frequency, benchmark, slippage, costs
- **Signal Breakdown:** Complete table of all 6 signals with raw values and scores

---

## ⚖️ License

MIT License
