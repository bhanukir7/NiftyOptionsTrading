"""
Morning Trade Panel Strategy Logic
Intraday Opening Range Breakout (ORB) with Multi-Index Confirmation.
Indicators: VWAP, EMA (9, 21), RSI (14).
Confirmation: Nifty + Bank Nifty (optional Sensex).

Author: Antigravity AI
"""
import pandas as pd
import numpy as np
from datetime import datetime, time
from ta.trend import ema_indicator
from ta.momentum import rsi
from ta.volume import volume_weighted_average_price

def morning_trade_panel(nifty_df, banknifty_df=None, sensex_df=None) -> dict:
    """
    Core logic for the Morning Trade Panel.
    Args:
        nifty_df: DataFrame with at least ['datetime', 'open', 'high', 'low', 'close', 'volume']
        banknifty_df: Optional DataFrame for Bank Nifty
        sensex_df: Optional DataFrame for Sensex
    Returns:
        dict: Panel data for UI display
    """
    # 1. CLEANING & TYPE CONVERSION
    def clean_df(df):
        if df is None or df.empty: return None
        df = df.copy()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=["close"], inplace=True)
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)
        return df

    nifty_df = clean_df(nifty_df)
    banknifty_df = clean_df(banknifty_df)
    sensex_df = clean_df(sensex_df)

    if nifty_df is None or nifty_df.empty:
        return {"error": "Insufficient Nifty data"}

    # 2. ORB CALCULATION (9:15 - 9:30)
    # Filter for today's session
    latest_date = nifty_df.index.date[-1]
    today_df = nifty_df[nifty_df.index.date == latest_date]
    
    orb_start = time(9, 15)
    orb_end = time(9, 30)
    orb_window = today_df[(today_df.index.time >= orb_start) & (today_df.index.time < orb_end)]
    
    if not orb_window.empty:
        orb_high = orb_window['high'].max()
        orb_low = orb_window['low'].min()
    else:
        # Fallback if we haven't reached 9:30 yet or it's the start of the day
        # Use first 3 candles if 5-min, or first 15 if 1-min
        orb_high = today_df['high'].iloc[:3].max() if len(today_df) >= 3 else today_df['high'].max()
        orb_low = today_df['low'].iloc[:3].min() if len(today_df) >= 3 else today_df['low'].min()

    # 3. INDICATORS
    nifty_df["vwap"] = volume_weighted_average_price(
        high=nifty_df["high"], low=nifty_df["low"], close=nifty_df["close"], volume=nifty_df["volume"]
    )
    nifty_df["ema9"] = ema_indicator(nifty_df["close"], window=9)
    nifty_df["ema21"] = ema_indicator(nifty_df["close"], window=21)
    nifty_df["rsi"] = rsi(nifty_df["close"], window=14)

    latest = nifty_df.iloc[-1]
    prev = nifty_df.iloc[-2] if len(nifty_df) > 1 else latest
    
    price = latest["close"]
    vwap = latest["vwap"]
    ema9 = latest["ema9"]
    ema21 = latest["ema21"]
    rsi_val = latest["rsi"]

    # 4. CROSS-INDEX CONFIRMATION
    def get_vwap_status(df):
        if df is None or df.empty: return "na"
        df = df.copy()
        df["vwap"] = volume_weighted_average_price(
            high=df["high"], low=df["low"], close=df["close"], volume=df["volume"]
        )
        l = df.iloc[-1]
        return "above_vwap" if l["close"] >= l["vwap"] else "below_vwap"

    bn_status = get_vwap_status(banknifty_df)
    sx_status = get_vwap_status(sensex_df)

    # Alignment Logic
    aligned = False
    if bn_status == "above_vwap" and (sx_status == "above_vwap" or sx_status == "na"):
        aligned = True
    elif bn_status == "below_vwap" and (sx_status == "below_vwap" or sx_status == "na"):
        aligned = True

    # 5. PRIMARY SIGNAL GENERATION (NIFTY)
    signal = "NO TRADE"
    reasons = []

    buy_ce_conditions = [
        price > vwap,
        price > orb_high,
        ema9 > ema21,
        rsi_val > 55
    ]
    
    buy_pe_conditions = [
        price < vwap,
        price < orb_low,
        ema9 < ema21,
        rsi_val < 45
    ]

    # Signal Logic
    if all(buy_ce_conditions):
        if bn_status == "above_vwap" and (sx_status == "above_vwap" or sx_status == "na"):
            signal = "BUY CE"
        else:
            reasons.append("Cross-index mismatch (Bank Nifty/Sensex not above VWAP)")
    elif all(buy_pe_conditions):
        if bn_status == "below_vwap" and (sx_status == "below_vwap" or sx_status == "na"):
            signal = "BUY PE"
        else:
            reasons.append("Cross-index mismatch (Bank Nifty/Sensex not below VWAP)")

    # 6. FAKE BREAKOUT FILTER
    if signal == "BUY CE" and prev["close"] > orb_high and price < orb_high:
        signal = "NO TRADE"
        reasons.append("Fake Breakout: Price failed to sustain above ORB High")
    elif signal == "BUY PE" and prev["close"] < orb_low and price > orb_low:
        signal = "NO TRADE"
        reasons.append("Fake Breakout: Price failed to sustain below ORB Low")

    # Override to NO TRADE if confirmation failed
    if signal != "NO TRADE" and not aligned:
        signal = "NO TRADE"
        reasons.append("Alignment Filter: Indices not moving in sync")

    # 7. CONFIDENCE SCORE
    score = 0
    if ema9 > ema21 if signal != "BUY PE" else ema9 < ema21: score += 25
    if price > vwap if signal != "BUY PE" else price < vwap: score += 20
    if price > orb_high if signal != "BUY PE" else price < orb_low: score += 25
    if rsi_val > 55 if signal != "BUY PE" else rsi_val < 45: score += 15
    if aligned: score += 15

    # 8. TRADE SETUP
    trade = {}
    if signal != "NO TRADE":
        entry_type = "Breakout" if abs(price - (orb_high if signal == "BUY CE" else orb_low)) < (price * 0.001) else "Retest"
        strike = "ATM" # Logic will be refined in app.py based on actual chain
        sl = vwap if abs(price - vwap) < abs(price - (orb_high if signal == "BUY CE" else orb_low)) else (orb_high if signal == "BUY CE" else orb_low)
        
        # Targets (based on ATR or fixed % as requested)
        targets = ["T1 (30-40%)", "Runner (Trail)"]
        
        trade = {
            "entry_type": entry_type,
            "strike": strike,
            "sl": round(sl, 2),
            "targets": targets
        }

    # reasoning
    if not reasons:
        if signal == "BUY CE":
            reasons = ["EMA Bullish Cross", "Above VWAP", "ORB High Breakout", "RSI Momentum > 55", "Multi-Index Confirmed"]
        elif signal == "BUY PE":
            reasons = ["EMA Bearish Cross", "Below VWAP", "ORB Low Breakdown", "RSI Momentum < 45", "Multi-Index Confirmed"]
        else:
            if price > orb_low and price < orb_high:
                reasons.append("Price inside ORB range")
            if (ema9 > ema21 and price < vwap) or (ema9 < ema21 and price > vwap):
                reasons.append("VWAP vs EMA Bias Conflict")
            if rsi_val > 45 and rsi_val < 55:
                reasons.append("RSI in No-Trade Zone (45-55)")

    return {
        "signal": signal,
        "confidence": score,
        "levels": {
            "spot": round(price, 2),
            "vwap": round(vwap, 2) if not np.isnan(vwap) else None,
            "orb_high": round(orb_high, 2),
            "orb_low": round(orb_low, 2)
        },
        "indicators": {
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "rsi": round(rsi_val, 2)
        },
        "confirmation": {
            "banknifty": bn_status,
            "sensex": sx_status,
            "aligned": aligned
        },
        "structure": {
            "trend": "Bullish" if ema9 > ema21 else "Bearish",
            "breakout": "Above ORB High" if price > orb_high else "Below ORB Low" if price < orb_low else "Inside Range",
            "vwap_bias": ("Bullish" if price > vwap else "Bearish" if price < vwap else "Chop") if vwap is not None else "N/A"
        },
        "trade": trade,
        "reasons": reasons,
        "source": nifty_df.attrs.get("source", "Breeze")
    }
