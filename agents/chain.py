"""
chain.py — Shared web3.py BSC connection with RPC failover.

Provides all low-level blockchain primitives used by the executor and guardian.
No private keys are stored here; callers pass them in for signing.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.types import TxReceipt

import config

# ─── Minimal ABIs ─────────────────────────────────────────────────────────────
ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

MAX_UINT256 = 2**256 - 1


def get_web3() -> Web3:
    """Return a connected Web3 instance, falling back to secondary RPC on failure."""
    for rpc_url in [config.BSC_RPC_PRIMARY, config.BSC_RPC_FALLBACK]:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
            if w3.is_connected():
                return w3
        except Exception:
            continue
    raise ConnectionError("[chain] Could not connect to any BSC RPC endpoint.")


def get_bnb_balance(address: str) -> float:
    """Return BNB balance in ETH units (float)."""
    w3 = get_web3()
    return float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(address)), "ether"))


def get_token_balance(token_address: str, wallet_address: str) -> int:
    """Return ERC-20 token balance in raw Wei units."""
    w3 = get_web3()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
    )
    return contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()


def get_token_allowance(token_address: str, owner: str, spender: str) -> int:
    """Return the current allowance for a spender."""
    w3 = get_web3()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
    )
    return contract.functions.allowance(
        Web3.to_checksum_address(owner),
        Web3.to_checksum_address(spender),
    ).call()


def get_gas_price_gwei() -> float:
    """Return current gas price in Gwei."""
    w3 = get_web3()
    return float(w3.from_wei(w3.eth.gas_price, "gwei"))


def sign_and_send(tx: dict, private_key: str) -> str:
    """Sign a transaction dict and broadcast it. Returns tx_hash hex."""
    w3 = get_web3()
    account: LocalAccount = Account.from_key(private_key)
    signed = account.sign_transaction(tx)
    
    # Defensively support both rawTransaction and raw_transaction across different eth-account versions
    raw_tx = getattr(signed, "rawTransaction", getattr(signed, "raw_transaction", None))
    if raw_tx is None:
        raise AttributeError("[chain] Signed transaction has neither rawTransaction nor raw_transaction attribute")
        
    tx_hash = w3.eth.send_rawTransaction(raw_tx)
    return tx_hash.hex()


def wait_for_tx(tx_hash: str, timeout: int = 120) -> TxReceipt:
    """Block until a transaction is mined. Raises TimeoutError if timeout exceeded."""
    w3 = get_web3()
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)


def approve_token(
    token_address: str,
    spender_address: str,
    amount: int,
    private_key: str,
) -> str:
    """Submit an ERC-20 approve() transaction. Returns tx_hash."""
    w3 = get_web3()
    account: LocalAccount = Account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
    )
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = contract.functions.approve(
        Web3.to_checksum_address(spender_address), amount
    ).build_transaction(
        {
            "from": account.address,
            "chainId": config.CHAIN_ID,
            "gas": 60000,
            "gasPrice": gas_price,
            "nonce": nonce,
        }
    )
    return sign_and_send(tx, private_key)


def revoke_token_approval(
    token_address: str, spender_address: str, private_key: str
) -> str:
    """Set token allowance to 0 (revoke). Returns tx_hash."""
    return approve_token(token_address, spender_address, 0, private_key)


def revoke_all_approvals(
    token_addresses: list[str],
    spender_addresses: list[str],
    private_key: str,
) -> list[str]:
    """
    Revoke all token approvals for the given spenders.
    Processes sequentially to avoid nonce collisions.
    """
    tx_hashes: list[str] = []
    for token in token_addresses:
        for spender in spender_addresses:
            try:
                current = get_token_allowance(token, Account.from_key(private_key).address, spender)
                if current > 0:
                    tx = revoke_token_approval(token, spender, private_key)
                    tx_hashes.append(tx)
                    print(f"[chain] Revoked {token} → {spender} | tx: {tx}")
                    # Small delay to avoid nonce issues
                    import time; time.sleep(2)
            except Exception as e:
                print(f"[chain] Warning: could not revoke {token} → {spender}: {e}")
    return tx_hashes


def transfer_bnb(to_address: str, amount_ether: float, private_key: str) -> str:
    """Transfer BNB to an address. Returns tx_hash."""
    w3 = get_web3()
    account: LocalAccount = Account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    amount_wei = w3.to_wei(amount_ether, "ether")

    tx = {
        "to": Web3.to_checksum_address(to_address),
        "value": amount_wei,
        "gas": 21000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": config.CHAIN_ID,
    }
    return sign_and_send(tx, private_key)
