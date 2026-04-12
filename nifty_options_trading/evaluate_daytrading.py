"""
Intraday Day Trading Signals (Pine Script Port)
Implements 'ToxicJ3ster - Signals for Day Trading' logic in Python.
Combines EMA Crossovers, RSI, Volume, ATR, VWAP, and MACD.

Author: Antigravity AI
"""
import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np
from ta.trend import ema_indicator, sma_indicator, MACD
from ta.volatility import AverageTrueRange
from ta.volume import volume_weighted_average_price

# Critical default thresholds from Pine Script
SHORT_MA_PERIOD = 9
LONG_MA_PERIOD = 21
RSI_PERIOD = 9
DELTA_THRESHOLD = 0.10
VOLUME_MULTIPLIER = 0.6
ATR_MULTIPLIER = 0.6
VOLUME_SPIKE_THRESHOLD = 0.7
BODY_SIZE_THRESHOLD_PERCENT = 25

def analyze_daytrading_signals(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 50:
        return {"signal": "HOLD", "reason": "Not enough data (need at least 50 candles)"}

    # Ensure numeric types for indicators
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill any NAs from conversion
    df = df.copy().dropna(subset=["close", "volume"])
    
    if len(df) < 50:
        return {
            "signal": "HOLD", 
            "reason": f"Not enough numeric data after cleaning (have {len(df)} rows, need 50)",
            "trend": "NONE",
            "indicators": {},
            "close": 0
        }

    try:
        # 1. Moving Averages
        df["short_ma"] = ema_indicator(df["close"], window=SHORT_MA_PERIOD)
        df["long_ma"] = ema_indicator(df["close"], window=LONG_MA_PERIOD)
        df["ema_delta"] = (df["short_ma"] - df["long_ma"]).abs()

        # 2. RSI & Smoothed RSI
        from ta.momentum import rsi
        df["rsi"] = rsi(df["close"], window=RSI_PERIOD)
        df["smoothed_rsi"] = sma_indicator(df["rsi"], window=30)

        # 3. Volume & ATR Filtering
        df["avg_volume"] = sma_indicator(df["volume"], window=20)
        
        atr_obj = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14)
        df["atr"] = atr_obj.average_true_range()
        df["avg_atr"] = sma_indicator(df["atr"], window=20)

        # 4. VWAP
        df["vwap"] = volume_weighted_average_price(high=df["high"], low=df["low"], close=df["close"], volume=df["volume"])

        # 5. MACD
        macd_obj = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd_obj.macd()
        df["macd_signal"] = macd_obj.macd_signal()
        df["macd_hist"] = macd_obj.macd_diff()
    except Exception as e:
        return {
            "signal": "ERROR", 
            "reason": f"Indicator calculation failed: {str(e)}",
            "trend": "NONE",
            "indicators": {},
            "close": 0
        }

    # --- Logic ---
    # Focus on the latest and previous bars
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Conditions
    volume_condition = latest["volume"] > (latest["avg_volume"] * VOLUME_MULTIPLIER)
    volatility_condition = latest["atr"] > (latest["avg_atr"] * ATR_MULTIPLIER)
    
    # Crossovers
    bull_crossover = (prev["short_ma"] <= prev["long_ma"]) and (latest["short_ma"] > latest["long_ma"])
    bear_crossover = (prev["short_ma"] >= prev["long_ma"]) and (latest["short_ma"] < latest["long_ma"])

    bull_signal = bull_crossover and (volume_condition or volatility_condition)
    bear_signal = bear_crossover and (volume_condition or volatility_condition)

    # Trend Confirmation (simplified state tracking by looking at the last few bars)
    # In Pine Script, confirmedBull is a persisting bool. 
    # Here we check if the most recent crossover was a bull one and it hasn't crossed back.
    # We find the last crossover point.
    
    def get_last_crossover_state(df):
        # Scan backward to find the most recent crossover of 9/21 EMA
        for i in range(len(df)-1, 0, -1):
            curr_s = df.iloc[i]["short_ma"]
            curr_l = df.iloc[i]["long_ma"]
            prev_s = df.iloc[i-1]["short_ma"]
            prev_l = df.iloc[i-1]["long_ma"]
            
            # Use same confirmation logic: crossover + volume + delta
            vol_cond = df.iloc[i]["volume"] > (df.iloc[i]["avg_volume"] * VOLUME_MULTIPLIER)
            volatility_cond = df.iloc[i]["atr"] > (df.iloc[i]["avg_atr"] * ATR_MULTIPLIER)
            delta_ok = df.iloc[i]["ema_delta"] > DELTA_THRESHOLD
            
            if (prev_s <= prev_l) and (curr_s > curr_l) and (vol_cond or volatility_cond) and delta_ok:
                return "BULL_CONFIRMED"
            if (prev_s >= prev_l) and (curr_s < curr_l) and (vol_cond or volatility_cond) and delta_ok:
                return "BEAR_CONFIRMED"
        return "NONE"

    trend_state = get_last_crossover_state(df)
    is_bull_confirmed = (trend_state == "BULL_CONFIRMED")
    is_bear_confirmed = (trend_state == "BEAR_CONFIRMED")

    # Specific Buy/Sell Triggers
    vwap_buy = (prev["close"] <= prev["vwap"]) and (latest["close"] > latest["vwap"]) and is_bull_confirmed
    vwap_sell = (prev["close"] >= prev["vwap"]) and (latest["close"] < latest["vwap"]) and is_bear_confirmed

    macd_hist_bullish_change = (latest["macd_hist"] >= 0 and prev["macd_hist"] <= 0 and latest["volume"] <= prev["volume"])
    macd_hist_bearish_change = (latest["macd_hist"] <= 0 and prev["macd_hist"] >= 0 and latest["volume"] <= prev["volume"])
    
    macd_buy = macd_hist_bullish_change and is_bull_confirmed
    macd_sell = macd_hist_bearish_change and is_bear_confirmed

    rsi_buy = (latest["smoothed_rsi"] <= 25) and is_bull_confirmed and (latest["short_ma"] > latest["long_ma"])
    rsi_sell = (latest["smoothed_rsi"] >= 75) and is_bear_confirmed and (latest["short_ma"] < latest["long_ma"])

    # Volume Reversal Pattern
    # volume[1] > avgVolume * threshold and not smallBody and close[1]<open[1] and close>open
    def has_small_body(row):
        body_size = abs(row["close"] - row["open"])
        candle_range = row["high"] - row["low"]
        if candle_range == 0: return True
        return body_size < (candle_range * BODY_SIZE_THRESHOLD_PERCENT / 100)

    volume_reversal_buy = (prev["volume"] > (latest["avg_volume"] * VOLUME_SPIKE_THRESHOLD)) \
        and not has_small_body(prev) \
        and (prev["close"] < prev["open"]) \
        and (latest["close"] > latest["open"]) \
        and not (vwap_buy or macd_buy or rsi_buy)

    volume_reversal_sell = (prev["volume"] > (latest["avg_volume"] * VOLUME_SPIKE_THRESHOLD)) \
        and not has_small_body(prev) \
        and (prev["close"] > prev["open"]) \
        and (latest["close"] < latest["open"]) \
        and not (vwap_buy or macd_buy or rsi_buy or vwap_sell or macd_sell or rsi_sell)

    any_buy = vwap_buy or macd_buy or rsi_buy or volume_reversal_buy
    any_sell = vwap_sell or macd_sell or rsi_sell or volume_reversal_sell

    signal = "HOLD"
    reason = "Waiting for confirmed high-conviction signal."
    
    if any_buy:
        signal = "BUY_CALL"
        if vwap_buy: reason = "VWAP Breakout + Bull Trend Confirmed."
        elif macd_buy: reason = "MACD Reversal + Bull Trend Confirmed."
        elif rsi_buy: reason = "RSI Oversold + Bull Trend Confirmed."
        elif volume_reversal_buy: reason = "Volume Reversal Pattern detected."
    elif any_sell:
        signal = "BUY_PUT"
        if vwap_sell: reason = "VWAP Breakdown + Bear Trend Confirmed."
        elif macd_sell: reason = "MACD Reversal + Bear Trend Confirmed."
        elif rsi_sell: reason = "RSI Overbought + Bear Trend Confirmed."
        elif volume_reversal_sell: reason = "Volume Reversal Pattern detected."
    elif is_bull_confirmed:
        reason = "Bull trend confirmed via EMA 9/21. Looking for specific entry trigger (VWAP/MACD)."
    elif is_bear_confirmed:
        reason = "Bear trend confirmed via EMA 9/21. Looking for specific entry trigger (VWAP/MACD)."

    return {
        "signal": signal,
        "reason": reason,
        "trend": trend_state,
        "indicators": {
            "short_ma": round(latest["short_ma"], 2),
            "long_ma": round(latest["long_ma"], 2),
            "rsi": round(latest["rsi"], 2),
            "smoothed_rsi": round(latest["smoothed_rsi"], 2),
            "vwap": round(latest["vwap"], 2),
            "macd_hist": round(latest["macd_hist"], 4),
            "ema_delta": round(latest["ema_delta"], 2),
            "volume_ratio": round(latest["volume"] / (latest["avg_volume"] or 1), 2),
            "atr_ratio": round(latest["atr"] / (latest["avg_atr"] or 1), 2)
        },
        "close": latest["close"]
    }

def generate_daytrading_verdict(signal_data: dict, opt_type: str) -> str:
    signal = signal_data.get("signal", "HOLD")
    trend = signal_data.get("trend", "NONE")
    
    if opt_type == "CE":
        if signal == "BUY_CALL":
            return "🟢 DAY TRADING BUY TRIGGERED (High-probability entry detected)"
        if trend == "BULL_CONFIRMED":
            return "🟡 BULL BIAS (Trend confirmed, but waiting for entry trigger like VWAP/MACD)"
        if trend == "BEAR_CONFIRMED":
            return "🛑 AVOID CALLS (Confirmed Bear Trend in place)"
        return "⚪ NEUTRAL (No trend or entry signal currently)"
    else:
        if signal == "BUY_PUT":
            return "🔴 DAY TRADING SELL TRIGGERED (High-probability entry detected)"
        if trend == "BEAR_CONFIRMED":
            return "🟡 BEAR BIAS (Trend confirmed, but waiting for entry trigger like VWAP/MACD)"
        if trend == "BULL_CONFIRMED":
            return "🛑 AVOID PUTS (Confirmed Bull Trend in place)"
        return "⚪ NEUTRAL (No trend or entry signal currently)"
