"""
backtester.py
Full hedge-fund style backtesting validation layer.
"""
import pandas as pd
import numpy as np
from datetime import datetime

class Backtester:
    def __init__(self, commission_per_lot=20.0, slippage_pct=0.0005):
        self.commission_per_lot = commission_per_lot
        self.slippage_pct = slippage_pct
        self.results = []

    def run_backtest(self, df: pd.DataFrame, orchestrator):
        """
        Runs the backtest loop over historical data.
        orchestrator: An instance of AutonomousEngine or a mock with evaluate_trade_decision.
        """
        self.results = []
        active_trade = None
        
        # Ensure indicators are present in df
        # (Assuming df has columns needed by orchestrator)
        
        for i in range(50, len(df)):
            row = df.iloc[i]
            timestamp = row.get("datetime", i)
            
            if active_trade:
                # Manage active trade
                current_price = row["close"]
                # Simplified management logic
                if current_price >= active_trade["target"] or current_price <= active_trade["sl"]:
                    # Exit
                    exit_price = current_price
                    pnl = (exit_price - active_trade["entry"]) if active_trade["type"] == "CE" else (active_trade["entry"] - exit_price)
                    
                    # Deduct slippage and brokerage
                    pnl -= (exit_price * self.slippage_pct)
                    pnl -= (self.commission_per_lot / active_trade["qty"]) # simplified
                    
                    active_trade["exit_price"] = exit_price
                    active_trade["pnl"] = pnl * active_trade["qty"]
                    active_trade["exit_time"] = timestamp
                    self.results.append(active_trade)
                    active_trade = None
                continue

            # Check for new trade
            data = self._prepare_data(df, i)
            decision = orchestrator.evaluate_trade_decision(data)
            
            if decision["decision"] == "EXECUTE":
                # Entry
                entry_price = row["close"] * (1 + self.slippage_pct)
                atr = data["atr"]
                
                active_trade = {
                    "type": "CE" if decision["bias"] == "BULLISH" else "PE",
                    "entry": entry_price,
                    "qty": 50, # fixed for backtest
                    "target": entry_price + (atr * 2) if decision["bias"] == "BULLISH" else entry_price - (atr * 2),
                    "sl": entry_price - (atr * 0.8) if decision["bias"] == "BULLISH" else entry_price + (atr * 0.8),
                    "entry_time": timestamp,
                    "regime": decision["regime"],
                    "score": decision["score"]
                }

        return self.compute_metrics()

    def _prepare_data(self, df, idx):
        # Helper to prepare the same data structure as _analyze_symbol
        subset = df.iloc[:idx+1]
        spot = subset.iloc[-1]["close"]
        # Simplified indicator calculation for backtest
        return {
            "symbol": "BACKTEST",
            "spot": spot,
            "vwap": subset["close"].mean(),
            "ema21": subset["close"].ewm(span=21).mean().iloc[-1],
            "ema50": subset["close"].ewm(span=50).mean().iloc[-1],
            "macd": 0, # placeholder
            "macd_signal": 0, # placeholder
            "chop": 40, # placeholder
            "atr": subset["close"].diff().abs().rolling(14).mean().iloc[-1],
            "vix": 15.0,
            "indicators": {"macd_hist": 1, "ema_alignment": True}
        }

    def compute_metrics(self):
        if not self.results:
            return {"status": "No trades executed"}

        res_df = pd.DataFrame(self.results)
        wins = res_df[res_df["pnl"] > 0]
        losses = res_df[res_df["pnl"] <= 0]
        
        total_pnl = res_df["pnl"].sum()
        win_rate = len(wins) / len(res_df) if len(res_df) > 0 else 0
        avg_win = wins["pnl"].mean() if not wins.empty else 0
        avg_loss = abs(losses["pnl"].mean()) if not losses.empty else 1
        profit_factor = (wins["pnl"].sum()) / abs(losses["pnl"].sum()) if not losses.empty and losses["pnl"].sum() != 0 else np.inf
        
        max_drawdown = (res_df["pnl"].cumsum().cummax() - res_df["pnl"].cumsum()).max()
        
        # Validation
        is_valid = profit_factor > 1.5 and max_drawdown < 10000 # example limit
        
        return {
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "is_valid": is_valid,
            "trades_count": len(res_df),
            "regime_performance": res_df.groupby("regime")["pnl"].sum().to_dict()
        }
