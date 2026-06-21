"""
register_agents.py — One-time ERC-8004 NFT agent identity registration.

Calls the ERC-8004 Identity Registry contract DIRECTLY via web3.py.
No fictional SDKs. Uses the verified BSC Testnet contract address.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from datetime import datetime, timezone

from eth_account import Account
from web3 import Web3

import config
from config import load_all_wallets
import state_db
from chain import get_web3, sign_and_send, wait_for_tx

# ─── ERC-8004 Identity Registry ABI (minimal) ─────────────────────────────────
IDENTITY_REGISTRY_ABI = [
    {
        "name": "register",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "metadataURI", "type": "string"}],
        "outputs": [{"name": "tokenId", "type": "uint256"}],
    },
    {
        "name": "AgentRegistered",
        "type": "event",
        "inputs": [
            {"name": "tokenId", "type": "uint256", "indexed": True},
            {"name": "owner", "type": "address", "indexed": True},
        ],
    },
]


def build_agent_card(
    name: str,
    description: str,
    wallet_address: str,
    owner_address: str,
    capabilities: list[str],
) -> str:
    """Build an ERC-8004 Agent Card JSON and return it as a data URI."""
    card = {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "standard": "ERC-8004",
        "capabilities": capabilities,
        "protocols": ["http"],
        "walletAddress": wallet_address,
        "owner": owner_address,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "projectUrl": "https://github.com/leobergjackson/BNB-hacakthon-2026",
    }
    card_json = json.dumps(card, indent=2)
    encoded = base64.b64encode(card_json.encode()).decode()
    return f"data:application/json;base64,{encoded}"


def register_agent(
    agent_name: str,
    agent_card_uri: str,
    private_key: str,
) -> tuple[str, int]:
    """
    Call register() on the ERC-8004 Identity Registry.
    Returns (tx_hash, token_id).
    """
    w3 = get_web3()
    account = Account.from_key(private_key)
    registry = w3.eth.contract(
        address=Web3.to_checksum_address(config.ERC8004_IDENTITY_REGISTRY),
        abi=IDENTITY_REGISTRY_ABI,
    )

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = registry.functions.register(agent_card_uri).build_transaction(
        {
            "from": account.address,
            "chainId": config.CHAIN_ID,
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": nonce,
        }
    )

    tx_hash = sign_and_send(tx, private_key)
    print(f"[register] {agent_name} tx submitted: {tx_hash}")
    print("[register] Waiting for confirmation...")

    receipt = wait_for_tx(tx_hash)
    if receipt["status"] != 1:
        raise RuntimeError(f"[register] Transaction failed for {agent_name}")

    # Parse AgentRegistered event to get token ID
    token_id = 0
    try:
        logs = registry.events.AgentRegistered().process_receipt(receipt)
        if logs:
            token_id = logs[0]["args"]["tokenId"]
    except Exception:
        # Fallback: derive from receipt if event parsing fails
        token_id = int(receipt["logs"][0]["topics"][1].hex(), 16) if receipt.get("logs") else 0

    return tx_hash, token_id


async def main() -> None:
    print("=" * 60)
    print("  Vantage — ERC-8004 Agent Registration")
    print("=" * 60)

    # Load keystores
    try:
        load_all_wallets()
    except FileNotFoundError as e:
        print(f"\n❌ {e}\n")
        sys.exit(1)

    await state_db.init_db()

    # Check if already registered
    identities = await state_db.get_agent_identities()
    registered = {i["agent_name"] for i in identities}

    # ── Register Executor ──────────────────────────────────────────────────
    if "executor" in registered:
        print(f"✅ Executor already registered (skip). View: {config.BSCSCAN_BASE_URL}")
    else:
        print("\n[1/2] Registering Execution Agent...")
        card_uri = build_agent_card(
            name="Vantage EDI Executor",
            description=(
                "Autonomous execution agent for the Emotional Duality v2 trading strategy "
                "on BNB Chain. Executes PancakeSwap v3 swaps when EDI signals fire."
            ),
            wallet_address=config.EXECUTOR_WALLET_ADDRESS,
            owner_address=config.EXECUTOR_WALLET_ADDRESS,
            capabilities=["trade_execution", "signal_processing", "pancakeswap_v3"],
        )

        tx_hash, token_id = register_agent(
            "Vantage EDI Executor", card_uri, config.EXECUTOR_PRIVATE_KEY
        )
        await state_db.save_agent_identity(
            "executor", token_id, config.EXECUTOR_WALLET_ADDRESS, tx_hash
        )

        # Patch .env.agents with the token ID
        _patch_env("EXECUTOR_AGENT_TOKEN_ID", str(token_id))
        _patch_env("EXECUTOR_WALLET_ADDRESS", config.EXECUTOR_WALLET_ADDRESS)

        print(f"\n✅ Executor registered!")
        print(f"   Token ID:  #{token_id}")
        print(f"   Wallet:    {config.EXECUTOR_WALLET_ADDRESS}")
        print(f"   Tx:        {config.BSCSCAN_BASE_URL}/tx/{tx_hash}")

    # ── Register Guardian ──────────────────────────────────────────────────
    if "guardian" in registered:
        print(f"✅ Guardian already registered (skip).")
    else:
        print("\n[2/2] Registering Risk Guardian...")
        card_uri = build_agent_card(
            name="Vantage EDI Guardian",
            description=(
                "24/7 autonomous risk guardian for the Vantage EDI trading system. "
                "Monitors drawdown and consecutive losses, triggers emergency stops, "
                "and mints incident reports as on-chain NFTs."
            ),
            wallet_address=config.GUARDIAN_WALLET_ADDRESS,
            owner_address=config.GUARDIAN_WALLET_ADDRESS,
            capabilities=["risk_monitoring", "emergency_stop", "incident_reporting"],
        )

        tx_hash, token_id = register_agent(
            "Vantage EDI Guardian", card_uri, config.GUARDIAN_PRIVATE_KEY
        )
        await state_db.save_agent_identity(
            "guardian", token_id, config.GUARDIAN_WALLET_ADDRESS, tx_hash
        )

        _patch_env("GUARDIAN_AGENT_TOKEN_ID", str(token_id))
        _patch_env("GUARDIAN_WALLET_ADDRESS", config.GUARDIAN_WALLET_ADDRESS)

        print(f"\n✅ Guardian registered!")
        print(f"   Token ID:  #{token_id}")
        print(f"   Wallet:    {config.GUARDIAN_WALLET_ADDRESS}")
        print(f"   Tx:        {config.BSCSCAN_BASE_URL}/tx/{tx_hash}")

    print("\n" + "=" * 60)
    print("  Registration complete. Run: python orchestrator.py")
    print("=" * 60)


def _patch_env(key: str, value: str) -> None:
    """Update a key=value line in .env.agents without overwriting the whole file."""
    from pathlib import Path
    env_path = Path(__file__).parent / ".env.agents"
    lines = env_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
