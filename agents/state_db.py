"""
state_db.py — SQLite async database wrapper.

This DB is the SINGLE SOURCE OF TRUTH for inter-process communication
between the executor and guardian. No HTTP polling is used for halt state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).parent / "vantage_agents.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id     TEXT    UNIQUE,
                asset         TEXT,
                direction     TEXT,
                amount_bnb    REAL,
                entry_price   REAL,
                exit_price    REAL,
                tx_hash       TEXT,
                status        TEXT DEFAULT 'PENDING',
                pnl_pct       REAL,
                regime        TEXT,
                conviction    INTEGER,
                demo          INTEGER DEFAULT 0,
                created_at    TEXT,
                confirmed_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS positions (
                asset         TEXT PRIMARY KEY,
                amount        REAL,
                entry_price   REAL,
                updated_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS guardian_state (
                id                   INTEGER PRIMARY KEY DEFAULT 1,
                peak_equity_bnb      REAL    DEFAULT 0.0,
                current_equity_bnb   REAL    DEFAULT 0.0,
                drawdown_pct         REAL    DEFAULT 0.0,
                consecutive_losses   INTEGER DEFAULT 0,
                is_halted            INTEGER DEFAULT 0,
                halt_reason          TEXT,
                halted_at            TEXT,
                last_check_at        TEXT
            );

            INSERT OR IGNORE INTO guardian_state (id) VALUES (1);

            CREATE TABLE IF NOT EXISTS agent_identities (
                agent_name       TEXT PRIMARY KEY,
                token_id         INTEGER,
                wallet_address   TEXT,
                registration_tx  TEXT,
                registered_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger              TEXT,
                drawdown_pct         REAL,
                consecutive_losses   INTEGER,
                actions_taken        TEXT,
                incident_nft_tx      TEXT,
                equity_recovered_bnb REAL,
                created_at           TEXT
            );
        """)
        await db.commit()


# ─── Trades ──────────────────────────────────────────────────────────────────

async def insert_trade(
    signal_id: str,
    asset: str,
    direction: str,
    amount_bnb: float,
    entry_price: float,
    tx_hash: str,
    regime: str,
    conviction: int,
    demo: bool = False,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO trades
               (signal_id, asset, direction, amount_bnb, entry_price, tx_hash,
                regime, conviction, demo, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
            (signal_id, asset, direction, amount_bnb, entry_price, tx_hash,
             regime, conviction, int(demo), _now()),
        )
        await db.commit()


async def confirm_trade(
    signal_id: str,
    status: str,
    exit_price: float = 0.0,
    pnl_pct: float = 0.0,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE trades SET status=?, exit_price=?, pnl_pct=?, confirmed_at=?
               WHERE signal_id=?""",
            (status, exit_price, pnl_pct, _now(), signal_id),
        )
        await db.commit()


async def get_recent_trades(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def count_consecutive_losses() -> int:
    """Count the current unbroken streak of losing trades (pnl_pct < 0)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT pnl_pct FROM trades WHERE status='CONFIRMED' ORDER BY confirmed_at DESC LIMIT 20"
        ) as cursor:
            rows = await cursor.fetchall()

    streak = 0
    for row in rows:
        if row["pnl_pct"] is not None and row["pnl_pct"] < 0:
            streak += 1
        else:
            break
    return streak


# ─── Guardian State ──────────────────────────────────────────────────────────

async def update_guardian_state(
    current_equity_bnb: float,
    peak_equity_bnb: float,
    drawdown_pct: float,
    consecutive_losses: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE guardian_state SET
               current_equity_bnb=?, peak_equity_bnb=?, drawdown_pct=?,
               consecutive_losses=?, last_check_at=?
               WHERE id=1""",
            (current_equity_bnb, peak_equity_bnb, drawdown_pct, consecutive_losses, _now()),
        )
        await db.commit()


async def set_halted(halted: bool, reason: str = "") -> None:
    """Atomically set or clear the halt flag."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE guardian_state SET
               is_halted=?, halt_reason=?, halted_at=?
               WHERE id=1""",
            (int(halted), reason if halted else None, _now() if halted else None),
        )
        await db.commit()


async def get_guardian_state() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guardian_state WHERE id=1") as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else {}


# ─── Positions ───────────────────────────────────────────────────────────────

async def upsert_position(asset: str, amount: float, entry_price: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO positions (asset, amount, entry_price, updated_at)
               VALUES (?, ?, ?, ?)""",
            (asset, amount, entry_price, _now()),
        )
        await db.commit()


async def clear_position(asset: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM positions WHERE asset=?", (asset,))
        await db.commit()


async def get_all_positions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM positions") as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─── Agent Identities ────────────────────────────────────────────────────────

async def save_agent_identity(
    agent_name: str,
    token_id: int,
    wallet_address: str,
    registration_tx: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO agent_identities
               (agent_name, token_id, wallet_address, registration_tx, registered_at)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_name, token_id, wallet_address, registration_tx, _now()),
        )
        await db.commit()


async def get_agent_identities() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agent_identities") as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─── Incidents ───────────────────────────────────────────────────────────────

async def save_incident(
    trigger: str,
    drawdown_pct: float,
    consecutive_losses: int,
    actions_taken: list[str],
    incident_nft_tx: str,
    equity_recovered_bnb: float,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO incidents
               (trigger, drawdown_pct, consecutive_losses, actions_taken,
                incident_nft_tx, equity_recovered_bnb, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trigger, drawdown_pct, consecutive_losses,
                json.dumps(actions_taken), incident_nft_tx,
                equity_recovered_bnb, _now(),
            ),
        )
        await db.commit()
        return cursor.lastrowid
