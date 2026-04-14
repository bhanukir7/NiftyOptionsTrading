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
