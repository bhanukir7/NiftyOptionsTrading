"""
run.py — Unified Launcher for Nifty Options Trading (v2.0)

Universal entry point to handle PYTHONPATH issues and first-time setup.

Subcommands:
    python run.py dash              # Start the Web Dashboard (default)
    python run.py btst "CONTRACT"   # Run the BTST CLI Evaluator
    python run.py global            # Run the Global Cues CLI
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import nifty_options_trading.session_manager as sm

# ── Always resolve paths relative to this file ──────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
SRC_PKG   = REPO_ROOT / "nifty_options_trading"
LOGS_DIR  = REPO_ROOT / "logs"

def kill_process_on_port(port):
    """Find and kill any process listening on the given port (Windows)."""
    if os.name != 'nt':
        return # Only targeted for Windows as requested
    
    try:
        # Search for processes LISTENING on the target port
        cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
        output = subprocess.check_output(cmd, shell=True).decode()
        
        for line in output.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                # addr_port is parts[1] (e.g. 0.0.0.0:8001), pid is parts[-1]
                addr_port = parts[1]
                pid = parts[-1]
                if addr_port.endswith(f":{port}"):
                    print(f"  [!] Found existing dashboard process on port {port} (PID {pid}). Cleaning up...")
                    # /F: Forcefully terminate, /T: Terminate child processes (zombies)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
    except subprocess.CalledProcessError:
        pass # No process found on that port
    except Exception as e:
        print(f"  [!] Note: Could not clean up zombie processes: {e}")

def check_setup():
    """Ensure basic requirements are met before running."""
    print(f"[run.py] Auto-Setup Check...")
    
    # 1. Ensure logs directory exists
    if not LOGS_DIR.exists():
        print(f"  [+] Creating logs/ directory...")
        LOGS_DIR.mkdir(exist_ok=True)

    # 2. Check for .env
    if not (REPO_ROOT / ".env").exists():
        print(f"  [!] WARNING: .env file not found in root!")
        if (REPO_ROOT / ".env.example").exists():
            print(f"      Action Required: Copy .env.example to .env and fill in your ICICI API keys.")
        print("-" * 50)

    # 3. Check for SecurityMaster
    today_str = datetime.now().strftime("%Y%m%d")
    txt_path = LOGS_DIR / f"FONSEScripMaster_{today_str}.txt"
    zip_path = REPO_ROOT / "SecurityMaster.zip"
    
    if not txt_path.exists() and not zip_path.exists():
        print(f"  [!] NOTICE: SecurityMaster.zip not found.")
        print(f"      No worries—the Dashboard will try to download the latest F&O Master")
        print(f"      automatically when you start analyzing live contracts.")
        print("-" * 50)

def validate_session_preflight():
    """Checks if the session is alive. If not, triggers the interactive/silent refresh."""
    print(f"[run.py] API Session Check...")
    load_dotenv(find_dotenv(), override=True)
    
    broker_type = os.getenv("BROKER_TYPE", "ICICI_BREEZE")
    if broker_type == "ICICI_BREEZE":
        api_key = os.getenv("API_KEY")
    elif broker_type == "ANGLE_ONE":
        api_key = os.getenv("ANGLE_API_KEY")
    else: # ZERODHA
        api_key = os.getenv("ZERODHA_API_KEY")
    
    if not api_key:
        print(f"  [!] Error: API Key missing for {broker_type} in .env.")
        return False
        
    if broker_type == "ICICI_BREEZE":
        api_secret = os.getenv("API_SECRET")
        session_token = os.getenv("SESSION_TOKEN")
        if not session_token:
            return trigger_refresh(api_key, broker_type)
        is_valid, error = sm.check_session_health(api_key, api_secret, session_token, broker_type)
    elif broker_type == "ANGLE_ONE":
        session_token = os.getenv("ANGLE_JWT_TOKEN")
        refresh_token = os.getenv("ANGLE_REFRESH_TOKEN")
        if not session_token:
            return trigger_refresh(api_key, broker_type)
        is_valid, error = sm.check_session_health(api_key, None, session_token, broker_type, refresh_token=refresh_token)
    else: # ZERODHA
        session_token = os.getenv("ZERODHA_ACCESS_TOKEN")
        if not session_token:
            return trigger_refresh(api_key, broker_type)
        is_valid, error = sm.check_session_health(api_key, None, session_token, broker_type)
    
    if is_valid:
        print(f"  [+] {broker_type} session is valid.")
        return True
    
    print(f"  [!] Session expired/invalid ({error}). Refreshing...")
    return trigger_refresh(api_key, broker_type)

def trigger_refresh(api_key, broker_type="ICICI_BREEZE"):
    """Triggers the appropriate login flow."""
    if broker_type == "ICICI_BREEZE":
        new_token = sm.capture_session_token(api_key)
        if new_token:
            return sm.update_env_token(new_token)
    elif broker_type == "ANGLE_ONE":
        client_code = os.getenv("ANGLE_CLIENT_CODE")
        password = os.getenv("ANGLE_PASSWORD")
        totp_secret = os.getenv("ANGLE_TOTP_SECRET")
        
        if not all([client_code, password, totp_secret]):
            print("  [!] Error: Angle One credentials missing in .env (CLIENT_CODE, PASSWORD, TOTP_SECRET).")
            return False
            
        print(f"  [i] Performing silent TOTP login for {client_code}...")
        jwt, refresh = sm.login_smartapi(api_key, client_code, password, totp_secret)
        if jwt:
            sm.set_key(str(sm.ENV_PATH), "ANGLE_JWT_TOKEN", jwt)
            sm.set_key(str(sm.ENV_PATH), "ANGLE_REFRESH_TOKEN", refresh)
            print("  [+] Successfully updated .env with Angle One tokens.")
            return True
    elif broker_type == "ZERODHA":
        api_secret = os.getenv("ZERODHA_API_SECRET")
        if not api_secret:
            print("  [!] Error: ZERODHA_API_SECRET missing in .env.")
            return False
        
        request_token = sm.capture_kite_token(api_key)
        if request_token:
            print(f"  [i] Exchanging request token for access token...")
            from nifty_options_trading.safe_kite import SafeKite
            try:
                broker = SafeKite(api_key=api_key)
                data = broker.generate_session(api_secret, request_token)
                access_token = data["access_token"]
                sm.set_key(str(sm.ENV_PATH), "ZERODHA_ACCESS_TOKEN", access_token)
                print("  [+] Successfully updated .env with Zerodha access token.")
                return True
            except Exception as e:
                print(f"  [!] Zerodha Token Exchange Failed: {e}")
                
    return False

def main():
    parser = argparse.ArgumentParser(description="Nifty Options Trading Suite v2.0 Launcher")
    
    # Using subparsers for different modes
    subparsers = parser.add_subparsers(dest="mode", help="Execution mode")
    
    # 1. Dash subparser
    dash_p = subparsers.add_parser("dash", help="Start the FastAPI Web Dashboard")
    dash_p.add_argument("--port", type=int, default=8001, help="Port to bind (default: 8001)")
    dash_p.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    dash_p.add_argument("--no-reload", action="store_true", help="Disable file watching")

    # 2. BTST subparser
    btst_p = subparsers.add_parser("btst", help="Run the BTST CLI Evaluator")
    btst_p.add_argument("contract", type=str, help='Contract string, e.g. "NIFTY 16 Apr 23900 CE"')

    # 3. Global subparser
    subparsers.add_parser("global", help="Run the Global Cues CLI tool")

    # Handle default mode (dash) if no subcommand provided
    if len(sys.argv) == 1:
        args = parser.parse_args(["dash"])
    else:
        args = parser.parse_args()

    check_setup()
    
    # Pre-flight session check for trading modes
    if args.mode in ["dash", "btst", "global"]:
        if not validate_session_preflight():
            print("[run.py] Critical: Could not establish a valid session. Aborting.")
            sys.exit(1)

    # Ensure PYTHONPATH includes the repo root so every subprocess can import the package
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    repo_str    = str(REPO_ROOT)
    if repo_str not in existing_pp.split(os.pathsep):
        env["PYTHONPATH"] = repo_str + (os.pathsep + existing_pp if existing_pp else "")

    if args.mode == "dash":
        # Cleanup any previous instances to avoid "Address already in use"
        kill_process_on_port(args.port)

        cmd = [
            sys.executable, "-m", "uvicorn", "nifty_options_trading.app:app",
            "--host", args.host, "--port", str(args.port)
        ]
        if not args.no_reload:
            cmd += ["--reload", "--reload-dir", str(SRC_PKG)]
        print(f"[run.py] Starting Dashboard on http://{args.host}:{args.port}...")
    
    elif args.mode == "btst":
        cmd = [sys.executable, "-m", "nifty_options_trading.evaluate_btst", args.contract]
        print(f"[run.py] Starting BTST Evaluator for: {args.contract}...")

    elif args.mode == "global":
        cmd = [sys.executable, "-m", "nifty_options_trading.global_cues"]
        print(f"[run.py] Starting Global Cues Monitor...")

    try:
        subprocess.run(cmd, env=env, cwd=str(REPO_ROOT))
    except KeyboardInterrupt:
        print(f"\n[run.py] Stopping {args.mode}...")

if __name__ == "__main__":
    main()
