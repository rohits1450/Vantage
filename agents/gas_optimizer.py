"""
gas_optimizer.py — Gas price monitor with automatic trade deferral on spikes.
"""
from __future__ import annotations

from chain import get_web3
import config


def get_safe_gas_price_wei() -> int | None:
    """
    Return current gas price in Wei if within acceptable range, else None.
    On testnet, gas is always low. On mainnet, this prevents overpaying.
    """
    try:
        w3 = get_web3()
        gas_price_wei = w3.eth.gas_price
        gas_price_gwei = float(w3.from_wei(gas_price_wei, "gwei"))
        if gas_price_gwei > config.MAX_GAS_GWEI:
            print(
                f"[gas] Gas spike detected: {gas_price_gwei:.2f} Gwei "
                f"(limit: {config.MAX_GAS_GWEI} Gwei). Deferring trade."
            )
            return None
        return gas_price_wei
    except Exception as e:
        print(f"[gas] Warning: could not fetch gas price: {e}")
        return None


def is_gas_acceptable() -> bool:
    """Quick boolean check: is current gas price within our configured ceiling?"""
    return get_safe_gas_price_wei() is not None


def get_gas_price_gwei() -> float:
    """Return current gas price in Gwei for display purposes."""
    try:
        w3 = get_web3()
        return float(w3.from_wei(w3.eth.gas_price, "gwei"))
    except Exception:
        return 0.0
