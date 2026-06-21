"""
guardian.py — Vantage EDI Risk Guardian Agent.

Monitors the executor wallet every 30 seconds using MARK-TO-MARKET equity
(BNB balance + open position values at current Binance prices).
Writes halt state to the shared SQLite DB as the single source of truth.
Triggers emergency stop if drawdown > 20% or consecutive losses >= 5.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import aiohttp
from web3 import Web3

import config
import state_db
from chain import get_bnb_balance, revoke_all_approvals, transfer_bnb

# Tokens monitored for revocation during emergency
MONITORED_TOKENS = [config.WBNB_ADDRESS, config.USDT_ADDRESS]
MONITORED_SPENDERS = [config.PANCAKESWAP_UNIVERSAL_ROUTER, config.PERMIT2_ADDRESS]


async def get_live_price_usd(symbol: str) -> float:
    """
    Fetch live price from Binance public REST API (no auth required).
    Falls back to 0.0 on error, which will make the guardian conservative.
    """
    symbol_map = {
        "BNB": "BNBUSDT",
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "USDT": None,  # USDT is always 1.0
    }
    pair = symbol_map.get(symbol.upper())
    if pair is None:
        return 1.0  # USDT

    url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["price"])
    except Exception as e:
        print(f"[guardian] Price fetch failed for {symbol}: {e}")
    return 0.0


async def calculate_mark_to_market_equity(bnb_price_usd: float) -> float:
    """
    True equity = BNB balance (in USD) + sum(position_value in USD).
    This prevents false emergency stops when BNB is swapped to USDT.
    """
    bnb_balance = get_bnb_balance(config.EXECUTOR_WALLET_ADDRESS)
    bnb_value_usd = bnb_balance * bnb_price_usd

    positions = await state_db.get_all_positions()
    position_value_usd = 0.0
    for pos in positions:
        live_price = await get_live_price_usd(pos["asset"])
        position_value_usd += pos["amount"] * live_price

    total_usd = bnb_value_usd + position_value_usd
    return total_usd


class GuardianAgent:
    def __init__(self, broadcast_fn=None) -> None:
        self._broadcast = broadcast_fn or (lambda msg: asyncio.sleep(0))
        self._shutdown_event = asyncio.Event()
        self._emergency_triggered = False

    async def start(self) -> None:
        print("[guardian] Starting Vantage EDI Risk Guardian...")
        await self._broadcast({
            "type": "AGENT_STATUS",
            "agent": "guardian",
            "status": "RUNNING",
            "wallet": config.GUARDIAN_WALLET_ADDRESS,
        })
        await self.monitor_loop()

    async def monitor_loop(self) -> None:
        """Main monitoring loop — runs every GUARDIAN_POLL_INTERVAL_SEC seconds."""
        while not self._shutdown_event.is_set():
            try:
                await self._check_and_update()
            except Exception as e:
                print(f"[guardian] Monitor loop error: {e}")

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=config.GUARDIAN_POLL_INTERVAL_SEC,
                )
            except asyncio.TimeoutError:
                pass  # Normal — continue loop

    async def _check_and_update(self) -> None:
        """Single monitoring cycle: fetch state, calculate equity, check thresholds."""
        now = datetime.now(timezone.utc).isoformat()

        # Fetch live BNB price
        bnb_price = await get_live_price_usd("BNB")
        if bnb_price == 0.0:
            print("[guardian] Warning: could not fetch BNB price — skipping cycle")
            return

        # Calculate mark-to-market equity in USD
        current_equity_usd = await calculate_mark_to_market_equity(bnb_price)
        # Normalise to BNB-equivalent for simpler comparison
        current_equity_bnb = current_equity_usd / bnb_price if bnb_price > 0 else 0.0

        # Load previous state
        state = await state_db.get_guardian_state()
        peak_equity_bnb = max(
            state.get("peak_equity_bnb") or current_equity_bnb,
            current_equity_bnb,
        )

        drawdown_pct = 0.0
        if peak_equity_bnb > 0:
            drawdown_pct = (peak_equity_bnb - current_equity_bnb) / peak_equity_bnb * 100

        consecutive_losses = await state_db.count_consecutive_losses()

        await state_db.update_guardian_state(
            current_equity_bnb=current_equity_bnb,
            peak_equity_bnb=peak_equity_bnb,
            drawdown_pct=drawdown_pct,
            consecutive_losses=consecutive_losses,
        )

        print(
            f"[guardian] Equity: {current_equity_bnb:.4f} BNB | "
            f"Peak: {peak_equity_bnb:.4f} BNB | "
            f"DD: {drawdown_pct:.1f}% | "
            f"Losses: {consecutive_losses}"
        )

        await self._broadcast({
            "type": "GUARDIAN_UPDATE",
            "drawdown_pct": round(drawdown_pct, 2),
            "consecutive_losses": consecutive_losses,
            "current_equity_bnb": round(current_equity_bnb, 6),
            "peak_equity_bnb": round(peak_equity_bnb, 6),
            "last_check_at": now,
        })

        # ── Threshold checks ──────────────────────────────────────────────
        if not self._emergency_triggered:
            if drawdown_pct >= config.GUARDIAN_MAX_DRAWDOWN_PCT:
                await self.trigger_emergency_stop(
                    f"DRAWDOWN_BREACH",
                    drawdown_pct,
                    consecutive_losses,
                )
            elif consecutive_losses >= config.GUARDIAN_MAX_CONSECUTIVE_LOSSES:
                await self.trigger_emergency_stop(
                    f"CONSECUTIVE_LOSSES",
                    drawdown_pct,
                    consecutive_losses,
                )

    async def trigger_emergency_stop(
        self,
        reason: str,
        drawdown_pct: float,
        consecutive_losses: int,
    ) -> None:
        """
        Full emergency stop sequence:
        1. Set halt flag in DB (executor reads this before every trade)
        2. Revoke all token approvals
        3. Transfer remaining BNB to cold wallet
        4. Mint incident NFT
        5. Broadcast to frontend
        """
        if self._emergency_triggered:
            return  # Prevent double-triggering
        self._emergency_triggered = True

        print(f"\n[guardian] 🚨 EMERGENCY STOP: {reason}")

        # 1. Set halt flag atomically in DB
        await state_db.set_halted(True, reason)
        await self._broadcast({
            "type": "HALT",
            "reason": reason,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "drawdown_pct": drawdown_pct,
            "consecutive_losses": consecutive_losses,
        })

        actions: list[str] = []

        # 2. Revoke all token approvals (uses guardian wallet to call executor wallet's approvals)
        revoke_txs: list[str] = []
        if not config.DEMO_MODE and config.EXECUTOR_PRIVATE_KEY:
            try:
                revoke_txs = await asyncio.get_event_loop().run_in_executor(
                    None,
                    revoke_all_approvals,
                    MONITORED_TOKENS,
                    MONITORED_SPENDERS,
                    config.EXECUTOR_PRIVATE_KEY,
                )
                actions.extend([f"revoke:{tx}" for tx in revoke_txs])
                print(f"[guardian] Revoked {len(revoke_txs)} approvals.")
            except Exception as e:
                print(f"[guardian] Warning: approval revocation failed: {e}")
        else:
            revoke_txs = ["DEMO_REVOKE_1", "DEMO_REVOKE_2"]
            actions.append("demo_revoke_approvals")
            print("[guardian] DEMO: Simulated approval revocation.")

        # 3. Transfer remaining BNB to cold wallet
        transfer_tx = "DEMO_TRANSFER"
        equity_transferred = 0.0
        if config.COLD_WALLET_ADDRESS and config.COLD_WALLET_ADDRESS != "0xYOUR_COLD_WALLET_HERE":
            try:
                balance = get_bnb_balance(config.EXECUTOR_WALLET_ADDRESS)
                gas_reserve = 0.005
                transfer_amount = max(0.0, balance - gas_reserve)

                if transfer_amount > 0 and not config.DEMO_MODE:
                    transfer_tx = await asyncio.get_event_loop().run_in_executor(
                        None,
                        transfer_bnb,
                        config.COLD_WALLET_ADDRESS,
                        transfer_amount,
                        config.EXECUTOR_PRIVATE_KEY,
                    )
                    equity_transferred = transfer_amount
                    actions.append(f"transfer:{transfer_tx}")
                    print(f"[guardian] Transferred {transfer_amount:.6f} BNB to cold wallet.")
                else:
                    equity_transferred = transfer_amount
                    actions.append("demo_emergency_transfer")
                    print(f"[guardian] DEMO: Would transfer {transfer_amount:.6f} BNB.")
            except Exception as e:
                print(f"[guardian] Warning: emergency transfer failed: {e}")
        else:
            print("[guardian] Warning: COLD_WALLET_ADDRESS not configured — skipping transfer.")

        # 4. Mint incident NFT
        incident_tx = "DEMO_INCIDENT_NFT"
        try:
            from incident_nft import mint_incident_nft
            token_id = config.GUARDIAN_AGENT_TOKEN_ID or 0
            incident_tx = await asyncio.get_event_loop().run_in_executor(
                None,
                mint_incident_nft,
                reason,
                drawdown_pct,
                consecutive_losses,
                revoke_txs,
                transfer_tx,
                equity_transferred,
                config.GUARDIAN_PRIVATE_KEY,
                token_id,
            )
            actions.append(f"incident_nft:{incident_tx}")
        except Exception as e:
            print(f"[guardian] Warning: incident NFT minting failed: {e}")

        # 5. Save to DB
        await state_db.save_incident(
            trigger=reason,
            drawdown_pct=drawdown_pct,
            consecutive_losses=consecutive_losses,
            actions_taken=actions,
            incident_nft_tx=incident_tx,
            equity_recovered_bnb=equity_transferred,
        )

        # 6. Broadcast full incident report to frontend
        await self._broadcast({
            "type": "INCIDENT_REPORT",
            "reason": reason,
            "drawdown_pct": drawdown_pct,
            "consecutive_losses": consecutive_losses,
            "revoke_txs": revoke_txs,
            "transfer_tx": transfer_tx,
            "incident_nft_tx": incident_tx,
            "equity_recovered_bnb": equity_transferred,
            "bscscan_nft_url": f"{config.BSCSCAN_BASE_URL}/tx/{incident_tx}",
        })
        print("[guardian] ✅ Emergency stop complete.")

    async def stop(self) -> None:
        """Graceful shutdown: one final balance check then stop."""
        print("[guardian] Shutting down — running final check...")
        try:
            await self._check_and_update()
        except Exception:
            pass
        self._shutdown_event.set()
        await self._broadcast({"type": "AGENT_STATUS", "agent": "guardian", "status": "STOPPED"})
