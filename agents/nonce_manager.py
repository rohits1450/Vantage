"""
nonce_manager.py — Per-wallet nonce tracker for crash-safe transaction sequencing.

Prevents nonce collisions and handles recovery after unexpected restarts
by syncing from the chain on startup.
"""
from __future__ import annotations

import asyncio
from threading import Lock

from chain import get_web3


class NonceManager:
    """
    Thread-safe nonce cache that syncs from the chain on first use
    and increments locally for each submitted transaction.
    """

    def __init__(self) -> None:
        self._cache: dict[str, int] = {}
        self._lock = Lock()

    def sync_from_chain(self, wallet_address: str) -> int:
        """
        Query the chain for the current confirmed nonce.
        Call this on agent startup to pick up where we left off.
        """
        w3 = get_web3()
        nonce = w3.eth.get_transaction_count(wallet_address, "pending")
        with self._lock:
            self._cache[wallet_address] = nonce
        print(f"[nonce] Synced {wallet_address[:10]}… → nonce={nonce}")
        return nonce

    def get_next_nonce(self, wallet_address: str) -> int:
        """Return the next nonce to use. Syncs from chain if not cached."""
        with self._lock:
            if wallet_address not in self._cache:
                w3 = get_web3()
                self._cache[wallet_address] = w3.eth.get_transaction_count(
                    wallet_address, "pending"
                )
            return self._cache[wallet_address]

    def increment(self, wallet_address: str) -> None:
        """Call after a transaction is successfully submitted."""
        with self._lock:
            self._cache[wallet_address] = self._cache.get(wallet_address, 0) + 1

    def reset(self, wallet_address: str) -> None:
        """Force re-sync from chain on next use (call after a failed/dropped tx)."""
        with self._lock:
            self._cache.pop(wallet_address, None)


# Module-level singleton
_manager = NonceManager()


def get_next_nonce(wallet_address: str) -> int:
    return _manager.get_next_nonce(wallet_address)


def increment_nonce(wallet_address: str) -> None:
    _manager.increment(wallet_address)


def reset_nonce(wallet_address: str) -> None:
    _manager.reset(wallet_address)


def sync_nonce(wallet_address: str) -> int:
    return _manager.sync_from_chain(wallet_address)
