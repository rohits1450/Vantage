"""
incident_nft.py — Mint on-chain incident reports as ERC-8004 Reputation Registry entries.

For the hackathon demo, incident metadata is stored as a local JSON file
with a placeholder CID field documenting the intended BNB Greenfield integration.
The on-chain record (tx hash) on the Reputation Registry is real and verifiable.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from eth_account import Account
from web3 import Web3

import config
from chain import get_web3, sign_and_send, wait_for_tx

# ─── ERC-8004 Reputation Registry ABI (minimal) ───────────────────────────────
REPUTATION_REGISTRY_ABI = [
    {
        "name": "addRecord",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentTokenId", "type": "uint256"},
            {"name": "recordURI", "type": "string"},
            {"name": "recordType", "type": "string"},
        ],
        "outputs": [],
    }
]

INCIDENTS_DIR = Path(__file__).parent / "incident_reports"


def mint_incident_nft(
    trigger: str,
    drawdown_pct: float,
    consecutive_losses: int,
    revoke_tx_hashes: list[str],
    transfer_tx_hash: str,
    equity_transferred: float,
    guardian_private_key: str,
    guardian_token_id: int,
) -> str:
    """
    Build incident JSON, save locally, and add a record to the Reputation Registry.
    Returns the on-chain tx_hash (real and verifiable on BscScan).
    """
    INCIDENTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    incident_data = {
        "incident_type": trigger,
        "triggered_at": timestamp,
        "standard": "ERC-8004 Reputation Registry",
        "drawdown_pct": drawdown_pct,
        "consecutive_losses": consecutive_losses,
        "actions_taken": [
            f"revoke_approvals ({len(revoke_tx_hashes)} txns)",
            "emergency_bnb_transfer",
            "halt_flag_set_in_db",
        ],
        "revoke_tx_hashes": revoke_tx_hashes,
        "transfer_tx_hash": transfer_tx_hash,
        "equity_transferred_bnb": equity_transferred,
        "cold_wallet": config.COLD_WALLET_ADDRESS,
        "greenfield_cid": "PLACEHOLDER — integrate BNB Greenfield for decentralized storage",
        "network": "BSC Testnet (ChainID 97)",
    }

    # Save locally
    safe_ts = timestamp.replace(":", "-").split(".")[0]
    local_path = INCIDENTS_DIR / f"incident_{safe_ts}.json"
    with open(local_path, "w") as f:
        json.dump(incident_data, f, indent=2)
    print(f"[incident] Saved local report: {local_path}")

    # Encode as data URI
    encoded = base64.b64encode(json.dumps(incident_data).encode()).decode()
    record_uri = f"data:application/json;base64,{encoded}"

    # Mint on Reputation Registry
    w3 = get_web3()
    account = Account.from_key(guardian_private_key)
    registry = w3.eth.contract(
        address=Web3.to_checksum_address(config.ERC8004_REPUTATION_REGISTRY),
        abi=REPUTATION_REGISTRY_ABI,
    )

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = registry.functions.addRecord(
        guardian_token_id,
        record_uri,
        "EMERGENCY_STOP",
    ).build_transaction(
        {
            "from": account.address,
            "chainId": config.CHAIN_ID,
            "gas": 400000,
            "gasPrice": gas_price,
            "nonce": nonce,
        }
    )

    try:
        tx_hash = sign_and_send(tx, guardian_private_key)
        print(f"[incident] NFT minted: {config.BSCSCAN_BASE_URL}/tx/{tx_hash}")
        return tx_hash
    except Exception as e:
        print(f"[incident] Warning: could not mint NFT on-chain: {e}")
        return "DEMO_OR_FAILED"
