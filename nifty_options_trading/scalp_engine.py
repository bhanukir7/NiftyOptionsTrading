"""
Scalp Trade Lab Engine
High-speed 5m/10m options scalping validator and decision engine.
Designed for sub-2 second binary decision making (GO/BLOCK/WAIT).

Author: Antigravity AI
"""
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Dict, Optional, List
from ta.trend import ema_indicator, sma_indicator
from ta.momentum import rsi
from ta.volume import volume_weighted_average_price
from ta.volatility import AverageTrueRange

class LevelEngine:
    """Calculates key trading levels: PDH, PDL, and Opening Range."""
    
    @staticmethod
    def get_levels(df: pd.DataFrame) -> Dict:
        if df is None or df.empty:
            return {"key_resistance": 0, "key_support": 0, "pdh": 0, "pdl": 0, "orb_high": 0, "orb_low": 0}
        
        df = df.copy()
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors='coerce')
            df.dropna(subset=["datetime"], inplace=True)
            df.set_index("datetime", inplace=True)
        
        # Ensure OHLC columns are numeric
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 1. PDH / PDL (Yesterday)
        all_dates = sorted(np.unique(df.index.date))
        if len(all_dates) < 2:
            pdh = pdl = 0
        else:
            yesterday_date = all_dates[-2]
            yesterday_df = df[df.index.date == yesterday_date]
            pdh = yesterday_df["high"].max()
            pdl = yesterday_df["low"].min()
            
        # 2. Opening Range (15 min: 09:15 - 09:30)
        today_date = all_dates[-1]
        today_df = df[df.index.date == today_date]
        
        orb_start = time(9, 15)
        orb_end = time(9, 30)
        orb_window = today_df[(today_df.index.time >= orb_start) & (today_df.index.time < orb_end)]
        
        if not orb_window.empty:
            orb_high = orb_window["high"].max()
            orb_low = orb_window["low"].min()
        else:
            # Fallback if market just opened
            orb_high = today_df["high"].iloc[:3].max() if len(today_df) >= 3 else today_df["high"].max()
            orb_low = today_df["low"].iloc[:3].min() if len(today_df) >= 3 else today_df["low"].min()
            
        return {
            "pdh": round(float(pdh or 0), 2),
            "pdl": round(float(pdl or 0), 2),
            "orb_high": round(float(orb_high or 0), 2),
            "orb_low": round(float(orb_low or 0), 2),
            "key_resistance": round(float(orb_high or 0), 2), # Explicitly Opening Range High
            "key_support": round(float(orb_low or 0), 2)    # Explicitly Opening Range Low
        }

class InstantDecisionEngine:
    """Sub-100ms decision engine for scalping entries."""
    
    def get_instant_decision(self, symbol: str, timeframe: int, df: pd.DataFrame, oi_data: Dict) -> Dict:
        """
        Primary goal: Enable sub-2 second decision making.
        Returns: GO / BLOCK / WAIT
        """
        if df is None or len(df) < 20:
            return {
                "verdict": "YELLOW",
                "action": "WAIT",
                "confidence": "LOW",
                "reason": "Insufficient data for instant decision",
                "sl_points": 0,
                "target_points": 0,
                "flags": {}
            }
            
        # 1. TIME FILTER (MANDATORY)
        now_time = datetime.now().time()
        if time(9, 15) <= now_time <= time(9, 25):
            return self._yellow_response("Opening noise — Wait for range stability")
        if time(12, 0) <= now_time <= time(13, 30):
            return self._yellow_response("Midday chop — Liquidity low")
            
        # 2. INDICATORS
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        prev3 = df.tail(3)
        
        spot = float(latest["close"])
        vwap = float(latest.get("vwap", spot))
        atr_ind = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
        atr = float(atr_ind.average_true_range().iloc[-1])
        
        # Momentum score (Placeholder for specific multi-factor momentum)
        # Using RSI and EMA alignment as proxy for momentum score
        rsi_val = float(rsi(df["close"], window=14).iloc[-1])
        ema9 = float(ema_indicator(df["close"], window=9).iloc[-1])
        ema21 = float(ema_indicator(df["close"], window=21).iloc[-1])
        
        momentum_score = 0
        if ema9 > ema21: momentum_score += 30
        if spot > ema9: momentum_score += 20
        if rsi_val > 60: momentum_score += 20
        if rsi_val > 70: momentum_score += 10 # Extra strength
        
        # Volume Spike
        avg_vol = float(df["volume"].tail(10).mean())
        vol_spike = bool(latest["volume"] > (avg_vol * 1.5))
        
        # Candle Strength
        candle_range = latest["high"] - latest["low"]
        candle_body = abs(latest["close"] - latest["open"])
        strong_candle = bool(candle_body > (0.6 * atr))
        
        # Levels
        levels = LevelEngine.get_levels(df)
        is_breakout_up = spot > levels["key_resistance"]
        is_breakout_down = spot < levels["key_support"]
        
        # OI Walls
        ce_wall = oi_data.get("nearest_ce_wall", 999999)
        pe_wall = oi_data.get("nearest_pe_wall", 0)
        
        # Flags for UI
        flags = {
            "momentum": bool(momentum_score >= 70),
            "vwap": bool(spot > vwap), # Will be checked later for direction
            "volume": vol_spike,
            "candle_strength": strong_candle,
            "oi_clear": True, # Default, will be checked below
            "late_move": False # Default, will be checked below
        }
        
        # ---------------------------------------------------------------------
        # 🚨 HARD BLOCK CONDITIONS (ANY = RED)
        # ---------------------------------------------------------------------
        
        # 1. Near OI Wall
        near_ce_wall = (ce_wall - spot) <= (0.5 * atr)
        near_pe_wall = (spot - pe_wall) <= (0.5 * atr)
        
        # 2. Late / Exhausted Move
        total_move_3 = prev3["high"].max() - prev3["low"].min()
        late_move = bool(total_move_3 > (1.5 * atr))
        flags["late_move"] = late_move
        
        # 3. No Expansion Candle
        no_expansion = bool(candle_range < (1.2 * atr))
        
        # 4. VWAP Conflict
        vwap_conflict_bull = bool(spot < vwap)
        vwap_conflict_bear = bool(spot > vwap)
        
        # BLOCK CHECK
        if near_ce_wall or near_pe_wall:
            flags["oi_clear"] = False
            return self._red_response("BLOCK — Price near major OI wall", flags)
        if late_move:
            return self._red_response("BLOCK — Move exhausted (Over-extended)", flags)
        if no_expansion:
            return self._red_response("BLOCK — Low volatility candle (No expansion)", flags)
            
        # ---------------------------------------------------------------------
        # 🟢 GREEN CONDITIONS (ALL REQUIRED)
        # ---------------------------------------------------------------------
        
        # Bullish GO
        if (is_breakout_up and strong_candle and vol_spike and momentum_score >= 70 
            and not vwap_conflict_bull and not near_ce_wall and not late_move):
            return self._green_response("GO — Execute BUY CE (Breakout + Momentum)", "BUY CE", flags)
            
        # Bearish GO
        if (is_breakout_down and strong_candle and vol_spike and momentum_score >= 70 
            and not vwap_conflict_bear and not near_pe_wall and not late_move):
            return self._green_response("GO — Execute BUY PE (Breakdown + Momentum)", "BUY PE", flags)
            
        # ---------------------------------------------------------------------
        # 🟡 YELLOW (DEFAULT)
        # ---------------------------------------------------------------------
        return self._yellow_response("WAIT — Setup not fully aligned", flags)

    def _green_response(self, reason: str, action: str, flags: Dict) -> Dict:
        return {
            "verdict": "GREEN",
            "action": action,
            "confidence": "HIGH",
            "reason": reason,
            "sl_points": 27,
            "target_points": 45,
            "flags": flags
        }

    def _red_response(self, reason: str, flags: Dict) -> Dict:
        return {
            "verdict": "RED",
            "action": "BLOCK",
            "confidence": "MEDIUM",
            "reason": reason,
            "sl_points": 0,
            "target_points": 0,
            "flags": flags
        }

    def _yellow_response(self, reason: str, flags: Dict = None) -> Dict:
        return {
            "verdict": "YELLOW",
            "action": "WAIT",
            "confidence": "LOW",
            "reason": reason,
            "sl_points": 0,
            "target_points": 0,
            "flags": flags or {}
        }

def get_composite_scalp_view(symbol: str, timeframe: int, df: pd.DataFrame, chain_df: pd.DataFrame) -> Dict:
    """
    Main orchestrator for Scalp Lab.
    """
    engine = InstantDecisionEngine()
    
    # Extract OI walls from chain_df
    nearest_ce_wall = 999999
    nearest_pe_wall = 0
    if chain_df is not None and not chain_df.empty:
        spot = float(df.iloc[-1]["close"])
        # Find strikes with max OI
        calls = chain_df[chain_df["right"].str.upper().isin(["CALL", "CE"])]
        puts = chain_df[chain_df["right"].str.upper().isin(["PUT", "PE"])]
        
        if not calls.empty:
            ce_max_oi_strike = calls.sort_values("open_interest", ascending=False).iloc[0]["strike_price"]
            nearest_ce_wall = float(ce_max_oi_strike or 999999)
        if not puts.empty:
            pe_max_oi_strike = puts.sort_values("open_interest", ascending=False).iloc[0]["strike_price"]
            nearest_pe_wall = float(pe_max_oi_strike or 0)

    oi_data = {"nearest_ce_wall": nearest_ce_wall, "nearest_pe_wall": nearest_pe_wall}
    
    # 1. Get Instant Decision
    decision = engine.get_instant_decision(symbol, timeframe, df, oi_data)
    
    # 2. Get Levels
    levels = LevelEngine.get_levels(df)
    
    # 3. Strike Recommendation
    strike_info = get_strike_recommendation(decision, symbol, df.iloc[-1]["close"])
    
    return {
        "decision": decision,
        "levels": levels,
        "strike": strike_info,
        "timestamp": datetime.now().isoformat()
    }

def get_strike_recommendation(decision: Dict, symbol: str, spot: float) -> Dict:
    """Suggests strikes only if verdict is GREEN."""
    if decision["verdict"] != "GREEN":
        return {"action": "WAIT", "strike": "N/A"}
        
    # Standard Nifty/BankNifty strike step
    step = 50 if symbol.upper() == "NIFTY" else 100
    atm_strike = round(spot / step) * step
    
    action = decision["action"] # "BUY CE" or "BUY PE"
    if action == "BUY CE":
        # 1 ITM
        suggested = atm_strike - step
    else:
        # 1 ITM
        suggested = atm_strike + step
        
    return {
        "action": action,
        "strike": f"{symbol} {int(suggested)} {action.split()[-1]}"
    }
