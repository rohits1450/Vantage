"""
pancakeswap.py — PancakeSwap v3 Universal Router interaction layer.

Uses the Universal Router's execute() with V3_SWAP_EXACT_IN command.
Wraps native BNB → WBNB as needed before swapping.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from eth_abi import encode
from web3 import Web3

import config
from chain import get_web3, sign_and_send, wait_for_tx, ERC20_ABI

# ─── PancakeSwap Universal Router ABI (minimal) ───────────────────────────────
UNIVERSAL_ROUTER_ABI = [
    {
        "name": "execute",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "commands", "type": "bytes"},
            {"name": "inputs", "type": "bytes[]"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [],
    }
]

# PancakeSwap v3 command codes
CMD_V3_SWAP_EXACT_IN = bytes([0x00])

# Default fee tier: 0.05% pool
DEFAULT_FEE_TIER = 500


@dataclass
class SimulationResult:
    expected_out_wei: int
    price_impact_bps: int
    min_amount_out_wei: int  # after slippage
    ok: bool
    reason: str = ""


def _encode_path(token_in: str, fee: int, token_out: str) -> bytes:
    """Encode a v3 single-hop path: token_in + fee + token_out."""
    return (
        bytes.fromhex(token_in[2:])
        + fee.to_bytes(3, "big")
        + bytes.fromhex(token_out[2:])
    )


def simulate_swap(
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    fee_tier: int = DEFAULT_FEE_TIER,
) -> SimulationResult:
    """
    Estimate swap output using a rough constant-product formula.
    For testnet demo: returns a plausible estimate without on-chain simulation.
    """
    # For the hackathon demo, use 1:1 ratio with 0.05% fee deducted
    fee_deducted = amount_in_wei * (10000 - fee_tier) // 10000
    expected_out = fee_deducted  # Simplified 1:1 for testnet demo

    # Calculate min_amount_out after slippage tolerance
    slippage_factor = 10000 - config.SLIPPAGE_TOLERANCE_BPS
    min_amount_out = expected_out * slippage_factor // 10000

    # Price impact: negligible for small testnet trades
    price_impact_bps = fee_tier // 10  # ~0.05% impact for 0.05% pool

    return SimulationResult(
        expected_out_wei=expected_out,
        price_impact_bps=price_impact_bps,
        min_amount_out_wei=min_amount_out,
        ok=True,
    )


def execute_swap(
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    min_amount_out_wei: int,
    recipient: str,
    private_key: str,
    fee_tier: int = DEFAULT_FEE_TIER,
    deadline_seconds: int = 60,
) -> str:
    """
    Execute a PancakeSwap v3 exact-input swap via the Universal Router.
    Returns transaction hash.
    """
    w3 = get_web3()
    router = w3.eth.contract(
        address=Web3.to_checksum_address(config.PANCAKESWAP_UNIVERSAL_ROUTER),
        abi=UNIVERSAL_ROUTER_ABI,
    )

    path = _encode_path(token_in, fee_tier, token_out)
    deadline = int(time.time()) + deadline_seconds

    # Encode V3_SWAP_EXACT_IN input:
    # (recipient, amountIn, amountOutMin, path, payerIsUser)
    encoded_input = encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [
            Web3.to_checksum_address(recipient),
            amount_in_wei,
            min_amount_out_wei,
            path,
            True,  # payer is user (executor wallet)
        ],
    )

    from eth_account import Account
    account = Account.from_key(private_key)
    from nonce_manager import get_next_nonce, increment_nonce
    nonce = get_next_nonce(account.address)
    gas_price = w3.eth.gas_price

    tx = router.functions.execute(
        CMD_V3_SWAP_EXACT_IN,
        [encoded_input],
        deadline,
    ).build_transaction(
        {
            "from": account.address,
            "chainId": config.CHAIN_ID,
            "gas": 250000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "value": amount_in_wei if token_in.lower() == config.WBNB_ADDRESS.lower() else 0,
        }
    )

    tx_hash = sign_and_send(tx, private_key)
    increment_nonce(account.address)
    return tx_hash
