"""
orchestrator.py — Vantage Agent Layer Orchestrator.

Responsibilities:
  1. WebSocket server (port 8765) — broadcasts events to the frontend
  2. HTTP server (port 8766) — receives signals from Next.js backend
  3. Spawns and supervises ExecutorAgent and GuardianAgent coroutines
  4. Rate-limits /signal endpoint (1 per 10s per asset; 10 per min global)
  5. Graceful shutdown on SIGINT/SIGTERM
  6. Sends TRADE_HISTORY (last 20 trades) to every new WS connection

Run with: python orchestrator.py
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional, Set

import aiohttp
import aiohttp.web
import websockets
import websockets.server

import config
import state_db
from config import load_all_wallets
from executor import ExecutorAgent, AgentSignal
from guardian import GuardianAgent

# ─── Rate Limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Sliding window rate limiter stored in process memory.
    - Max 1 signal per 10 seconds per asset
    - Max 10 signals per minute globally
    """
    def __init__(self) -> None:
        self._per_asset: dict[str, deque] = defaultdict(deque)
        self._global: deque = deque()

    def check(self, asset: str) -> tuple[bool, str]:
        now = time.time()

        # Clean expired entries
        while self._global and now - self._global[0] > 60:
            self._global.popleft()
        asset_q = self._per_asset[asset]
        while asset_q and now - asset_q[0] > 10:
            asset_q.popleft()

        # Check global limit
        if len(self._global) >= 10:
            return False, "Rate limit: max 10 signals/minute globally"

        # Check per-asset limit
        if len(asset_q) >= 1:
            wait = 10 - (now - asset_q[-1])
            return False, f"Rate limit: 1 signal/10s per asset (wait {wait:.1f}s)"

        # Record
        self._global.append(now)
        asset_q.append(now)
        return True, "ok"


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self) -> None:
        self._ws_clients: Set[websockets.server.WebSocketServerProtocol] = set()
        self._rate_limiter = RateLimiter()
        self._executor: Optional[ExecutorAgent] = None
        self._guardian: Optional[GuardianAgent] = None
        self._shutdown_event = asyncio.Event()

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        payload = json.dumps(message)
        dead: set = set()
        for ws in self._ws_clients:
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    async def _ws_handler(
        self, ws: websockets.server.WebSocketServerProtocol
    ) -> None:
        """Handle a new WebSocket connection."""
        self._ws_clients.add(ws)
        client_addr = ws.remote_address
        print(f"[ws] Client connected: {client_addr}")

        # Hydrate client with recent trade history
        try:
            trades = await state_db.get_recent_trades(limit=20)
            identities = await state_db.get_agent_identities()
            guardian_state = await state_db.get_guardian_state()

            await ws.send(json.dumps({
                "type": "TRADE_HISTORY",
                "trades": trades,
            }))
            await ws.send(json.dumps({
                "type": "AGENT_IDENTITIES",
                "identities": identities,
            }))
            await ws.send(json.dumps({
                "type": "GUARDIAN_STATE",
                **guardian_state,
            }))

            # Initial status
            await ws.send(json.dumps({
                "type": "AGENT_STATUS",
                "agent": "executor",
                "status": "RUNNING" if self._executor else "OFFLINE",
                "demo_mode": config.DEMO_MODE,
                "wallet": config.EXECUTOR_WALLET_ADDRESS,
                "token_id": config.EXECUTOR_AGENT_TOKEN_ID,
                "bscscan_url": config.BSCSCAN_BASE_URL,
            }))
            await ws.send(json.dumps({
                "type": "AGENT_STATUS",
                "agent": "guardian",
                "status": "RUNNING" if self._guardian else "OFFLINE",
                "wallet": config.GUARDIAN_WALLET_ADDRESS,
                "token_id": config.GUARDIAN_AGENT_TOKEN_ID,
            }))
        except Exception as e:
            print(f"[ws] Error hydrating client: {e}")

        try:
            # Keep connection alive until client disconnects
            await ws.wait_closed()
        finally:
            self._ws_clients.discard(ws)
            print(f"[ws] Client disconnected: {client_addr}")

    # ── HTTP Server ───────────────────────────────────────────────────────────

    async def _handle_signal(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """POST /signal — Receive trading signal from Next.js backend."""
        try:
            body = await request.json()
        except Exception:
            return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

        asset = body.get("asset", "UNKNOWN")

        # Rate limit check
        allowed, reason = self._rate_limiter.check(asset)
        if not allowed:
            print(f"[http] Rate limited: {reason}")
            return aiohttp.web.json_response({"error": reason}, status=429)

        # Validate minimum required fields
        required = ["signal_id", "asset", "direction", "generated_at"]
        for field in required:
            if field not in body:
                return aiohttp.web.json_response(
                    {"error": f"Missing field: {field}"}, status=400
                )

        signal = AgentSignal(
            signal_id=body["signal_id"],
            asset=body["asset"],
            direction=body["direction"],
            conviction=int(body.get("conviction", 7)),
            regime=body.get("regime", "UNKNOWN"),
            risk_pct=float(body.get("risk_pct", 1.0)),
            slippage_bps=int(body.get("slippage_bps", 50)),
            generated_at=body["generated_at"],
            portfolio_size_usd=float(body.get("portfolio_size_usd", 10000)),
            divergence_type=body.get("divergence_type", ""),
        )

        if self._executor:
            await self._executor.enqueue_signal(signal)
            print(f"[http] Signal queued: {signal.signal_id} ({asset} {signal.direction})")
            return aiohttp.web.json_response({"status": "queued"})
        else:
            return aiohttp.web.json_response({"error": "Executor not running"}, status=503)

    async def _handle_status(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """GET /status — Return combined agent status."""
        state = await state_db.get_guardian_state()
        identities = await state_db.get_agent_identities()
        recent_trades = await state_db.get_recent_trades(5)
        return aiohttp.web.json_response({
            "executor": {
                "running": self._executor is not None,
                "demo_mode": config.DEMO_MODE,
                "wallet": config.EXECUTOR_WALLET_ADDRESS,
                "token_id": config.EXECUTOR_AGENT_TOKEN_ID,
            },
            "guardian": {
                "running": self._guardian is not None,
                "wallet": config.GUARDIAN_WALLET_ADDRESS,
                "token_id": config.GUARDIAN_AGENT_TOKEN_ID,
                **state,
            },
            "identities": identities,
            "recent_trades": recent_trades,
        })

    async def _handle_settings(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """POST /settings — Update agent configuration at runtime."""
        try:
            body = await request.json()
        except Exception:
            return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

        if "max_drawdown_pct" in body:
            config.GUARDIAN_MAX_DRAWDOWN_PCT = float(body["max_drawdown_pct"])
        if "max_consecutive_losses" in body:
            config.GUARDIAN_MAX_CONSECUTIVE_LOSSES = int(body["max_consecutive_losses"])
        if "max_trade_size_bnb" in body:
            config.MAX_TRADE_SIZE_BNB = float(body["max_trade_size_bnb"])
        if "slippage_bps" in body:
            config.SLIPPAGE_TOLERANCE_BPS = int(body["slippage_bps"])

        print(f"[http] Settings updated: {body}")
        await self.broadcast({"type": "SETTINGS_UPDATED", **body})
        return aiohttp.web.json_response({"status": "updated"})

    async def _handle_control(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """POST /control — Manual agent control (stop, halt, restart)."""
        try:
            body = await request.json()
            action = body.get("action", "")
        except Exception:
            return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

        if action == "halt" and self._guardian:
            await self._guardian.trigger_emergency_stop("MANUAL_HALT", 0.0, 0)
            return aiohttp.web.json_response({"status": "halted"})
        elif action == "stop" and self._executor:
            await self._executor.stop()
            return aiohttp.web.json_response({"status": "executor_stopped"})
        elif action == "restart":
            # Signal main loop to restart
            await state_db.set_halted(False, "")
            return aiohttp.web.json_response({"status": "restart_requested"})
        else:
            return aiohttp.web.json_response({"error": f"Unknown action: {action}"}, status=400)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start all services and block until shutdown."""
        await state_db.init_db()

        # Create agents with broadcast injected
        self._executor = ExecutorAgent(broadcast_fn=self.broadcast)
        self._guardian = GuardianAgent(broadcast_fn=self.broadcast)

        # ── HTTP server ───────────────────────────────────────────────────
        app = aiohttp.web.Application()
        app.router.add_post("/signal", self._handle_signal)
        app.router.add_get("/status", self._handle_status)
        app.router.add_post("/settings", self._handle_settings)
        app.router.add_post("/control", self._handle_control)

        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", config.ORCHESTRATOR_HTTP_PORT)
        await site.start()
        print(f"[orchestrator] HTTP server: http://localhost:{config.ORCHESTRATOR_HTTP_PORT}")

        # ── WebSocket server ──────────────────────────────────────────────
        ws_server = await websockets.serve(
            self._ws_handler,
            "0.0.0.0",
            config.ORCHESTRATOR_WS_PORT,
        )
        print(f"[orchestrator] WebSocket server: ws://localhost:{config.ORCHESTRATOR_WS_PORT}")
        print(f"[orchestrator] Demo mode: {'ON ⚠️' if config.DEMO_MODE else 'OFF — real trades'}")
        print("[orchestrator] All systems nominal. Ctrl+C to stop.\n")

        # ── Run agents concurrently ───────────────────────────────────────
        try:
            await asyncio.gather(
                self._executor.start(),
                self._guardian.start(),
                self._shutdown_event.wait(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            # Cleanup
            ws_server.close()
            await ws_server.wait_closed()
            await runner.cleanup()

    async def shutdown(self) -> None:
        """Ordered graceful shutdown sequence."""
        print("\n[orchestrator] Shutdown initiated...")

        # 1. Set halt flag to stop any new trades
        await state_db.set_halted(True, "SYSTEM_SHUTDOWN")

        # 2. Stop both agents
        shutdown_tasks = []
        if self._executor:
            shutdown_tasks.append(asyncio.wait_for(self._executor.stop(), timeout=10))
        if self._guardian:
            shutdown_tasks.append(asyncio.wait_for(self._guardian.stop(), timeout=10))

        if shutdown_tasks:
            try:
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            except Exception as e:
                print(f"[orchestrator] Shutdown warning: {e}")

        # 3. Broadcast shutdown to WS clients
        await self.broadcast({"type": "SYSTEM_SHUTDOWN"})

        # 4. Signal the main run loop to exit
        self._shutdown_event.set()
        print("[orchestrator] Shutdown complete.")


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("  Vantage EDI — Agent Orchestrator")
    print("=" * 60)

    # Load and decrypt keystores
    try:
        load_all_wallets()
    except FileNotFoundError as e:
        print(f"\n❌ {e}\n")
        sys.exit(1)

    orchestrator = Orchestrator()

    # Signal handlers for graceful shutdown (SIGINT = Ctrl+C, SIGTERM = server restart)
    loop = asyncio.get_event_loop()

    def _handle_signal(sig_name: str) -> None:
        print(f"\n[orchestrator] Received {sig_name}...")
        loop.create_task(orchestrator.shutdown())

    for sig in [signal.SIGINT, signal.SIGTERM]:
        try:
            loop.add_signal_handler(sig, _handle_signal, sig.name)
        except NotImplementedError:
            # Windows doesn't fully support add_signal_handler; use SIGINT fallback
            pass

    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        print("\n[orchestrator] Interrupted by user. Shutting down gracefully...")
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
