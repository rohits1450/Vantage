"""
config.py — Centralized configuration loader for the Vantage Agent Layer.

Loads all settings from .env.agents and decrypts keystore files into
private keys at startup. Private keys are NEVER logged or written to disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from eth_account import Account

# Load .env.agents from the same directory as this file
_ENV_PATH = Path(__file__).parent / ".env.agents"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"[config] Required env var '{key}' is missing in .env.agents")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def load_wallet(keystore_path: str, password: str) -> tuple[str, str]:
    """
    Decrypt an Ethereum keystore file.
    Returns (private_key_hex, address). Never logs the private key.
    """
    ks_path = Path(__file__).parent / keystore_path
    if not ks_path.exists():
        raise FileNotFoundError(
            f"[config] Keystore not found: {ks_path}\n"
            "Run agents/setup.bat (Windows) or agents/setup.sh to generate keystores."
        )
    with open(ks_path) as f:
        keystore = json.load(f)
    private_key = Account.decrypt(keystore, password)
    account = Account.from_key(private_key)
    return private_key.hex(), account.address


# ─── Chain ───────────────────────────────────────────────────────────────────
CHAIN_ID: int = int(_optional("CHAIN_ID", "97"))
BSC_RPC_PRIMARY: str = _optional("BSC_RPC_PRIMARY", "https://data-seed-prebsc-1-s1.binance.org:8545")
BSC_RPC_FALLBACK: str = _optional("BSC_RPC_FALLBACK", "https://data-seed-prebsc-2-s1.binance.org:8545")
BSCSCAN_BASE_URL: str = _optional("BSCSCAN_BASE_URL", "https://testnet.bscscan.com")

# ─── Wallets (decrypted lazily on first use) ──────────────────────────────────
_EXECUTOR_KEYSTORE_PATH: str = _optional("EXECUTOR_KEYSTORE_PATH", "keystores/executor.json")
_EXECUTOR_KEYSTORE_PASS: str = _optional("EXECUTOR_KEYSTORE_PASS", "")
_GUARDIAN_KEYSTORE_PATH: str = _optional("GUARDIAN_KEYSTORE_PATH", "keystores/guardian.json")
_GUARDIAN_KEYSTORE_PASS: str = _optional("GUARDIAN_KEYSTORE_PASS", "")

COLD_WALLET_ADDRESS: str = _optional("COLD_WALLET_ADDRESS", "")

# ─── Cached wallet values (populated by load_all_wallets()) ──────────────────
EXECUTOR_PRIVATE_KEY: Optional[str] = None
EXECUTOR_WALLET_ADDRESS: str = _optional("EXECUTOR_WALLET_ADDRESS", "")
GUARDIAN_PRIVATE_KEY: Optional[str] = None
GUARDIAN_WALLET_ADDRESS: str = _optional("GUARDIAN_WALLET_ADDRESS", "")


def load_all_wallets() -> None:
    """
    Decrypt both keystores and populate the module-level wallet variables.
    Call once during orchestrator/agent startup.
    """
    global EXECUTOR_PRIVATE_KEY, EXECUTOR_WALLET_ADDRESS
    global GUARDIAN_PRIVATE_KEY, GUARDIAN_WALLET_ADDRESS

    keystores_dir = Path(__file__).parent / "keystores"
    if not keystores_dir.exists():
        raise FileNotFoundError(
            "[config] keystores/ directory not found. Run setup.bat / setup.sh first."
        )

    EXECUTOR_PRIVATE_KEY, EXECUTOR_WALLET_ADDRESS = load_wallet(
        _EXECUTOR_KEYSTORE_PATH, _EXECUTOR_KEYSTORE_PASS
    )
    GUARDIAN_PRIVATE_KEY, GUARDIAN_WALLET_ADDRESS = load_wallet(
        _GUARDIAN_KEYSTORE_PATH, _GUARDIAN_KEYSTORE_PASS
    )
    print(f"[config] Executor wallet: {EXECUTOR_WALLET_ADDRESS}")
    print(f"[config] Guardian wallet: {GUARDIAN_WALLET_ADDRESS}")


# ─── Orchestrator ─────────────────────────────────────────────────────────────
ORCHESTRATOR_WS_PORT: int = int(_optional("ORCHESTRATOR_WS_PORT", "8765"))
ORCHESTRATOR_HTTP_PORT: int = int(_optional("ORCHESTRATOR_HTTP_PORT", "8766"))

# ─── Trading parameters ───────────────────────────────────────────────────────
MAX_TRADE_SIZE_BNB: float = float(_optional("MAX_TRADE_SIZE_BNB", "0.01"))
MIN_GAS_RESERVE_BNB: float = float(_optional("MIN_GAS_RESERVE_BNB", "0.005"))
SLIPPAGE_TOLERANCE_BPS: int = int(_optional("SLIPPAGE_TOLERANCE_BPS", "50"))
MAX_GAS_GWEI: float = float(_optional("MAX_GAS_GWEI", "10.0"))
CMC_DATA_STALENESS_MAX_SEC: int = int(_optional("CMC_DATA_STALENESS_MAX_SEC", "120"))

# ─── Guardian thresholds ──────────────────────────────────────────────────────
GUARDIAN_MAX_DRAWDOWN_PCT: float = float(_optional("GUARDIAN_MAX_DRAWDOWN_PCT", "20.0"))
GUARDIAN_MAX_CONSECUTIVE_LOSSES: int = int(_optional("GUARDIAN_MAX_CONSECUTIVE_LOSSES", "5"))
GUARDIAN_POLL_INTERVAL_SEC: int = int(_optional("GUARDIAN_POLL_INTERVAL_SEC", "30"))
GUARDIAN_HEARTBEAT_TIMEOUT_SEC: int = int(_optional("GUARDIAN_HEARTBEAT_TIMEOUT_SEC", "90"))

# ─── Agent identities ─────────────────────────────────────────────────────────
EXECUTOR_AGENT_TOKEN_ID: Optional[int] = (
    int(_optional("EXECUTOR_AGENT_TOKEN_ID")) if _optional("EXECUTOR_AGENT_TOKEN_ID") else None
)
GUARDIAN_AGENT_TOKEN_ID: Optional[int] = (
    int(_optional("GUARDIAN_AGENT_TOKEN_ID")) if _optional("GUARDIAN_AGENT_TOKEN_ID") else None
)

# ─── Contract addresses (BSC Testnet) ────────────────────────────────────────
ERC8004_IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
ERC8004_REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713"
PANCAKESWAP_UNIVERSAL_ROUTER = "0x9A082015c919AD0E47861e5Db9A1c7070E81A2C7"
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
WBNB_ADDRESS = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
USDT_ADDRESS = "0x337610d27c682E347C9cD60BD4b3b107C9d34dD"

# ─── Demo mode ────────────────────────────────────────────────────────────────
DEMO_MODE: bool = _optional("DEMO_MODE", "true").lower() == "true"
