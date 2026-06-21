"""
executor.py — Vantage EDI Execution Agent.

Listens for trading signals from the orchestrator, performs safety checks,
and executes real PancakeSwap v3 swaps (or simulated swaps in DEMO_MODE).

IPC with the Risk Guardian is via SHARED SQLITE DB — no HTTP polling.
The executor checks guardian_state.is_halted / halted_at directly from DB
before every trade.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiosqlite

import config
import state_db
from chain import (
    get_bnb_balance,
    get_token_allowance,
    approve_token,
    revoke_all_approvals,
)
from gas_optimizer import is_gas_acceptable, get_gas_price_gwei
from nonce_manager import sync_nonce
from pancakeswap import simulate_swap, execute_swap

# ─── Signal dataclass ─────────────────────────────────────────────────────────

@dataclass
class AgentSignal:
    signal_id: str
    asset: str
    direction: str           # "LONG" | "CLOSE"
    conviction: int          # 1-10
    regime: str
    risk_pct: float          # % of portfolio per trade
    slippage_bps: int
    generated_at: str        # ISO timestamp
    portfolio_size_usd: float = 10000.0
    divergence_type: str = ""


# ─── Execution Agent ─────────────────────────────────────────────────────────

class ExecutorAgent:
    def __init__(self, broadcast_fn=None) -> None:
        """
        broadcast_fn: coroutine callable that sends a dict to all WS clients.
        Injected by the orchestrator.
        """
        self._broadcast = broadcast_fn or (lambda msg: asyncio.sleep(0))
        self._signal_queue: asyncio.Queue[AgentSignal] = asyncio.Queue()
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start all agent loops."""
        print("[executor] Starting Vantage EDI Execution Agent...")

        # Sync nonce from chain
        if not config.DEMO_MODE:
            try:
                sync_nonce(config.EXECUTOR_WALLET_ADDRESS)
            except Exception as e:
                print(f"[executor] Warning: could not sync nonce: {e}")

        # Pre-flight token approval check
        await self.pre_flight_setup()

        self._running = True
        print(f"[executor] Ready. DEMO_MODE={'ON' if config.DEMO_MODE else 'OFF'}")

        if config.DEMO_MODE:
            print("[executor] ⚠️  DEMO MODE ACTIVE — no real transactions will be submitted.")

        await self._broadcast({
            "type": "AGENT_STATUS",
            "agent": "executor",
            "status": "RUNNING",
            "demo_mode": config.DEMO_MODE,
            "wallet": config.EXECUTOR_WALLET_ADDRESS,
        })

        # Run signal processor
        await self.signal_processor()

    async def pre_flight_setup(self) -> None:
        """
        Check and set token allowances for all tradeable assets on startup.
        Skipped in DEMO_MODE.
        """
        if config.DEMO_MODE:
            print("[executor] pre_flight_setup: skipped (DEMO_MODE)")
            return

        print("[executor] pre_flight_setup: checking token allowances...")
        tokens_to_approve = [
            (config.USDT_ADDRESS, "USDT"),
            (config.WBNB_ADDRESS, "WBNB"),
        ]
        spender = config.PANCAKESWAP_UNIVERSAL_ROUTER

        for token_addr, symbol in tokens_to_approve:
            try:
                allowance = get_token_allowance(
                    token_addr, config.EXECUTOR_WALLET_ADDRESS, spender
                )
                if allowance < (2**128):  # Less than half of max_uint256
                    print(f"[executor] Approving {symbol} for PancakeSwap router...")
                    tx = approve_token(
                        token_addr, spender,
                        2**256 - 1,  # max_uint256 for testnet
                        config.EXECUTOR_PRIVATE_KEY,
                    )
                    print(f"[executor] {symbol} approved: {config.BSCSCAN_BASE_URL}/tx/{tx}")
                    await asyncio.sleep(3)  # Wait for confirmation
                else:
                    print(f"[executor] {symbol} allowance OK.")
            except Exception as e:
                print(f"[executor] Warning: could not check/set allowance for {symbol}: {e}")

    async def enqueue_signal(self, signal: AgentSignal) -> None:
        """Called by the orchestrator when a new signal arrives."""
        await self._signal_queue.put(signal)

    async def signal_processor(self) -> None:
        """Main loop: process one signal at a time from the queue."""
        while not self._shutdown_event.is_set():
            try:
                signal = await asyncio.wait_for(
                    self._signal_queue.get(), timeout=1.0
                )
                await self._process_signal(signal)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[executor] Error in signal_processor: {e}")

    async def _process_signal(self, signal: AgentSignal) -> None:
        """Full signal processing pipeline with all safety checks."""
        print(f"\n[executor] Processing signal: {signal.signal_id} ({signal.asset} {signal.direction})")

        # ── CHECK 1: Signal staleness ─────────────────────────────────────
        try:
            generated = datetime.fromisoformat(signal.generated_at.replace("Z", "+00:00"))
            age_sec = (datetime.now(timezone.utc) - generated).total_seconds()
            if age_sec > config.CMC_DATA_STALENESS_MAX_SEC:
                await self._reject(signal, f"STALE_SIGNAL ({age_sec:.0f}s old)")
                return
        except Exception:
            pass  # If parsing fails, continue

        # ── CHECK 2: Guardian halt state from DB ──────────────────────────
        guardian = await state_db.get_guardian_state()
        if guardian.get("is_halted"):
            await self._reject(signal, f"TRADING_HALTED: {guardian.get('halt_reason', 'unknown')}")
            return

        # Check if guardian state is stale (guardian may be dead)
        if guardian.get("halted_at"):
            try:
                halted_at = datetime.fromisoformat(
                    guardian["halted_at"].replace("Z", "+00:00")
                )
                stale_sec = (datetime.now(timezone.utc) - halted_at).total_seconds()
                if stale_sec > 120:
                    await self._reject(signal, "GUARDIAN_STATE_STALE — self-pausing")
                    return
            except Exception:
                pass

        # Check last_check_at for guardian heartbeat
        if guardian.get("last_check_at"):
            try:
                last_check = datetime.fromisoformat(
                    guardian["last_check_at"].replace("Z", "+00:00")
                )
                guardian_age = (datetime.now(timezone.utc) - last_check).total_seconds()
                if guardian_age > config.GUARDIAN_HEARTBEAT_TIMEOUT_SEC:
                    await self._reject(signal, f"GUARDIAN_OFFLINE ({guardian_age:.0f}s since last check)")
                    await self._broadcast({"type": "GUARDIAN_OFFLINE", "last_seen": guardian.get("last_check_at")})
                    return
            except Exception:
                pass

        # ── DEMO MODE fast path ───────────────────────────────────────────
        if config.DEMO_MODE:
            await self._execute_demo(signal)
            return

        # ── CHECK 3: Gas price ────────────────────────────────────────────
        if not is_gas_acceptable():
            gwei = get_gas_price_gwei()
            await self._reject(signal, f"GAS_TOO_HIGH ({gwei:.2f} Gwei)")
            await self._broadcast({"type": "GAS_SPIKE", "current_gwei": gwei, "max_gwei": config.MAX_GAS_GWEI})
            return

        # ── CHECK 4: Wallet gas reserve ───────────────────────────────────
        bnb_balance = get_bnb_balance(config.EXECUTOR_WALLET_ADDRESS)
        if bnb_balance < config.MIN_GAS_RESERVE_BNB:
            await self._reject(signal, f"INSUFFICIENT_GAS ({bnb_balance:.6f} BNB)")
            return

        # ── CHECK 5: Slippage simulation ──────────────────────────────────
        trade_amount_wei = int(config.MAX_TRADE_SIZE_BNB * 1e18)
        sim = simulate_swap(
            config.WBNB_ADDRESS,
            config.USDT_ADDRESS,
            trade_amount_wei,
        )
        if not sim.ok or sim.price_impact_bps > config.SLIPPAGE_TOLERANCE_BPS:
            await self._reject(
                signal, f"SLIPPAGE_EXCEEDED ({sim.price_impact_bps} bps > {config.SLIPPAGE_TOLERANCE_BPS})"
            )
            return

        # ── EXECUTE REAL SWAP ─────────────────────────────────────────────
        await self._execute_real(signal, sim.min_amount_out_wei)

    async def _execute_demo(self, signal: AgentSignal) -> None:
        """DEMO_MODE: generate realistic fake tx, broadcast instantly."""
        fake_tx = "0x" + secrets.token_hex(32)
        print(f"[executor] DEMO trade submitted: {fake_tx}")

        await state_db.insert_trade(
            signal_id=signal.signal_id,
            asset=signal.asset,
            direction=signal.direction,
            amount_bnb=config.MAX_TRADE_SIZE_BNB,
            entry_price=0.0,
            tx_hash=fake_tx,
            regime=signal.regime,
            conviction=signal.conviction,
            demo=True,
        )
        await self._broadcast({
            "type": "TRADE_SUBMITTED",
            "signal_id": signal.signal_id,
            "tx_hash": fake_tx,
            "asset": signal.asset,
            "direction": signal.direction,
            "amount_bnb": config.MAX_TRADE_SIZE_BNB,
            "demo": True,
        })

        # Simulate 2s block time
        await asyncio.sleep(2)

        # Fake PnL: random small gain/loss for realism
        import random
        pnl = round(random.uniform(-1.5, 3.5), 2)
        exit_price = 0.0
        status = "DEMO"

        await state_db.confirm_trade(signal.signal_id, status, exit_price, pnl)
        await self._broadcast({
            "type": "TRADE_CONFIRMED",
            "signal_id": signal.signal_id,
            "tx_hash": fake_tx,
            "pnl_pct": pnl,
            "status": status,
            "demo": True,
            "bscscan_url": f"{config.BSCSCAN_BASE_URL}/tx/{fake_tx}",
        })
        print(f"[executor] DEMO trade confirmed. PnL: {pnl:+.2f}%")

    async def _execute_real(self, signal: AgentSignal, min_amount_out_wei: int) -> None:
        """Real on-chain swap execution."""
        trade_amount_wei = int(config.MAX_TRADE_SIZE_BNB * 1e18)
        try:
            tx_hash = execute_swap(
                token_in=config.WBNB_ADDRESS,
                token_out=config.USDT_ADDRESS,
                amount_in_wei=trade_amount_wei,
                min_amount_out_wei=min_amount_out_wei,
                recipient=config.EXECUTOR_WALLET_ADDRESS,
                private_key=config.EXECUTOR_PRIVATE_KEY,
            )
        except Exception as e:
            await self._reject(signal, f"SWAP_FAILED: {e}")
            return

        await state_db.insert_trade(
            signal_id=signal.signal_id,
            asset=signal.asset,
            direction=signal.direction,
            amount_bnb=config.MAX_TRADE_SIZE_BNB,
            entry_price=0.0,
            tx_hash=tx_hash,
            regime=signal.regime,
            conviction=signal.conviction,
            demo=False,
        )
        await self._broadcast({
            "type": "TRADE_SUBMITTED",
            "signal_id": signal.signal_id,
            "tx_hash": tx_hash,
            "asset": signal.asset,
            "direction": signal.direction,
            "demo": False,
            "bscscan_url": f"{config.BSCSCAN_BASE_URL}/tx/{tx_hash}",
        })

        print(f"[executor] Real swap submitted: {tx_hash}")
        print("[executor] Waiting for confirmation...")

        try:
            from chain import wait_for_tx
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, wait_for_tx, tx_hash, 120
            )
            status = "CONFIRMED" if receipt["status"] == 1 else "FAILED"
        except Exception:
            status = "FAILED"

        await state_db.confirm_trade(signal.signal_id, status)
        await self._broadcast({
            "type": "TRADE_CONFIRMED",
            "signal_id": signal.signal_id,
            "tx_hash": tx_hash,
            "status": status,
            "demo": False,
        })
        print(f"[executor] Trade {status}: {config.BSCSCAN_BASE_URL}/tx/{tx_hash}")

    async def _reject(self, signal: AgentSignal, reason: str) -> None:
        print(f"[executor] ❌ Signal rejected: {reason}")
        await self._broadcast({
            "type": "TRADE_FAILED",
            "signal_id": signal.signal_id,
            "reason": reason,
        })

    async def stop(self) -> None:
        """Graceful shutdown — finish any in-flight trade before stopping."""
        print("[executor] Shutting down...")
        self._running = False
        self._shutdown_event.set()
        await self._broadcast({"type": "AGENT_STATUS", "agent": "executor", "status": "STOPPED"})
