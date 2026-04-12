"""
maxpain_strategy.py

Implements a buyer-side trading strategy that mimics option sellers.
Logic: Buy calls near support (Put OI wall) and puts near resistance (Call OI wall),
targeting a mean-reversion to Max Pain.

Author: Aditya Kota
"""
from typing import Dict, List, Optional
import pandas as pd

class MaxPainStrategy:
    """
    Stateless strategy engine that evaluates Max Pain and OI walls to generate 
    mean-reversion signals.
    """

    def generate_signal(self, 
                        spot_price: float, 
                        oi_chain: List[Dict], 
                        max_pain: float,
                        global_bias: str, 
                        dte: int) -> Dict:
        """
        Generates a trading signal based on Max Pain and OI concentration.
        
        Input Format (oi_chain): List of { "strike": float, "call_oi": float, "put_oi": float, 
                                          "call_oi_change": float, "put_oi_change": float }
        """
        if not oi_chain or spot_price <= 0 or max_pain <= 0:
            return self._no_trade("Insufficient data for analysis")

        df = pd.DataFrame(oi_chain)
        
        # 1. Identify OI Walls (Top 3 by absolute OI)
        top_calls = df.nlargest(3, 'call_oi').sort_values('strike')
        top_puts = df.nlargest(3, 'put_oi').sort_values('strike')
        
        resistance = top_calls['strike'].iloc[-1] # Highest major call wall
        support = top_puts['strike'].iloc[0]      # Lowest major put wall
        
        # 2. Basic Distance Rules
        dist_from_max_pain = spot_price - max_pain
        
        # Rule: NO TRADE if price within ±50 of max pain (Too close to target)
        if abs(dist_from_max_pain) < 50:
            return self._no_trade("Price is within noise zone of Max Pain (±50 pts)")

        # 3. Detect Unwinding (Negative OI Change at walls)
        is_call_unwinding = any(top_calls['call_oi_change'] < 0)
        is_put_unwinding = any(top_puts['put_oi_change'] < 0)

        signal = "NO_TRADE"
        reason = ""
        confidence = 0
        
        # ── BUY_PE LOGIC (Mean Reversion Down to Max Pain) ──────────────────
        # Conditions: Price significantly above Max Pain and near resistance
        if dist_from_max_pain >= 80:
            near_resistance = (resistance - spot_price) <= 100
            if near_resistance:
                if not is_call_unwinding:
                    signal = "BUY_PE"
                    reason = f"Price ({spot_price:.0f}) is {dist_from_max_pain:.0f} pts above Max Pain ({max_pain:.0f}) and near Resistance ({resistance:.0f})."
                else:
                    reason = f"Resistance wall at {resistance} is unwinding. Avoiding PE."

        # ── BUY_CE LOGIC (Mean Reversion Up to Max Pain) ────────────────────
        # Conditions: Price significantly below Max Pain and near support
        elif dist_from_max_pain <= -80:
            near_support = (spot_price - support) <= 100
            if near_support:
                if not is_put_unwinding:
                    signal = "BUY_CE"
                    reason = f"Price ({spot_price:.0f}) is {abs(dist_from_max_pain):.0f} pts below Max Pain ({max_pain:.0f}) and near Support ({support:.0f})."
                else:
                    reason = f"Support wall at {support} is unwinding. Avoiding CE."

        if signal == "NO_TRADE":
            return self._no_trade(reason or "No clear OI mean-reversion setup detected.")

        # ── 4. Confidence Score Calculation ───────────────────────────────
        confidence = 0
        # +30 if far from max pain (>100 pts)
        if abs(dist_from_max_pain) > 100:
            confidence += 30
        
        # +20 strong OI cluster (Wall OI > 2x average OI)
        avg_oi = df['call_oi'].mean() + df['put_oi'].mean()
        wall_oi = top_calls['call_oi'].max() if signal == "BUY_PE" else top_puts['put_oi'].max()
        if wall_oi > (avg_oi * 1.5):
            confidence += 20
            
        # +10 bias alignment
        if (signal == "BUY_CE" and global_bias == "BULLISH") or (signal == "BUY_PE" and global_bias == "BEARISH"):
            confidence += 10
            
        # +10 PCR Neutrality (Mean reversion works best in non-trending markets)
        total_calls = df['call_oi'].sum()
        total_puts = df['put_oi'].sum()
        pcr = total_puts / total_calls if total_calls > 0 else 1.0
        if 0.9 <= pcr <= 1.1:
            confidence += 10

        # Targets and SL
        results = {
            "signal": signal,
            "confidence": min(confidence + 30, 100), # Base confidence 30
            "entry_zone": [spot_price - 5, spot_price + 5],
            "targets": {
                "t1": max_pain,
                "t2": support if signal == "BUY_PE" else resistance
            },
            "stop_loss": -25.0, # -25% premium
            "reason": reason
        }
        
        return results

    def _no_trade(self, reason: str) -> Dict:
        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": reason,
            "targets": {"t1": 0, "t2": 0},
            "stop_loss": 0
        }
