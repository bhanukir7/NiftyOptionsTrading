"""
Strict Intraday Trading Signal Validator
Implements multi-factor validation with weighted confidence scoring.
"""
import pandas as pd
import numpy as np
from ta.trend import ema_indicator
from ta.momentum import rsi
from ta.volume import volume_weighted_average_price

def validate_strict_signal(df: pd.DataFrame) -> dict:
    """
    Evaluates price data against strict intraday rules and returns a structured signal.
    """
    if df is None or len(df) < 50:
        return {
            "signal": "NO TRADE",
            "confidence": 0,
            "reasons": ["Insufficient data for calculation"]
        }

    # Ensure numeric
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill missing volume with 0 (Indices like NIFTY often have no volume in cash segment)
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0)
        
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    # Guard: after cleaning, ensure sufficient rows remain for indicators (EMA21, RSI14, etc.)
    if len(df) < 30:
        return {
            "signal": "NO TRADE",
            "confidence": 0,
            "reasons": ["Insufficient clean data after removing NaN values"],
            "indicators": {"price": 0, "ema9": 0, "ema21": 0, "vwap": 0,
                           "rsi": 50, "volume": 0, "avg_volume": 0}
        }

    # 1. Calculate base indicators
    price = df.iloc[-1]["close"]
    ema9 = ema_indicator(df["close"], window=9).iloc[-1]
    ema21 = ema_indicator(df["close"], window=21).iloc[-1]
    curr_rsi = rsi(df["close"], window=14).iloc[-1]
    current_volume = df.iloc[-1]["volume"]
    avg_volume_10 = df["volume"].tail(10).mean()
    
    # VWAP (Intraday)
    df["vwap"] = volume_weighted_average_price(high=df["high"], low=df["low"], close=df["close"], volume=df["volume"])
    vwap = df["vwap"].iloc[-1]

    reasons = []
    confidence = 0
    
    # --- BULLISH CHECKS ---
    bull_checks = {
        "trend": price > ema9 > ema21,
        "vwap": price > vwap,
        "momentum": curr_rsi > 60,
        "volume": current_volume > (avg_volume_10 * 1.5),
        "pullback": (abs(price - ema9) / price <= 0.002) or (abs(price - vwap) / price <= 0.002)
    }
    
    # --- BEARISH CHECKS ---
    bear_checks = {
        "trend": price < ema9 < ema21,
        "vwap": price < vwap,
        "momentum": curr_rsi < 40,
        "volume": current_volume > (avg_volume_10 * 1.5), # Volume is same for both
        "pullback": (abs(price - ema9) / price <= 0.002) or (abs(price - vwap) / price <= 0.002)
    }

    # Weights
    weights = {
        "trend": 25,
        "vwap": 20,
        "momentum": 20,
        "pullback": 20,
        "volume": 15
    }

    # Evaluation
    is_all_bull = all(bull_checks.values())
    is_all_bear = all(bear_checks.values())

    if is_all_bull:
        signal = "BUY"
        confidence = 100
        reasons = ["All bullish conditions met (Trend, VWAP, RSI, Volume, Pullback)"]
    elif is_all_bear:
        signal = "SELL"
        confidence = 100
        reasons = ["All bearish conditions met (Trend, VWAP, RSI, Volume, Pullback)"]
    else:
        signal = "NO TRADE"
        reasons = []
        # Calculate confidence anyway for information
        bull_score = sum(weights[k] for k, v in bull_checks.items() if v)
        bear_score = sum(weights[k] for k, v in bear_checks.items() if v)
        
        if bull_score >= bear_score:
            confidence = bull_score
            bias = "Bullish"
            checks = bull_checks
        else:
            confidence = bear_score
            bias = "Bearish"
            checks = bear_checks
            
        for k, v in checks.items():
            if v: reasons.append(f"{k.upper()}: Conforming ({bias})")
            else: reasons.append(f"{k.upper()}: Failed ({bias} requirement)")

    # Ensure all indicator values are JSON-serializable (no NaN/Inf)
    def clean_val(v):
        import math
        try:
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return 0
            return v
        except: return 0

    res = {
        "signal": signal,
        "confidence": int(confidence),
        "reasons": reasons,
        "indicators": {
            "price": round(clean_val(price), 2),
            "ema9": round(clean_val(ema9), 2),
            "ema21": round(clean_val(ema21), 2),
            "vwap": round(clean_val(vwap), 2),
            "rsi": round(clean_val(curr_rsi), 2),
            "volume": int(clean_val(current_volume)),
            "avg_volume": int(clean_val(avg_volume_10))
        }
    }
    return res
