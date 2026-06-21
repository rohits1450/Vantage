@echo off
REM ============================================================
REM Vantage AI Agent Layer — Windows Setup Script
REM ============================================================
echo.
echo === Vantage Agent Layer Setup (Windows) ===
echo.

REM 1. Create Python virtual environment
echo [1/5] Creating Python virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: python not found. Install Python 3.11+ from https://python.org
    exit /b 1
)
call venv\Scripts\activate.bat

REM 2. Install dependencies
echo.
echo [2/5] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
)

REM 3. Create keystores directory
echo.
echo [3/5] Generating encrypted wallets...
if not exist "keystores" mkdir keystores

REM Generate both wallets using Python
echo import json, sys > setup_helper.py
echo from eth_account import Account >> setup_helper.py
echo passw = 'devpassword123' >> setup_helper.py
echo exec_wallet = Account.create() >> setup_helper.py
echo guard_wallet = Account.create() >> setup_helper.py
echo with open('keystores/executor.json', 'w') as f: json.dump(exec_wallet.encrypt(passw), f) >> setup_helper.py
echo with open('keystores/guardian.json', 'w') as f: json.dump(guard_wallet.encrypt(passw), f) >> setup_helper.py
echo print('\n  Executor Address: ' + exec_wallet.address) >> setup_helper.py
echo print('  Guardian Address: ' + guard_wallet.address) >> setup_helper.py
echo print('\n  Keystore password: devpassword123') >> setup_helper.py
echo print('  Change EXECUTOR_KEYSTORE_PASS / GUARDIAN_KEYSTORE_PASS in .env.agents') >> setup_helper.py
echo lines = open('.env.agents').read().splitlines() >> setup_helper.py
echo patches = {'EXECUTOR_WALLET_ADDRESS': exec_wallet.address, 'GUARDIAN_WALLET_ADDRESS': guard_wallet.address} >> setup_helper.py
echo for i, line in enumerate(lines): >> setup_helper.py
echo     for k, v in patches.items(): >> setup_helper.py
echo         if line.startswith(k + '='): lines[i] = k + '=' + v >> setup_helper.py
echo open('.env.agents', 'w').write('\n'.join(lines) + '\n') >> setup_helper.py

python setup_helper.py
del setup_helper.py


echo.
echo [4/5] MANUAL STEP REQUIRED:
echo.
echo   Fund the following wallets with BSC Testnet BNB:
echo   Faucet: https://testnet.bnbchain.org/faucet-smart
echo.
echo   (Also fund your COLD_WALLET_ADDRESS in .env.agents)
echo.
pause

REM 5. Register agents on-chain
echo.
echo [5/5] Registering ERC-8004 agent identities on-chain...
python register_agents.py
if errorlevel 1 (
    echo ERROR: Registration failed. Check your wallet balance and RPC connection.
    exit /b 1
)

echo.
echo =====================================================
echo   Setup complete!
echo   Start the agent layer with: python orchestrator.py
echo =====================================================
echo.
