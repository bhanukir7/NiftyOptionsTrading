"""
global_cues.py — Shared Global Market Analysis Logic
Provides live fetching of global indices via yfinance and derives sentiment cues.
"""

from datetime import datetime
import time
from typing import Literal, Optional
import pandas as pd

# Global cache for yfinance to reduce pings
_GLOBAL_MARKETS_CACHE = None
_GLOBAL_MARKETS_TIMESTAMP = 0
_GLOBAL_MARKETS_TTL = 300  # 5 minutes

# Market mapping for Dashboard & BTST
WORLD_INDICES = {
    # India
    "Nifty 50":       "^NSEI",
    "Bank Nifty":     "^NSEBANK",
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
    "Shanghai":       "000001.SS",
    "Kospi":          "^KS11",
    "Sensex":         "^BSESN",
    "Taiwan (TWII)":  "^TWII",
    # Australia
    "ASX 200":        "^AXJO",
}

REGION_MAP = {
    "Nifty 50": "India", "Bank Nifty": "India", "Sensex": "India",
    "S&P 500": "Americas", "NASDAQ": "Americas", "Dow Jones": "Americas",
    "FTSE 100": "Europe", "DAX": "Europe", "CAC 40": "Europe",
    "Euro Stoxx 50": "Europe", "SMI (Switzerland)": "Europe",
    "Nikkei 225": "Asia", "Hang Seng": "Asia", "Shanghai": "Asia",
    "Kospi": "Asia", "Taiwan (TWII)": "Asia",
    "ASX 200": "Australia",
}

# Ticker → BTST cue group mapping
_BTST_US_TICKERS     = ["^GSPC", "^IXIC", "^DJI"]             # S&P500, Nasdaq, Dow
_BTST_EUROPE_TICKERS = ["^FTSE", "^GDAXI", "^FCHI"]         # FTSE 100, DAX, CAC 40
_BTST_ASIA_TICKERS   = ["^N225", "^HSI", "000001.SS", "^KS11", "^TWII"]  # Asia
_BTST_INDIA_TICKER   = "^NSEI"                                # Nifty50 as Gift Nifty proxy

def fetch_world_markets() -> dict:
    """Fetch live quote data for world indices via yfinance with 5-min caching."""
    global _GLOBAL_MARKETS_CACHE, _GLOBAL_MARKETS_TIMESTAMP

    # Check cache
    if _GLOBAL_MARKETS_CACHE and (time.time() - _GLOBAL_MARKETS_TIMESTAMP < _GLOBAL_MARKETS_TTL):
        return _GLOBAL_MARKETS_CACHE

    try:
        import yfinance as yf
        tickers = list(WORLD_INDICES.values())
        # period="5d" to ensure we get at least 2 valid closing points for pct_change
        data = yf.download(tickers, period="5d", progress=False, auto_adjust=True)["Close"]
        
        if isinstance(data, pd.Series):
            data = data.to_frame()

        pct = data.pct_change(fill_method=None).iloc[-1]
        prev_close = data.iloc[-2]
        last_close = data.iloc[-1]

        results = []
        for name, ticker in WORLD_INDICES.items():
            try:
                chg = float(pct.get(ticker, 0.0) or 0.0) * 100
                lc  = float(last_close.get(ticker, 0.0) or 0.0)
                pc  = float(prev_close.get(ticker, 0.0) or 0.0)
            except Exception:
                chg, lc, pc = 0.0, 0.0, 0.0
            
            results.append({
                "name":   name,
                "ticker": ticker,
                "region": REGION_MAP.get(name, "Other"),
                "last":   round(lc, 2),
                "prev":   round(pc, 2),
                "change_pct": round(chg, 3),
                "direction": "up" if chg > 0 else "down" if chg < 0 else "flat",
            })
        
        cache_result = {"markets": results, "timestamp": datetime.now().isoformat(), "error": None}
        _GLOBAL_MARKETS_CACHE = cache_result
        _GLOBAL_MARKETS_TIMESTAMP = time.time()
        return cache_result
    except Exception as e:
        return {"markets": [], "timestamp": datetime.now().isoformat(), "error": str(e)}

def _pct_to_signal(avg_pct: float, threshold: float = 0.15) -> Literal["UP", "DOWN", "FLAT"]:
    """Convert an average % change into UP/DOWN/FLAT cue signal."""
    if avg_pct > threshold:
        return "UP"
    if avg_pct < -threshold:
        return "DOWN"
    return "FLAT"

def derive_btst_cues(markets: list[dict]) -> dict:
    """
    Derive the three BTST global cue signals from live yfinance market data.
    """
    by_ticker = {m["ticker"]: m for m in markets}

    # Gift Nifty proxy — use live Nifty 50
    nifty_m   = by_ticker.get(_BTST_INDIA_TICKER, {})
    nifty_pct = nifty_m.get("change_pct", 0.0)
    gift_nifty = _pct_to_signal(nifty_pct, threshold=0.2)

    # US market — average of the three US indices
    us_vals = [by_ticker[t]["change_pct"] for t in _BTST_US_TICKERS if t in by_ticker]
    us_avg  = sum(us_vals) / len(us_vals) if us_vals else 0.0
    us_market = _pct_to_signal(us_avg, threshold=0.15)

    # Europe market — average of major European indices
    euro_vals = [by_ticker[t]["change_pct"] for t in _BTST_EUROPE_TICKERS if t in by_ticker]
    euro_avg  = sum(euro_vals) / len(euro_vals) if euro_vals else 0.0
    europe_market = _pct_to_signal(euro_avg, threshold=0.15)

    # Asia market — average of major Asian indices
    asia_vals = [by_ticker[t]["change_pct"] for t in _BTST_ASIA_TICKERS if t in by_ticker]
    asia_avg  = sum(asia_vals) / len(asia_vals) if asia_vals else 0.0
    asia_market = _pct_to_signal(asia_avg, threshold=0.15)

    return {
        "gift_nifty":   gift_nifty,
        "us_market":    us_market,
        "europe_market": europe_market,
        "asia_market":  asia_market,
        "derived_cues": {
            "gift_nifty": {
                "signal": gift_nifty,
                "source": "Nifty 50 (live proxy)",
                "pct":    round(nifty_pct, 3),
                "indices": [{"name": nifty_m.get("name", "Nifty 50"), "pct": round(nifty_pct, 3)}],
            },
            "us_market": {
                "signal": us_market,
                "source": "S&P 500 + NASDAQ + Dow Jones average",
                "pct":    round(us_avg, 3),
                "indices": [
                    {"name": by_ticker[t]["name"], "pct": round(by_ticker[t]["change_pct"], 3)}
                    for t in _BTST_US_TICKERS if t in by_ticker
                ],
            },
            "europe_market": {
                "signal": europe_market,
                "source": "FTSE 100 + DAX + CAC 40 average",
                "pct":    round(euro_avg, 3),
                "indices": [
                    {"name": by_ticker[t]["name"], "pct": round(by_ticker[t]["change_pct"], 3)}
                    for t in _BTST_EUROPE_TICKERS if t in by_ticker
                ],
            },
            "asia_market": {
                "signal": asia_market,
                "source": "Nikkei + Hang Seng + Shanghai + Kospi + Taiwan average",
                "pct":    round(asia_avg, 3),
                "indices": [
                    {"name": by_ticker[t]["name"], "pct": round(by_ticker[t]["change_pct"], 3)}
                    for t in _BTST_ASIA_TICKERS if t in by_ticker
                ],
            },
        },
    }
