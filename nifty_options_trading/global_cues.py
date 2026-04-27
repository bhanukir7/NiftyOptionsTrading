"""
global_cues.py — Shared Global Market Analysis Logic
Provides live fetching of global indices via yfinance and derives sentiment cues.
"""

from datetime import datetime
import time
import math
from typing import Literal, Optional
import pandas as pd
from nifty_options_trading.groww_scraper import fetch_groww_indices

# Global cache for yfinance to reduce pings
_GLOBAL_MARKETS_CACHE = None
_GLOBAL_MARKETS_TIMESTAMP = 0
_GLOBAL_MARKETS_TTL = 300  # 5 minutes

# Market mapping for Dashboard & BTST
WORLD_INDICES = {
    # India Core
    "NIFTY 50":       "^NSEI",
    "BANK NIFTY":     "^NSEBANK",
    "FIN NIFTY":      "^CNXFIN",
    "SENSEX":         "^BSESN",
    "SENSEX BANK":    "^BSEBK",
    "GIFT NIFTY (NSE IX Proxy)": "^NSEI",
    "INDIA VIX":      "^INDIAVIX",
    
    # Americas
    "S&P 500":        "^GSPC",
    "NASDAQ":         "^IXIC",
    "Dow Jones":      "^DJI",
    
    # Europe
    "FTSE 100":       "^FTSE",
    "DAX":            "^GDAXI",
    "CAC 40":         "^FCHI",
    "Euro Stoxx 50":  "^STOXX50E",
    "SMI (Switzerland)": "^SSMI",
    
    # Asia
    "Nikkei 225":     "^N225",
    "Hang Seng":      "^HSI",
    "STI (Singapore)": "^STI",
    "Shanghai":       "000001.SS",
    "Kospi":          "^KS11",
    "Taiwan (TWII)":  "^TWII",
    
    # Australia
    "ASX 200":        "^AXJO",

    # Commodities & Macro
    "Brent Crude Oil": "BZ=F",
    "Gold":            "GC=F",
    "USD/INR":         "INR=X",
}

REGION_MAP = {
    "NIFTY 50": "India", "BANK NIFTY": "India", "FIN NIFTY": "India",
    "SENSEX": "India", "SENSEX BANK": "India", "GIFT NIFTY (NSE IX Proxy)": "India",
    "INDIA VIX": "India",
    "S&P 500": "Americas", "NASDAQ": "Americas", "Dow Jones": "Americas",
    "FTSE 100": "Europe", "DAX": "Europe", "CAC 40": "Europe",
    "Euro Stoxx 50": "Europe", "SMI (Switzerland)": "Europe",
    "Nikkei 225": "Asia", "Hang Seng": "Asia", "STI (Singapore)": "Asia", 
    "Shanghai": "Asia", "Kospi": "Asia", "Taiwan (TWII)": "Asia",
    "ASX 200": "Australia",
    "Brent Crude Oil": "Commodities", "Gold": "Commodities", "USD/INR": "Forex",
}

# Ticker → BTST cue group mapping
_BTST_US_TICKERS     = ["^GSPC", "^IXIC", "^DJI"]             # S&P500, Nasdaq, Dow
_BTST_EUROPE_TICKERS = ["^FTSE", "^GDAXI", "^FCHI"]         # FTSE 100, DAX, CAC 40
_BTST_ASIA_TICKERS   = ["^N225", "^HSI", "^STI", "000001.SS", "^KS11", "^TWII"]  # Asia
_BTST_INDIA_TICKER   = "^NSEI"                                # Nifty50 as Gift Nifty proxy

def fetch_world_markets(ignore_cache: bool = False) -> dict:
    """
    Fetch world indices using a hybrid approach:
    1. Primary: Groww Scraper (High fidelity for India + Real GIFT Nifty)
    2. Secondary/Merge: yfinance (Coverage for missing global indices)
    """
    global _GLOBAL_MARKETS_CACHE, _GLOBAL_MARKETS_TIMESTAMP
    # Translate to yf result if groww missing.
    # Check cache
    if not ignore_cache and _GLOBAL_MARKETS_CACHE and (time.time() - _GLOBAL_MARKETS_TIMESTAMP < _GLOBAL_MARKETS_TTL):
        return _GLOBAL_MARKETS_CACHE

    try:
        # ── Step 1: Fetch Groww Data ─────────────────────────────────────────
        groww_map = {}
        groww_source = None
        try:
            groww_data = fetch_groww_indices()
            if groww_data and groww_data.get("markets"):
                groww_map = {m["std_name"]: m for m in groww_data["markets"]}
                groww_source = "Groww"
        except Exception as e:
            print(f"Groww Scraper Error: {e}")

        # ── Step 2: Fetch yfinance Data (Bulk) ───────────────────────────────
        import yfinance as yf
        # Filter: only fetch from yfinance if not already provided by Groww
        yf_tickers = [ticker for name, ticker in WORLD_INDICES.items() if name not in groww_map]
        
        # Download EOD baseline for missing global indices
        data = pd.DataFrame()
        if yf_tickers:
            data = yf.download(yf_tickers, period="5d", progress=False, auto_adjust=True)["Close"]
            if isinstance(data, pd.Series):
                data = data.to_frame()

        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # ── Step 3: Merge and Enrich ─────────────────────────────────────────
        final_markets = []
        for name, ticker in WORLD_INDICES.items():
            # Priority 1: Groww (if available)
            if name in groww_map:
                m = groww_map[name]
                final_markets.append({
                    "name": name,
                    "ticker": ticker,
                    "region": REGION_MAP.get(name, "Other"),
                    "last": m["last"],
                    "prev": 0.0,
                    "change_pct": m["change_pct"],
                    "direction": "up" if m["change_pct"] > 0 else "down" if m["change_pct"] < 0 else "flat",
                    "source": "Groww"
                })
                continue
            
            # Priority 2: yfinance
            lc, pc, chg = 0.0, 0.0, 0.0
            try:
                col_data = data[ticker].dropna() if ticker in data.columns else pd.Series(dtype=float)
                last_date = col_data.index[-1].strftime("%Y-%m-%d") if not col_data.empty else ""
                eod_last  = float(col_data.iloc[-1])  if not col_data.empty else 0.0
                eod_prev  = float(col_data.iloc[-2])  if len(col_data) >= 2 else 0.0

                if last_date == today_str:
                    lc, pc = eod_last, eod_prev
                else:
                    # Enrich with fast_info for live session
                    t_obj = yf.Ticker(ticker)
                    info  = t_obj.fast_info
                    lc    = info.get("last_price", eod_last)
                    pc    = info.get("previous_close", eod_prev)
                
                if pc > 0:
                    chg = ((lc - pc) / pc) * 100
                
                final_markets.append({
                    "name": name,
                    "ticker": ticker,
                    "region": REGION_MAP.get(name, "Other"),
                    "last": round(lc, 2),
                    "prev": round(pc, 2),
                    "change_pct": round(chg, 2),
                    "direction": "up" if chg > 0.02 else "down" if chg < -0.02 else "flat",
                    "source": "yfinance"
                })
            except Exception:
                pass

        if final_markets:
            cache_result = {
                "markets": final_markets, 
                "timestamp": datetime.now().isoformat(), 
                "source": "Hybrid (Groww + yfinance)", 
                "error": None
            }
            _GLOBAL_MARKETS_CACHE = cache_result
            _GLOBAL_MARKETS_TIMESTAMP = time.time()
            return cache_result

        return {"markets": [], "error": "No data fetched from any source"}
    except Exception as e:
        return {"markets": [], "timestamp": datetime.now().isoformat(), "error": str(e)}

def _pct_to_signal(avg_pct: float) -> Literal["UP", "DOWN", "FLAT"]:
    """Convert an average % change into UP/DOWN/FLAT cue signal. Threshold removed: any change counts."""
    if avg_pct > 0:
        return "UP"
    if avg_pct < 0:
        return "DOWN"
    return "FLAT"

def derive_btst_cues(markets: list[dict]) -> dict:
    """
    Derive the BTST global cue signals with 40/60 weightage.
    Core (40%): Nifty 50, Gift Nifty, India VIX, Brent Crude (Inverted)
    Global (60%): US, Europe, Asia
    """
    by_name = {m["name"]: m for m in markets}

    # ── 1. Indian Core (40% Weightage) ──────────
    n50_pct    = by_name.get("NIFTY 50", {}).get("change_pct", 0.0)
    gift_pct   = by_name.get("GIFT NIFTY (NSE IX Proxy)", {}).get("change_pct", 0.0)
    vix_pct    = by_name.get("INDIA VIX", {}).get("change_pct", 0.0)
    crude_pct  = by_name.get("Brent Crude Oil", {}).get("change_pct", 0.0)
    usdinr_pct = by_name.get("USD/INR", {}).get("change_pct", 0.0)
    
    # VIX, Crude, and USD/INR are inverted for Indian bullishness (Down = bullish)
    # We give Crude and USD/INR a 0.5 weighting because they are secondary drivers
    core_avg = (n50_pct + gift_pct - vix_pct - (0.5 * crude_pct) - (0.5 * usdinr_pct)) / 4.0
    core_signal = _pct_to_signal(core_avg)

    # ── 2. Global Markets (60% Weightage) ─────────
    # US
    us_indices = ["S&P 500", "NASDAQ", "Dow Jones"]
    us_vals = [by_name[n]["change_pct"] for n in us_indices if n in by_name]
    us_avg = sum(us_vals) / len(us_vals) if us_vals else 0.0
    
    # Europe
    eu_indices = ["FTSE 100", "DAX", "CAC 40", "Euro Stoxx 50", "SMI (Switzerland)"]
    eu_vals = [by_name[n]["change_pct"] for n in eu_indices if n in by_name]
    eu_avg = sum(eu_vals) / len(eu_vals) if eu_vals else 0.0
    
    # Asia
    as_indices = ["Nikkei 225", "Hang Seng", "STI (Singapore)", "Shanghai", "Kospi", "Taiwan (TWII)"]
    as_vals = [by_name[n]["change_pct"] for n in as_indices if n in by_name]
    as_avg = sum(as_vals) / len(as_vals) if as_vals else 0.0
    
    global_avg = (us_avg + eu_avg + as_avg) / 3.0
    global_signal = _pct_to_signal(global_avg)

    # ── 3. Weighted Final Signal ──────────────────
    weighted_pct = (core_avg * 0.4) + (global_avg * 0.6)
    final_signal = _pct_to_signal(weighted_pct)

    return {
        "weighted_pct": round(weighted_pct, 3),
        "final_signal": final_signal,
        "gift_nifty":   _pct_to_signal(gift_pct),
        "us_market":    _pct_to_signal(us_avg),
        "europe_market": _pct_to_signal(eu_avg),
        "asia_market":  _pct_to_signal(as_avg),
        "vix":          vix_pct,
        "crude":        crude_pct,
        "derived_cues": {
            "core_india": {
                "signal": core_signal,
                "pct": round(core_avg, 3),
                "indices": [
                    {"name": "Nifty 50", "pct": n50_pct},
                    {"name": "Gift Nifty", "pct": gift_pct},
                    {"name": "India VIX", "pct": vix_pct},
                    {"name": "Brent Crude", "pct": crude_pct},
                    {"name": "USD/INR", "pct": usdinr_pct}
                ]
            },
            "global_market": {
                "signal": global_signal,
                "pct": round(global_avg, 3),
                "indices": [
                    {"name": "US Avg", "pct": round(us_avg, 3)},
                    {"name": "Europe Avg", "pct": round(eu_avg, 3)},
                    {"name": "Asia Avg", "pct": round(as_avg, 3)}
                ]
            }
        }
    }
