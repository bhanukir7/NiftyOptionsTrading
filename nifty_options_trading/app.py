"""
app.py — Nifty Options Trading Suite Dashboard Server

Serves the nifty_trading_dashboard.html UI and exposes API endpoints for:
  POST /api/v3/analyze       — V3 Multi-Strike Intraday evaluator
  POST /api/btst/analyze     — BTST probabilistic evaluator
  POST /api/global/analyze   — Global Macro confluence evaluator
  POST /api/monitor/snapshot — One-shot Max Pain + Theta defense snapshot
  POST /api/risk/simulate    — Rule Engine Config simulator
  GET  /api/global/markets   — Live yfinance world market data
  GET  /api/expiries         — SecurityMaster expiry list
  GET  /api/strikes          — SecurityMaster strike list
  GET  /api/usage            — Live API usage stats

Run (recommended — handles PYTHONPATH and --reload-dir correctly):
  python run.py

Or manually from the repo root:
  python -m uvicorn nifty_options_trading.app:app --port 8001 --reload-dir nifty_options_trading

Do NOT use bare `--reload` without `--reload-dir`: on Windows the watchfiles
reloader subprocess loses sys.path and will fail to re-import.
"""

import asyncio
import json
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Robust path bootstrap (survives watchfiles reload subprocess on Windows) ──
# __file__ is always resolved relative to this source file, so Path().resolve()
# is stable even when cwd changes inside the reloader.
_THIS_FILE  = Path(__file__).resolve()
_CURR_DIR   = _THIS_FILE.parent          # …/nifty_options_trading/
_PARENT_DIR = _CURR_DIR.parent           # …/NiftyOptionsTrading/
for _p in (_PARENT_DIR, _CURR_DIR):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

# Convenience aliases used throughout the module
current_dir = _CURR_DIR
parent_dir  = _PARENT_DIR

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=parent_dir / ".env")
except ImportError:
    pass

# ── Internal imports ──────────────────────────────────────────────────────────
from nifty_options_trading.broker_interface import BaseBroker
from nifty_options_trading.safe_breeze import SafeBreeze
from nifty_options_trading.safe_smartapi import SafeSmartAPI
from nifty_options_trading.safe_kite import SafeKite
from nifty_options_trading.options_engine import (
    get_option_chain, get_dynamic_lot_size, get_expiries, get_strikes,
)
from nifty_options_trading.max_pain import calculate_max_pain
from nifty_options_trading.theta_defense import calculate_dte, evaluate_theta_risk
from nifty_options_trading.rule_engine import (
    Config, StateManager, can_trade, validate_entry, calculate_position_size,
    determine_bias, can_take_new_trade_time,
)
from nifty_options_trading.global_cues import (
    fetch_world_markets, derive_btst_cues
)
from nifty_options_trading.trading_engine import AutonomousEngine
from nifty_options_trading.trade_analyzer import parse_fno_trade_book
from nifty_options_trading.evaluate_daytrading import (
    analyze_daytrading_signals, generate_daytrading_verdict
)
from nifty_options_trading.strict_validator import validate_strict_signal
from nifty_options_trading.morning_strategy import morning_trade_panel

# ── Read env once ─────────────────────────────────────────────────────────────
API_KEY       = os.getenv("API_KEY", "")
API_SECRET    = os.getenv("API_SECRET", "")
SESSION_TOKEN = os.getenv("SESSION_TOKEN", "")
BROKER_TYPE   = os.getenv("BROKER_TYPE", "ICICI_BREEZE")
AVAILABLE_FUNDS = float(os.getenv("AVAILABLE_FUNDS", "50000"))
STOCK_CODES_STR = os.getenv("STOCK_CODES", "NIFTY,CNXBAN,VEDLIM,MAZDOC,RELIND,COCSHI")
STOCK_CODES     = [s.strip().upper() for s in STOCK_CODES_STR.split(",") if s.strip()]
API_USAGE_PATH = parent_dir / "logs" / "api_usage.json"

app = FastAPI(title="Nifty Options Trading Suite", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_executor = ThreadPoolExecutor(max_workers=4)
_engine: Optional[AutonomousEngine] = None
_broker_instance: Optional[BaseBroker] = None

# ── HTML Dashboard ────────────────────────────────────────────────────────────
DASHBOARD_PATH = current_dir / "nifty_trading_dashboard.html"

@app.get("/", response_class=HTMLResponse)
async def index():
    return DASHBOARD_PATH.read_text(encoding="utf-8")


class EngineModeRequest(BaseModel):
    paper_trade: bool


# ── UTILS ────────────────────────────────────────────────────────────────────
def clean_json_data(o):
    """Recursively replace NaN/Inf with 0 for JSON serialization."""
    import math
    if isinstance(o, dict):
        return {k: clean_json_data(v) for k, v in o.items()}
    elif isinstance(o, (list, tuple)):
        return [clean_json_data(x) for x in o]
    elif isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return 0.0
        return o
    return o


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global _engine, _broker_instance
    print(f"[app.py] Initializing {BROKER_TYPE} dashboard services...")
    try:
        if BROKER_TYPE == "ICICI_BREEZE":
            if not API_KEY or not SESSION_TOKEN:
                print("  [!] Skip engine startup: API_KEY or SESSION_TOKEN missing")
                return
            _broker_instance = SafeBreeze(api_key=API_KEY)
            _broker_instance.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
        elif BROKER_TYPE == "ANGLE_ONE":
            api_key = os.getenv("ANGLE_API_KEY")
            jwt = os.getenv("ANGLE_JWT_TOKEN")
            if not api_key or not jwt:
                print("  [!] Skip engine startup: ANGLE_API_KEY or ANGLE_JWT_TOKEN missing")
                return
            _broker_instance = SafeSmartAPI(api_key=api_key)
            _broker_instance.smart.setAccessToken(jwt)
        elif BROKER_TYPE == "ZERODHA":
            api_key = os.getenv("ZERODHA_API_KEY")
            access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
            if not api_key or not access_token:
                print("  [!] Skip engine startup: ZERODHA_API_KEY or ZERODHA_ACCESS_TOKEN missing")
                return
            _broker_instance = SafeKite(api_key=api_key)
            _broker_instance.kite.set_access_token(access_token)
        
        _engine = AutonomousEngine(_broker_instance, stock_codes=STOCK_CODES)
        # Pre-warm Security Master
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, lambda: _broker_instance.get_expiries("NIFTY"))
            print(f"  [+] Trading Engine ({BROKER_TYPE}) and Security Master initialized.")
        except Exception as se:
            print(f"  [!] Security Master warning: {se}")
            
    except Exception as e:
        error_msg = str(e)
        print(f"  [!] ENGINE STARTUP FAILED: {error_msg}")
        
        if "session" in error_msg.lower() or "expired" in error_msg.lower():
            print("  [!] CAUSE: API Session is expired or invalid.")
            print("  [i] ACTION: Please stop the dashboard (Ctrl+C) and run 'python run.py dash' again.")
            print("      The launcher will automatically trigger an interactive login.")
        else:
            print(f"  [i] Unexpected error: {error_msg}")
            
        print("  [i] Dashboard UI will still be accessible (Trade Journal, etc.)")

@app.on_event("shutdown")
def shutdown_event():
    if _engine:
        try:
            _engine.stop()
        except Exception as e:
            print(f"[app.py] Warning: Error during engine shutdown: {e}")


# ── Helper: get authenticated Breeze instance ─────────────────────────────────
def _get_breeze() -> BaseBroker:
    global _broker_instance
    if _broker_instance:
        return _broker_instance
        
    if BROKER_TYPE == "ICICI_BREEZE":
        if not API_KEY: raise HTTPException(status_code=400, detail="API_KEY missing")
        _broker_instance = SafeBreeze(api_key=API_KEY)
        _broker_instance.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    elif BROKER_TYPE == "ANGLE_ONE":
        api_key = os.getenv("ANGLE_API_KEY")
        jwt = os.getenv("ANGLE_JWT_TOKEN")
        if not api_key: raise HTTPException(status_code=400, detail="ANGLE_API_KEY missing")
        _broker_instance = SafeSmartAPI(api_key=api_key)
        _broker_instance.smart.setAccessToken(jwt)
    elif BROKER_TYPE == "ZERODHA":
        api_key = os.getenv("ZERODHA_API_KEY")
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
        if not api_key: raise HTTPException(status_code=400, detail="ZERODHA_API_KEY missing")
        _broker_instance = SafeKite(api_key=api_key)
        _broker_instance.kite.set_access_token(access_token)
        
    return _broker_instance


# ══════════════════════════════════════════════════════════════════════════════
#  GET /api/expiries & /api/strikes  — Security Master proxies
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/expiries")
async def api_expiries(symbol: str = "NIFTY", option_type: str = "CE"):
    broker = _get_breeze() # generic broker
    loop = asyncio.get_event_loop()
    dates = await loop.run_in_executor(
        _executor, lambda: broker.get_expiries(symbol.upper())
    )
    return JSONResponse({"expiries": [str(d) for d in dates]})


@app.get("/api/strikes")
async def api_strikes(symbol: str = "NIFTY", expiry: str = "", option_type: str = "CE"):
    if not expiry:
        return JSONResponse({"strikes": []})
    broker = _get_breeze()
    try:
        # Normalize expiry if needed
        pass 
    except ValueError:
        return JSONResponse({"strikes": []})
    loop = asyncio.get_event_loop()
    strikes = await loop.run_in_executor(
        _executor, lambda: broker.get_strikes(symbol.upper(), expiry)
    )
    return JSONResponse({"strikes": [float(s) for s in strikes]})
 
@app.get("/api/positions")
async def api_positions():
    broker = _get_breeze()
    loop = asyncio.get_event_loop()
    try:
        positions = await loop.run_in_executor(
            _executor, lambda: broker.get_positions()
        )
        return JSONResponse({"positions": positions})
    except Exception as e:
        return JSONResponse({"positions": [], "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
#  Helper: Get Exchange for Symbol
# ══════════════════════════════════════════════════════════════════════════════

def _get_exchange(symbol: str) -> str:
    s = symbol.upper()
    # Explicitly map known BSE index symbols
    if s in ["BSESEN", "SENSEX", "BANKEX", "BSESN", "BSEX", "SENSEX50"]:
        return "BSE"
    return "NSE"


def _get_cash_symbol(symbol: str) -> str:
    s = symbol.upper()
    # Map friendly names to ICICI Breeze cash symbols
    mapping = {
        "BSESEN": "BSESN",
        "SENSEX": "BSESN",
        "BANKEX": "BSEX",
        "SENSEX50": "SNX50"
    }
    return mapping.get(s, s)


# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  GET /api/global/markets  — Live yfinance world market snapshot
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/global/markets")
async def global_markets():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, fetch_world_markets)
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/v3/analyze  — V3 Multi-Strike Intraday Evaluator
# ══════════════════════════════════════════════════════════════════════════════

class V3Request(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""           # YYYY-MM-DD
    option_type: str = "CE"
    capital: float = 50_000.0


def _run_v3(req: V3Request) -> dict:
    import numpy as np
    from ta.trend import MACD
    from ta.volatility import AverageTrueRange, BollingerBands
    from nifty_options_trading.evaluate_contract_V3 import (
        fetch_multiday_data, analyze_advanced_indicators, generate_verdict
    )

    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    # 1. Fetch 5-min spot data
    exchange = _get_exchange(stock_code)
    cash_sym = _get_cash_symbol(stock_code)
    print(f"[DEBUG] Fetching 5m data for {cash_sym} on {exchange}...")
    try:
        spot_df = fetch_multiday_data(breeze, cash_sym, exchange, "5minute", days_back=7)
    except Exception as e:
        print(f"[ERROR] V3 spot fetch failed: {e}")
        spot_df = pd.DataFrame()

    if spot_df.empty:
        raise HTTPException(
            status_code=500, 
            detail=f"Spot data unavailable for {cash_sym} ({exchange}). Please verify API session or try during market hours."
        )

    signal_data = analyze_advanced_indicators(spot_df)
    verdict = generate_verdict(signal_data, req.option_type.upper())

    # 2. Fetch option chain
    chain_df = get_option_chain(breeze, stock_code, req.expiry)
    strikes_data = []
    spot_price = signal_data.get("close", 0)
    lot_size = get_dynamic_lot_size(stock_code)

    if chain_df is not None and not chain_df.empty and spot_price > 0:
        opt_type_full = "CALL" if req.option_type.upper() == "CE" else "PUT"
        chain_filtered = chain_df[chain_df["right"].str.upper().isin([opt_type_full, req.option_type.upper()])].copy()

        if not chain_filtered.empty:
            chain_filtered["strike_price"] = chain_filtered["strike_price"].astype(float)
            atm_diff = (chain_filtered["strike_price"] - spot_price).abs()
            atm_idx = atm_diff.idxmin()
            atm_strike = chain_filtered.loc[atm_idx, "strike_price"]

            unique_strikes = sorted(chain_filtered["strike_price"].unique())
            try:
                atm_pos = unique_strikes.index(atm_strike)
                start_pos = max(0, atm_pos - 4)
                end_pos = min(len(unique_strikes), atm_pos + 5)
                selected_strikes = unique_strikes[start_pos:end_pos]
            except ValueError:
                selected_strikes = []

            target_df = chain_filtered[chain_filtered["strike_price"].isin(selected_strikes)].copy()
            target_df = target_df.sort_values("strike_price")

            for _, row in target_df.iterrows():
                strike = float(row["strike_price"])
                ltp = float(row.get("last_traded_price", 0) or 0)
                lot_cost = ltp * lot_size if ltp > 0 else 0
                num_lots = int(req.capital / lot_cost) if lot_cost > 0 else 0
                tag = "ATM" if abs(strike - atm_strike) < 1 else ("ITM" if (req.option_type == "CE" and strike < atm_strike) or (req.option_type == "PE" and strike > atm_strike) else "OTM")
                strikes_data.append({
                    "strike": strike,
                    "ltp": round(ltp, 2),
                    "tag": tag,
                    "lot_cost": round(lot_cost, 2),
                    "num_lots": num_lots,
                    "target1": round(ltp * 1.05, 2),
                    "target2": round(ltp * 1.10, 2),
                    "sl": round(ltp * 0.97, 2),
                })

    breeze.log_api_usage()
    return {
        "symbol": stock_code,
        "spot": round(spot_price, 2),
        "expiry": req.expiry,
        "option_type": req.option_type.upper(),
        "signal": signal_data.get("signal", "HOLD"),
        "reason": signal_data.get("reason", ""),
        "verdict": verdict,
        "indicators": {
            "macd": round(float(signal_data.get("macd", 0) or 0), 4),
            "macd_hist": round(float(signal_data.get("macd_hist", 0) or 0), 4),
            "atr": round(float(signal_data.get("atr", 0) or 0), 2),
            "bb_low": round(float(signal_data.get("bb_low", 0) or 0), 2),
            "bb_mid": round(float(signal_data.get("bb_mid", 0) or 0), 2),
            "bb_high": round(float(signal_data.get("bb_high", 0) or 0), 2),
            "chop": round(float(signal_data.get("chop", 50) or 50), 2),
        },
        "lot_size": lot_size,
        "strikes": strikes_data,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v3/analyze")
async def v3_analyze(req: V3Request):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_v3(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/daytrading/analyze  — Day Trading Signals Evaluator (Pine Script Port)
# ══════════════════════════════════════════════════════════════════════════════

class DayTradingRequest(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""
    option_type: str = "CE"
    capital: float = 50_000.0


def _run_daytrading(req: DayTradingRequest) -> dict:
    from nifty_options_trading.evaluate_contract_V3 import fetch_multiday_data
    
    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    # 1. Fetch 5-min spot data (enough for EMA/RSI/MACD burn-in)
    exchange = _get_exchange(stock_code)
    cash_sym = _get_cash_symbol(stock_code)
    print(f"[DEBUG] Fetching 5m data for {cash_sym} on {exchange}...")
    spot_df = fetch_multiday_data(breeze, cash_sym, exchange, "5minute", days_back=10)
    if spot_df.empty:
        raise HTTPException(status_code=500, detail="Could not fetch spot data. Check API or trading hours.")

    analysis = analyze_daytrading_signals(spot_df)
    verdict = generate_daytrading_verdict(analysis, req.option_type.upper())

    # 2. Fetch option chain for strike evaluation
    chain_df = get_option_chain(breeze, stock_code, req.expiry)
    strikes_data = []
    spot_price = analysis.get("close", 0)
    lot_size = get_dynamic_lot_size(stock_code)

    if chain_df is not None and not chain_df.empty and spot_price > 0:
        opt_type_full = "CALL" if req.option_type.upper() == "CE" else "PUT"
        chain_filtered = chain_df[chain_df["right"].str.upper().isin([opt_type_full, req.option_type.upper()])].copy()

        if not chain_filtered.empty:
            chain_filtered["strike_price"] = chain_filtered["strike_price"].astype(float)
            # Center around current spot
            atm_diff = (chain_filtered["strike_price"] - spot_price).abs()
            atm_idx = atm_diff.idxmin()
            atm_strike = chain_filtered.loc[atm_idx, "strike_price"]

            unique_strikes = sorted(chain_filtered["strike_price"].unique())
            try:
                atm_pos = unique_strikes.index(atm_strike)
                start_pos = max(0, atm_pos - 4)
                end_pos = min(len(unique_strikes), atm_pos + 5)
                selected_strikes = unique_strikes[start_pos:end_pos]
            except ValueError:
                selected_strikes = []

            target_df = chain_filtered[chain_filtered["strike_price"].isin(selected_strikes)].copy()
            target_df = target_df.sort_values("strike_price")

            # Signal conviction multipliers for targets
            m1, m2, s1 = 1.05, 1.10, 0.97
            if analysis["signal"] in ["BUY_CALL", "BUY_PUT"]:
                # Stronger signal = slightly more aggressive targets
                m1, m2, s1 = 1.10, 1.20, 0.95

            for _, row in target_df.iterrows():
                strike = float(row["strike_price"])
                ltp = float(row.get("last_traded_price", 0) or 0)
                lot_cost = ltp * lot_size if ltp > 0 else 0
                num_lots = int(req.capital / lot_cost) if lot_cost > 0 else 0
                tag = "ATM" if abs(strike - atm_strike) < 1 else ("ITM" if (req.option_type == "CE" and strike < atm_strike) or (req.option_type == "PE" and strike > atm_strike) else "OTM")
                
                strikes_data.append({
                    "strike": strike,
                    "ltp": round(ltp, 2),
                    "tag": tag,
                    "lot_cost": round(lot_cost, 2),
                    "num_lots": num_lots,
                    "target1": round(ltp * m1, 2),
                    "target2": round(ltp * m2, 2),
                    "sl": round(ltp * s1, 2),
                })

    breeze.log_api_usage()
    res = {
        "symbol": stock_code,
        "spot": round(spot_price, 2),
        "expiry": req.expiry,
        "option_type": req.option_type.upper(),
        "signal": analysis.get("signal", "HOLD"),
        "reason": analysis.get("reason", ""),
        "trend": analysis.get("trend", "NONE"),
        "verdict": verdict,
        "indicators": analysis.get("indicators", {}),
        "lot_size": lot_size,
        "strikes": strikes_data,
        "timestamp": datetime.now().isoformat(),
    }
    return clean_json_data(res)


@app.post("/api/daytrading/analyze")
async def daytrading_analyze(req: DayTradingRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_daytrading(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/btst/analyze  — BTST Probabilistic Evaluator
# ══════════════════════════════════════════════════════════════════════════════


class BTSTRequest(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""
    strike: float = 22000.0
    option_type: str = "CE"
    capital: float = 50_000.0


def _run_btst(req: BTSTRequest) -> dict:
    from nifty_options_trading.evaluate_btst import (
        fetch_multiday_data, analyze_advanced_indicators,
        analyze_oi, estimate_iv, compute_btst_score, generate_score_verdict
    )

    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    # ── 1. Fetch live world markets and derive cues ───────────────────────────
    world    = fetch_world_markets()
    markets  = world.get("markets", [])
    cue_data = derive_btst_cues(markets)

    gift_nifty    = cue_data["gift_nifty"]
    us_market     = cue_data["us_market"]
    europe_market = cue_data["europe_market"]
    asia_market   = cue_data["asia_market"]

    # ── 2. Local 1-day technicals ─────────────────────────────────────────────
    exchange = _get_exchange(stock_code)
    cash_sym = _get_cash_symbol(stock_code)
    print(f"[DEBUG] Fetching 1D data for {cash_sym} on {exchange}...")
    try:
        spot_df = fetch_multiday_data(breeze, cash_sym, exchange, "1day", days_back=90)
    except Exception as e:
        print(f"[ERROR] fetch_multiday_data crashed: {e}")
        spot_df = pd.DataFrame()

    if spot_df.empty:
        print(f"[ERROR] Historical data fetch failed for {cash_sym} ({exchange}). No recovery possible.")
        raise HTTPException(
            status_code=500, 
            detail=f"Historical data unavailable for {cash_sym} ({exchange}). Breeze API is unresponsive and fallback data was not found."
        )

    signal_data = analyze_advanced_indicators(spot_df)
    spot_price  = signal_data.get("close", 0.0)

    # ── 3. Options chain — OI & IV ────────────────────────────────────────────
    chain_df = get_option_chain(breeze, stock_code, req.expiry)
    oi_data  = analyze_oi(chain_df, spot_price)
    iv_data  = estimate_iv(spot_df)

    global_data = {
        "gift_nifty":    gift_nifty,
        "us_market":     us_market,
        "europe_market": europe_market,
        "asia_market":   asia_market,
        "vix":           cue_data.get("vix", 0.0),
        "derived_cues":  cue_data.get("derived_cues", {}),
    }

    is_put = (req.option_type == "PE")
    score   = compute_btst_score(signal_data, oi_data, iv_data, global_data, is_put=is_put)
    verdict = generate_score_verdict(score)

    # ── 4. Contract LTP ───────────────────────────────────────────────────────
    opt_ltp, lot_size, num_lots = 0.0, get_dynamic_lot_size(stock_code), 0
    if chain_df is not None and not chain_df.empty:
        opt_type_full = "CALL" if req.option_type.upper() == "CE" else "PUT"
        target_row = chain_df[
            (chain_df["strike_price"] == float(req.strike)) &
            (chain_df["right"].str.upper().isin([opt_type_full, req.option_type.upper()]))
        ]
        if not target_row.empty:
            opt_ltp = float(target_row.iloc[0]["last_traded_price"] or 0)
            if opt_ltp > 0:
                num_lots = int(req.capital / (opt_ltp * lot_size))

    # ── 5. Sub-score breakdown ────────────────────────────────────────────────
    is_put = (req.option_type == "PE")
    cs     = signal_data.get("close_strength", 50)
    pcr    = oi_data.get("pcr", 1.0)
    iv_p   = iv_data.get("iv_percentile", 50)

    if is_put:
        sub_price_action = min(35, int(
            (10 if signal_data.get("macd_bearish") else 0) +
            (10 if signal_data.get("below_bb_mid") else 0) +
            int(((100 - cs) / 100.0) * 15)
        ))
        # Global cues scoring for Puts (Inverse)
        gn_pts = {"UP": -10, "DOWN": 15, "FLAT": 0}[gift_nifty]
        us_pts = {"UP": -5,  "DOWN": 8,  "FLAT": 0}[us_market]
        eu_pts = {"UP": -3,  "DOWN": 5,  "FLAT": 0}[europe_market]
        as_pts = {"UP": -2,  "DOWN": 2,  "FLAT": 0}[asia_market]
    else:
        sub_price_action = min(35, int(
            (10 if signal_data.get("macd_bullish") else 0) +
            (10 if signal_data.get("above_bb_mid") else 0) +
            int((cs / 100.0) * 15)
        ))
        # Global cues scoring for Calls (Standard)
        gn_pts = {"UP": 15, "DOWN": -10, "FLAT": 0}[gift_nifty]
        us_pts = {"UP": 8,  "DOWN": -5,  "FLAT": 0}[us_market]
        eu_pts = {"UP": 5,  "DOWN": -3,  "FLAT": 0}[europe_market]
        as_pts = {"UP": 2,  "DOWN": -2,  "FLAT": 0}[asia_market]

    sub_oi = min(25, (15 if oi_data.get("support_below") else 0) + (10 if 0.8 <= pcr <= 1.2 else 0))
    sub_iv = 10 if iv_p < 60 else (-5 if iv_p > 80 else 0)

    # ── 6. Final Score (Sum of sub-scores) ───────────────────────────────────
    # We sum the breakdown components to ensure the total matches the visualization
    total_calculated_score = sub_price_action + sub_oi + sub_iv + gn_pts + us_pts + eu_pts + as_pts
    score = min(max(total_calculated_score, 0), 100)
    
    # --- BTST GUARDRAIL ---
    # Global cues alignment: final_signal should be UP for calls, DOWN for puts
    global_signal = cue_data.get("final_signal", "FLAT")
    cues_aligned = (not is_put and global_signal == "UP") or (is_put and global_signal == "DOWN")
    
    if score < 70 or not cues_aligned:
        verdict = "BLOCK CARRY FORWARD (Low score or global cues mismatch)"
    else:
        verdict = generate_score_verdict(score)

    # ── 7. Group markets by region for the UI ────────────────────────────────
    up_count   = sum(1 for m in markets if m["direction"] == "up")
    down_count = sum(1 for m in markets if m["direction"] == "down")

    breeze.log_api_usage()
    return {
        "symbol":       stock_code,
        "strike":       req.strike,
        "option_type":  req.option_type.upper(),
        "expiry":       req.expiry,
        "spot":         round(spot_price, 2),
        "opt_ltp":      opt_ltp,
        "lot_size":     lot_size,
        "num_lots":     num_lots,
        "targets": {
            "t1": round(opt_ltp * 1.15, 2),
            "t2": round(opt_ltp * 1.30, 2),
            "sl": round(opt_ltp * 0.90, 2),
        } if opt_ltp > 0 else {},
        "score":   score,
        "verdict": verdict,
        "sub_scores": {
            "price_action": sub_price_action,
            "oi_pcr":       sub_oi,
            "iv":           sub_iv,
            "gift_nifty":   gn_pts,
            "us_market":    us_pts,
            "europe":       eu_pts,
            "asia":         as_pts,
        },
        "indicators": {
            "close_strength": cs,
            "macd_bullish":   bool(signal_data.get("macd_bullish")),
            "above_bb_mid":   bool(signal_data.get("above_bb_mid")),
            "pcr":            round(pcr, 3),
            "support_below":  bool(oi_data.get("support_below")),
            "iv_percentile":  iv_p,
        },
        "global_cues":   global_data,
        "derived_cues":  cue_data["derived_cues"],
        "markets":       markets,
        "up_count":      up_count,
        "down_count":    down_count,
        "timestamp":     datetime.now().isoformat(),
    }


@app.post("/api/btst/analyze")
async def btst_analyze(req: BTSTRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_btst(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/global/analyze  — Global Macro Confluence Evaluator
# ══════════════════════════════════════════════════════════════════════════════

class GlobalRequest(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""
    strike: float = 22000.0
    option_type: str = "CE"
    capital: float = 50_000.0


def _run_global(req: GlobalRequest) -> dict:
    from nifty_options_trading.evaluate_global import (
        fetch_multiday_data, analyze_advanced_indicators, generate_macro_verdict
    )

    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    # 1. Live global sentiment via yfinance (extended)
    world = fetch_world_markets()
    markets = world.get("markets", [])
    up_count   = sum(1 for m in markets if m["direction"] == "up")
    down_count = sum(1 for m in markets if m["direction"] == "down")
    is_bullish = up_count >= len(markets) / 2
    global_data = {
        "is_bullish": is_bullish,
        "metrics": {m["name"]: m["change_pct"] for m in markets},
        "up_count": up_count,
        "total": len(markets),
        "markets": markets,
    }

    # 2. Local 1-Day technicals
    spot_df = fetch_multiday_data(breeze, stock_code, "NSE", "1day", days_back=90)
    if spot_df.empty:
        raise HTTPException(status_code=500, detail="Could not fetch 1D historic data.")

    signal_data = analyze_advanced_indicators(spot_df)
    spot_price  = signal_data.get("close", 0.0)

    # 3. Contract LTP
    chain_df = get_option_chain(breeze, stock_code, req.expiry)
    opt_ltp, lot_size, num_lots = 0.0, get_dynamic_lot_size(stock_code), 0
    if chain_df is not None and not chain_df.empty:
        opt_type_full = "CALL" if req.option_type.upper() == "CE" else "PUT"
        target_row = chain_df[
            (chain_df["strike_price"] == float(req.strike)) &
            (chain_df["right"].str.upper().isin([opt_type_full, req.option_type.upper()]))
        ]
        if not target_row.empty:
            opt_ltp = float(target_row.iloc[0]["last_traded_price"] or 0)
            if opt_ltp > 0:
                num_lots = int(req.capital / (opt_ltp * lot_size))

    verdict = generate_macro_verdict(signal_data.get("signal", "HOLD"), global_data, req.option_type.upper())

    breeze.log_api_usage()
    return {
        "symbol":       stock_code,
        "spot":         round(spot_price, 2),
        "opt_ltp":      opt_ltp,
        "lot_size":     lot_size,
        "num_lots":     num_lots,
        "targets": {
            "t1": round(opt_ltp * 1.15, 2),
            "t2": round(opt_ltp * 1.30, 2),
            "sl": round(opt_ltp * 0.90, 2),
        } if opt_ltp > 0 else {},
        "verdict":      verdict,
        "global_state": "BULLISH" if is_bullish else "BEARISH",
        "up_count":     up_count,
        "down_count":   down_count,
        "total_indices": len(markets),
        "markets":      markets,
        "local": {
            "signal":         signal_data.get("signal", "HOLD"),
            "reason":         signal_data.get("reason", ""),
            "close":          round(float(signal_data.get("close", 0) or 0), 2),
            "close_strength": signal_data.get("close_strength", 50),
            "macd_hist":      round(float(signal_data.get("macd_hist", 0) or 0), 4),
            "bb_mid":         round(float(signal_data.get("bb_mid", 0) or 0), 2),
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/global/analyze")
async def global_analyze(req: GlobalRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_global(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/morning/analyze  — Morning Trade Panel Evaluator
# ══════════════════════════════════════════════════════════════════════════════

class MorningRequest(BaseModel):
    symbol: str = "NIFTY"
    capital: float = 50_000.0

def _run_morning(req: MorningRequest) -> dict:
    from nifty_options_trading.evaluate_contract_V3 import fetch_multiday_data
    from nifty_options_trading.alerts import send_alert
    
    breeze = _get_breeze()
    
    # 1. Fetch Data for Nifty, Bank Nifty, and Sensex
    # Interval 5min for stability, 1min also possible but 5min is standard for ORB
    try:
        nifty_df = fetch_multiday_data(breeze, "NIFTY", "NSE", "5minute", days_back=2)
    except Exception: nifty_df = pd.DataFrame()
    
    try:
        bn_df = fetch_multiday_data(breeze, "CNXBAN", "NSE", "5minute", days_back=2)
    except Exception: bn_df = pd.DataFrame()
    
    try:
        sx_df = fetch_multiday_data(breeze, "BSESN", "BSE", "5minute", days_back=2)
    except Exception: sx_df = pd.DataFrame()
    
    if nifty_df.empty:
        raise HTTPException(status_code=500, detail="Primary Nifty data unavailable. Verify Breeze session.")
        
    # 2. Run Strategy Logic
    result = morning_trade_panel(nifty_df, bn_df, sx_df)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    # 3. Strike Logic (Refine Strike for UI)
    spot_price = nifty_df["close"].iloc[-1]
    lot_size = get_dynamic_lot_size("NIFTY")
    
    if result["signal"] != "NO TRADE":
        # Determine Strike: ATM or 1 ITM
        # Nifty strike step is 50
        strike_step = 50
        atm_strike = round(spot_price / strike_step) * strike_step
        
        if result["confidence"] > 85:
            # Strong breakout -> 1 ITM
            if result["signal"] == "BUY CE":
                chosen_strike = atm_strike - strike_step
            else:
                chosen_strike = atm_strike + strike_step
        else:
            chosen_strike = atm_strike
            
        result["trade"]["strike"] = f"NIFTY {int(chosen_strike)} {result['signal'].split()[-1]}"
        
        # 4. Telegram Alert Hook (only if signal is new/changed - would need state, but for now we just push)
        # In a real app, we'd check against a state manager.
        alert_msg = (f"🌅 **MORNING TRADE SIGNAL**\n"
                     f"Signal: {result['signal']}\n"
                     f"Confidence: {result['confidence']}%\n"
                     f"Entry: {result['trade']['entry_type']}\n"
                     f"Strike: {result['trade']['strike']}\n"
                     f"SL: {result['trade']['sl']}\n"
                     f"Reason: {result['reasons'][0] if result['reasons'] else 'N/A'}")
        
        # We only send if it's a valid buy/sell (avoid spamming NO TRADE)
        # send_alert(alert_msg) 
        # Note: Disabled by default to avoid spam during testing, but the hook is here.
        
    breeze.log_api_usage()
    return clean_json_data(result)

@app.post("/api/morning/analyze")
async def morning_analyze(req: MorningRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_morning(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/monitor/snapshot  — Max Pain + Theta Defense one-shot
# ══════════════════════════════════════════════════════════════════════════════

class MonitorRequest(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""


def _run_monitor(req: MonitorRequest) -> dict:
    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    chain_df = get_option_chain(breeze, stock_code, req.expiry)
    if chain_df is None or chain_df.empty:
        raise HTTPException(status_code=500, detail="Failed to retrieve option chain. Check expiry date.")

    max_pain = calculate_max_pain(chain_df)
    dte      = calculate_dte(req.expiry)
    theta    = evaluate_theta_risk(dte, threshold=2)

    # Build strike-level OI summary for the mini chart
    # Safely handle optional change_in_oi column (not always present in API response)
    _has_oi_change = "change_in_oi" in chain_df.columns
    _call_cols = ["strike_price", "open_interest"] + (["change_in_oi"] if _has_oi_change else [])
    _put_cols  = ["strike_price", "open_interest"] + (["change_in_oi"] if _has_oi_change else [])
    calls = chain_df[chain_df["right"].str.upper().isin(["CALL", "CE"])][_call_cols].copy()
    puts  = chain_df[chain_df["right"].str.upper().isin(["PUT", "PE"])][_put_cols].copy()
    if _has_oi_change:
        calls.columns = ["strike", "call_oi", "call_oi_change"]
        puts.columns  = ["strike", "put_oi", "put_oi_change"]
    else:
        calls.columns = ["strike", "call_oi"]
        puts.columns  = ["strike", "put_oi"]
        calls["call_oi_change"] = 0.0
        puts["put_oi_change"]   = 0.0
    merged = pd.merge(calls, puts, on="strike", how="outer").fillna(0)
    merged = merged.sort_values("strike").reset_index(drop=True)  # reset so iloc positions are contiguous

    # Keep ±10 strikes around max-pain
    if max_pain > 0 and not merged.empty:
        diffs = (merged["strike"] - max_pain).abs()
        atm_pos = int(diffs.idxmin())  # index == iloc position after reset_index
        start   = max(0, atm_pos - 10)
        end     = min(len(merged), atm_pos + 11)
        merged  = merged.iloc[start:end]

    total_call_oi = float(chain_df[chain_df["right"].str.upper().isin(["CALL", "CE"])]["open_interest"].sum())
    total_put_oi  = float(chain_df[chain_df["right"].str.upper().isin(["PUT",  "PE"])]["open_interest"].sum())
    pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 1.0

    # AI Strategy Analysis
    from nifty_options_trading.maxpain_strategy import MaxPainStrategy
    strat = MaxPainStrategy()
    
    # Attempt to extract OI change if available in chain_df
    # Inmerged, we already merged calls and puts. We need call_oi_change and put_oi_change.
    # We should merge the change columns too if they exist.
    
    oi_data_for_strat = [
        {
            "strike": float(row["strike"]),
            "call_oi": float(row["call_oi"]),
            "put_oi": float(row["put_oi"]),
            "call_oi_change": float(row.get("call_oi_change", 0)),
            "put_oi_change": float(row.get("put_oi_change", 0))
        }
        for _, row in merged.iterrows()
    ]
    
    # 2. Fetch Actual Underlying Spot Price
    # We use 1-minute historical data to get the latest spot close price.
    spot_price = 0.0
    try:
        # Auto-correct BSESEN to BSESN for Cash spot price lookup
        spot_sym = "BSESN" if stock_code == "BSESEN" else stock_code
        hist_exch = "BSE" if spot_sym in ["BSESN", "BANKEX"] else "NSE"
        
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        start_iso = datetime.now().strftime("%Y-%m-%dT00:00:00.000Z")
        hist = breeze.get_historical_data(
            interval="1minute",
            from_date=start_iso,
            to_date=now_iso,
            stock_code=spot_sym,
            exchange_code=hist_exch,
            product_type="cash"
        )
        if hist and hist.get("Status") == 200 and hist.get("Success"):
            spot_price = float(hist["Success"][-1]["close"])
        else:
            # Fallback to chain LTP if historical data fails (less accurate)
            if not chain_df.empty:
                row0 = chain_df.iloc[0]
                spot_price = float(row0.get("last_traded_price", row0.get("ltp", 0)) or 0)
    except Exception as e:
        print(f"Error fetching spot price for monitor: {e}")
        if not chain_df.empty:
            spot_price = float(chain_df.iloc[0].get("last_traded_price", 0) or 0)

    # We use a neutral bias for the one-shot monitor unless we track it
    ai_strategy = strat.generate_signal(
        spot_price=spot_price,
        oi_chain=oi_data_for_strat,
        max_pain=float(max_pain),
        global_bias="NONE",
        dte=dte
    )

    breeze.log_api_usage()
    return {
        "symbol":         stock_code,
        "expiry":         req.expiry,
        "max_pain":       float(max_pain),
        "dte":            dte,
        "theta_defense":  bool(theta["defense_active"]),
        "theta_message":  theta["message"],
        "pcr":            float(pcr),
        "total_call_oi":  float(total_call_oi),
        "total_put_oi":   float(total_put_oi),
        "ai_strategy":    ai_strategy,
        "oi_table": [
            {
                "strike":   float(row["strike"]),
                "call_oi":  float(row["call_oi"]),
                "put_oi":   float(row["put_oi"]),
                "is_max_pain": bool(abs(float(row["strike"]) - max_pain) < 1),
            }
            for _, row in merged.iterrows()
        ],
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/monitor/snapshot")
async def monitor_snapshot(req: MonitorRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_monitor(req))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/risk/simulate  — Rule Engine Simulator
# ══════════════════════════════════════════════════════════════════════════════

class RiskSimRequest(BaseModel):
    capital: float = 50_000.0
    premium: float = 100.0
    option_type: str = "CE"
    spot: float = 22000.0
    vwap: float = 21900.0
    intraday_move_pct: float = 0.5
    # Config overrides
    max_trades_per_day: int = 5
    daily_loss_limit: float = -5000.0
    risk_per_trade_pct: float = 2.0
    sl_pct: float = 25.0
    cooldown_minutes: int = 20
    max_consecutive_losses: int = 2
    max_intraday_move_pct: float = 2.5
    # Simulated state
    trades_today: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    minutes_since_last_trade: Optional[float] = None


@app.post("/api/risk/simulate")
async def risk_simulate(req: RiskSimRequest):
    cfg = Config()
    cfg.max_trades_per_day     = req.max_trades_per_day
    cfg.daily_loss_limit       = req.daily_loss_limit
    cfg.risk_per_trade_pct     = req.risk_per_trade_pct / 100
    cfg.sl_pct                 = req.sl_pct / 100
    cfg.cooldown_minutes       = req.cooldown_minutes
    cfg.max_consecutive_losses = req.max_consecutive_losses
    cfg.max_intraday_move_pct  = req.max_intraday_move_pct

    state = StateManager()
    state.trades_today       = req.trades_today
    state.consecutive_losses = req.consecutive_losses
    state.daily_pnl          = req.daily_pnl
    if req.minutes_since_last_trade is not None:
        state.last_trade_time = datetime.now() - timedelta(minutes=req.minutes_since_last_trade)

    bias            = determine_bias(req.spot, req.vwap)
    can_trade_ok, can_trade_reason = can_trade(state, cfg)
    can_entry_ok, can_entry_reason = validate_entry(
        req.option_type.upper(), bias, req.intraday_move_pct, cfg
    )
    qty, risk_amt, sl_move = calculate_position_size(req.capital, req.premium, cfg)
    time_ok = can_take_new_trade_time()

    target  = req.premium * (1 + cfg.sl_pct * 1.5)
    sl      = req.premium - sl_move if req.option_type.upper() == "CE" else req.premium + sl_move

    return JSONResponse({
        "bias":              bias,
        "can_trade":         can_trade_ok,
        "can_trade_reason":  can_trade_reason,
        "entry_valid":       can_entry_ok,
        "entry_reason":      can_entry_reason,
        "time_ok":           time_ok,
        "overall_go":        can_trade_ok and can_entry_ok and time_ok,
        "position": {
            "qty":        qty,
            "risk_amt":   round(risk_amt, 2),
            "sl_move":    round(sl_move, 2),
            "entry":      req.premium,
            "target":     round(target, 2),
            "stop_loss":  round(sl, 2),
        },
    })


# ── Trade Analysis API ────────────────────────────────────────────────────────
@app.get("/api/trades/analysis")
async def get_trades_analysis(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """
    Scans the 'mytrades' directory for the latest F&O trade book and returns
    a summarized performance report with optional date filtering.
    """
    # Check package folder first, then fall back to root
    trades_dir = current_dir / "mytrades"
    if not trades_dir.exists():
        trades_dir = parent_dir / "mytrades"
    
    if not trades_dir.exists():
        return JSONResponse({"error": "No 'mytrades' folder found in root or package directory."}, status_code=404)
    
    csv_files = list(trades_dir.glob("*.csv"))
    if not csv_files:
        return JSONResponse({"error": "No CSV files found in 'mytrades' folder."}, status_code=404)
    
    # Get the most recently modified CSV
    latest_csv = max(csv_files, key=lambda p: p.stat().st_mtime)
    
    # Offload blocking IO to the thread pool
    report = await asyncio.get_event_loop().run_in_executor(
        _executor, parse_fno_trade_book, str(latest_csv), start_date, end_date
    )
    
    if "error" in report:
        return JSONResponse(report, status_code=500)
        
    return report


# ══════════════════════════════════════════════════════════════════════════════
#  GET /api/usage  — API Usage Stats
# ══════════════════════════════════════════════════════════════════════════════

MAX_DAILY_CALLS = 5000   # ICICI Breeze hard limit: 5000 calls/day
MAX_PER_MIN     = 100    # ICICI Breeze hard limit: 100 calls/minute

@app.get("/api/positions/greeks")
async def api_positions_greeks():
    broker = _get_breeze()
    loop = asyncio.get_event_loop()
    try:
        # 1. Get current positions
        res = await loop.run_in_executor(_executor, broker.get_positions)
        
        # 2. Enrich F&O positions with IV
        enriched = []
        for p in res:
            if p.get("segment") == "fno" and p.get("strike"):
                try:
                    greeks = await loop.run_in_executor(
                        _executor, 
                        lambda: broker.get_option_greeks(
                            p["symbol"], 
                            p["expiry"],
                            str(p["strike"]),
                            p["right"],
                            p.get("exchange", "NFO")
                        )
                    )
                    p["iv"] = greeks.get("iv", 0.15)
                except Exception as e:
                    print(f"Greek fetch failed for {p['symbol']}: {e}")
                    p["iv"] = 0.15
            enriched.append(p)
            
        return JSONResponse({"positions": enriched})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/ltp")
async def api_ltp(symbol: str = "NIFTY"):
    broker = _get_breeze()
    loop = asyncio.get_event_loop()
    try:
        # For Breeze, NIFTY is usually an index
        exchange = "NSE"
        if symbol.upper() in ["NIFTY", "CNXBAN", "NIFFIN"]:
            exchange = "NSE"
        
        ltp = await loop.run_in_executor(
            _executor, lambda: broker.get_ltp(symbol.upper(), exchange=exchange)
        )
        return JSONResponse({"symbol": symbol.upper(), "ltp": ltp})
    except Exception as e:
        return JSONResponse({"symbol": symbol.upper(), "ltp": 0, "error": str(e)})

@app.get("/api/usage")
async def api_usage():
    if API_USAGE_PATH.exists():
        try:
            data = json.loads(API_USAGE_PATH.read_text())
            calls  = int(data.get("daily_calls", 0))
            used   = min(calls, MAX_DAILY_CALLS)
            return JSONResponse({
                "daily_calls":   calls,
                "max_per_day":   MAX_DAILY_CALLS,
                "remaining":     MAX_DAILY_CALLS - used,
                "pct_used":      round(used / MAX_DAILY_CALLS * 100, 1),
                "current_day":   data.get("current_day", 0),
                "last_updated":  data.get("call_timestamps", [None])[-1],
            })
        except Exception:
            pass
    return JSONResponse({"daily_calls": 0, "max_per_day": MAX_DAILY_CALLS, "remaining": MAX_DAILY_CALLS, "pct_used": 0.0})


# ══════════════════════════════════════════════════════════════════════════════
#  Autonomous Engine Control Panel
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/engine/toggle")
async def engine_toggle():
    if not _engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")
    
    if _engine._is_running:
        _engine.stop()
        return {"status": "stopped", "message": "Engine stopped successfully."}
    else:
        _engine.start()
        return {"status": "running", "message": "Engine started successfully."}

@app.post("/api/engine/mode")
async def engine_mode(req: EngineModeRequest):
    if not _engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")
    _engine.config.paper_trade = req.paper_trade
    mode_str = "PAPER TRADE" if req.paper_trade else "LIVE (BETA)"
    _engine.log(f"Trading mode switched to: {mode_str}")
    return {"status": "success", "paper_trade": req.paper_trade}

@app.get("/api/engine/status")
async def engine_status():
    if not _engine:
        return {"is_running": False, "status": "Not Initialized"}
    
    return {
        "is_running": _engine._is_running,
        "paper_trade": _engine.config.paper_trade,
        "trades_today": _engine.state.trades_today,
        "daily_pnl": round(_engine.state.daily_pnl, 2),
        "current_bias": _engine.state.current_bias,
        "active_pos": len(_engine.state.active_positions) > 0,
        "last_signal": _engine.last_signal
    }

@app.get("/api/engine/logs")
async def engine_logs():
    if not _engine:
        return {"logs": ["Engine not initialized"]}
    return {"logs": list(_engine.logs)}

@app.get("/api/engine/advanced/signals")
async def engine_advanced_signals():
    if not _engine or not hasattr(_engine, "adv_strat"):
        return {"signals": []}
    
    signals = []
    for sig in _engine.adv_strat.signal_log:
        signals.append({
            "symbol": sig.symbol,
            "type": sig.signal_type,
            "price": round(sig.price, 2),
            "time": datetime.fromtimestamp(sig.timestamp).strftime("%H:%M:%S"),
            "metadata": sig.metadata
        })
    return {"signals": signals[::-1]} # Latest first

@app.get("/api/engine/advanced/snapshots")
async def engine_advanced_snapshots():
    if not _engine or not hasattr(_engine, "adv_strat"):
        return {"snapshots": []}
    
    snapshots = []
    for symbol in STOCK_CODES:
        snap = _engine.adv_strat.get_symbol_snapshot(symbol)
        snapshots.append(snap)
    return {"snapshots": snapshots}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/strict/analyze — Strict Intraday Signal Validator
# ══════════════════════════════════════════════════════════════════════════════

class StrictRequest(BaseModel):
    symbol: str = "NIFTY"
    expiry: str = ""
    option_type: str = "CE"
    capital: float = 50_000.0

def _run_strict_analysis(req: StrictRequest) -> dict:
    from nifty_options_trading.evaluate_contract_V3 import fetch_multiday_data
    
    breeze = _get_breeze()
    stock_code = req.symbol.upper()

    # Fetch 5-min data
    exchange = _get_exchange(stock_code)
    cash_sym = _get_cash_symbol(stock_code)
    print(f"[DEBUG] Fetching 5m data for {cash_sym} on {exchange}...")
    df = fetch_multiday_data(breeze, cash_sym, exchange, "5minute", days_back=10)
    if df.empty:
        raise HTTPException(status_code=500, detail=f"Could not fetch 5m spot data for {cash_sym} on {exchange}.")

    strict_res = validate_strict_signal(df)
    
    # Enrich with option data
    spot_price = strict_res["indicators"]["price"]
    lot_size = get_dynamic_lot_size(stock_code)
    strikes_data = []
    
    if req.expiry:
        chain_df = get_option_chain(breeze, stock_code, req.expiry)
        if chain_df is not None and not chain_df.empty:
             opt_type_full = "CALL" if req.option_type.upper() == "CE" else "PUT"
             target_df = chain_df[chain_df["right"].str.upper().isin([opt_type_full, req.option_type.upper()])].copy()
             
             if not target_df.empty:
                 target_df["strike_price"] = target_df["strike_price"].astype(float)
                 atm_diff = (target_df["strike_price"] - spot_price).abs()
                 atm_idx = atm_diff.idxmin()
                 atm_strike = target_df.loc[atm_idx, "strike_price"]
                 
                 unique_strikes = sorted(target_df["strike_price"].unique())
                 try:
                     atm_pos = unique_strikes.index(atm_strike)
                     selected_strikes = unique_strikes[max(0, atm_pos-2):min(len(unique_strikes), atm_pos+3)]
                 except: selected_strikes = []
                 
                 for _, row in target_df[target_df["strike_price"].isin(selected_strikes)].iterrows():
                     ltp = float(row.get("last_traded_price", 0) or 0)
                     strikes_data.append({
                         "strike": float(row["strike_price"]),
                         "ltp": round(ltp, 2),
                         "tag": "ATM" if abs(float(row["strike_price"]) - atm_strike) < 1 else "ITM/OTM"
                     })

    res = {
        "symbol": stock_code,
        "signal": strict_res["signal"],
        "confidence": strict_res["confidence"],
        "reasons": strict_res["reasons"],
        "indicators": strict_res["indicators"],
        "lot_size": lot_size,
        "strikes": strikes_data,
        "timestamp": datetime.now().isoformat()
    }
    return clean_json_data(res)

@app.post("/api/strict/analyze")
async def strict_analyze(req: StrictRequest):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _run_strict_analysis(req))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(result)
