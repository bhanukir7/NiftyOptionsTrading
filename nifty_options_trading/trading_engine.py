"""
trading_engine.py

Autonomous Trading Engine that runs the unified trading loop.
Handles market stream, signal generation (Technical + Max Pain), 
and execution (Paper vs Live).

Author: Aditya Kota
"""
import os
import time
import threading
import logging
from datetime import datetime, time as dt_time
from collections import deque
from typing import Dict, List, Optional, Literal, Tuple

import pandas as pd
from nifty_options_trading.safe_breeze import SafeBreeze
from nifty_options_trading.market_stream import MarketStream
from nifty_options_trading.strategy import analyze_and_generate_signal
from nifty_options_trading.maxpain_strategy import MaxPainStrategy
from nifty_options_trading.rule_engine import (
    StateManager, Config, determine_bias, can_trade, Position,
    validate_entry, calculate_position_size, can_take_new_trade_time, manage_trade, update_profit, update_loss
)
from nifty_options_trading.options_engine import get_option_chain, get_expiries
from nifty_options_trading.max_pain import calculate_max_pain
from nifty_options_trading.alerts import send_alert
from nifty_options_trading.breakout_strategy import BreakoutStrategy, MarketData
from nifty_options_trading.advanced_strategy import AdvancedBreakoutStrategy, MarketData as AdvMarketData
from nifty_options_trading.global_cues import fetch_world_markets

class AutonomousEngine:
    """
    The central brain of the dashboard that runs the background trading loop.
    """
    def __init__(self, breeze: SafeBreeze, stock_codes: Optional[List[str]] = None):
        self.breeze = breeze
        self.state = StateManager()
        self.config = Config()
        self.stream = MarketStream(breeze)
        self.maxpain_strat = MaxPainStrategy()
        self.breakout_strat = BreakoutStrategy()
        self.adv_strat = AdvancedBreakoutStrategy()
        
        self._is_running = False
        self._thread = None
        self.logs = deque(maxlen=50) # Keep last 50 log entries for the UI

        # Resolve stock codes: Argument > Environment > Defaults
        if stock_codes:
            self.stock_codes = [s.upper() for s in stock_codes]
        else:
            env_stocks = os.getenv("STOCK_CODES")
            if env_stocks:
                self.stock_codes = [s.strip().upper() for s in env_stocks.split(",") if s.strip()]
            else:
                self.stock_codes = ["NIFTY", "CNXBAN"] # Default fallback
                
        self.exchange = "NSE"
        self.last_signal = {"timestamp": None, "signal": "NONE", "reason": "System Idle"}
        
    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.logs.append(entry)
        print(entry)

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self.stream.subscribe(self.stock_codes)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log("Autonomous Engine Started.")

    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.stream.disconnect()
        self.log("Autonomous Engine Stopped.")

    def _run_loop(self):
        last_60s = time.time() - 60
        last_5s = time.time()
        
        while self._is_running:
            try:
                now = time.time()
                
                # 1. Active Trade Management (Every 5s)
                if now - last_5s >= 5:
                    last_5s = now
                    if self.state.active_positions:
                        self._manage_active_positions()

                # 2. Scanning Loop (Every 300s / 5m)
                if now - last_60s >= 300:
                    last_60s = now
                    self._scan_opportunities()

                # 3. Forced EOD Exit (After 15:20)
                if datetime.now().time() >= dt_time(15, 20):
                    if self.state.active_positions:
                        self.log("Forced EOD exit triggered at 15:20.")
                        symbols_to_close = list(self.state.active_positions.keys())
                        for symbol in symbols_to_close:
                            pos = self.state.active_positions[symbol]
                            current_price = self.stream.get_price(symbol) or pos.entry_price
                            self._finalize_trade(symbol, "Forced EOD exit", (current_price - pos.entry_price) * pos.qty)

                time.sleep(1)
            except Exception as e:
                self.log(f"CRITICAL ENGINE ERROR: {e}")
                time.sleep(10)

    def _manage_active_positions(self):
        closed_symbols = []
        for symbol, pos in self.state.active_positions.items():
            current_spot = self.stream.get_price(symbol)
            if not current_spot: continue
            
            is_closed, reason, real_pnl = manage_trade(pos, current_spot, self.state, self.config)
            
            if is_closed:
                closed_symbols.append((symbol, reason, real_pnl))
            elif reason.startswith("Partial"):
                self.log(f"[{symbol}] Partial profit booked: {reason}")
                send_alert(f"🎯 **PARTIAL PROFIT [{symbol}]**\n{reason}\nPnL: ₹{real_pnl:.2f}")
                
        for symbol, reason, real_pnl in closed_symbols:
            self._finalize_trade(symbol, reason, real_pnl)

    def _scan_opportunities(self):
        # Allow multiple concurrent scans for observability
        # We process symbols for the Signal Hub even if can_trade() or can_take_new_trade_time() is False
        for symbol in self.stock_codes:
            if symbol in self.state.active_positions:
                continue # Already in a trade for this symbol
            self._analyze_symbol(symbol)

    def _analyze_symbol(self, symbol: str):
        try:
            # 1. Fetch Technical Data (from 5min historical)
            today_start = datetime.now().strftime("%Y-%m-%dT00:00:00.000Z")
            hist_res = self.breeze.get_historical_data(
                interval="5minute", 
                from_date=today_start,
                to_date=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                stock_code=symbol,
                exchange_code=self.exchange,
                product_type="cash"
            )
            if not hist_res or hist_res.get("Status") != 200 or not hist_res.get("Success"): return
            
            df = pd.DataFrame(hist_res["Success"])
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=["close"], inplace=True)
            
            spot = self.stream.get_price(symbol) or df.iloc[-1]["close"]
            vwap = df["close"].mean()
            
            # Indicators for Bias
            df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
            df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
            ema21 = df["ema21"].iloc[-1]
            ema50 = df["ema50"].iloc[-1]
            
            # MACD
            exp1 = df["close"].ewm(span=12, adjust=False).mean()
            exp2 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd_line"] = exp1 - exp2
            df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
            macd_val = df["macd_line"].iloc[-1]
            macd_sig = df["macd_signal"].iloc[-1]
            
            # Chop Index (Simplified)
            df["tr"] = (df["high"] - df["low"])
            df["atr"] = df["tr"].rolling(14).mean()
            atr = df["atr"].iloc[-1]
            df["std20"] = df["close"].rolling(20).std()
            chop_val = 60 if (df["std20"].iloc[-1] < atr * 1.5) else 40
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi_val = 50
            if not loss.empty and loss.iloc[-1] != 0:
                rs = gain / loss
                rsi_val = 100 - (100 / (1 + rs.iloc[-1]))

            # Fetch VIX
            world_data = fetch_world_markets()
            vix_pct = 0.0
            if world_data and world_data.get("markets"):
                for m in world_data["markets"]:
                    if m["name"] == "INDIA VIX":
                        vix_pct = m.get("last", 15.0) # Using 'last' as price
                        break
            
            # Prepare Indicators for Scoring
            indicators = {
                "macd_hist": macd_val - macd_sig,
                "ema_alignment": spot > ema21 > ema50,
                "price_above_bb": False, # Placeholder for BB logic
                "rsi": rsi_val,
                "rsi_extreme": rsi_val > 70 or rsi_val < 30,
                "bb_reversal": False,
                "maxpain_distance": 100 # Placeholder
            }
            
            decision_data = {
                "symbol": symbol,
                "spot": spot,
                "vwap": vwap,
                "ema21": ema21,
                "ema50": ema50,
                "macd": macd_val,
                "macd_signal": macd_sig,
                "chop": chop_val,
                "atr": atr,
                "vix": vix_pct,
                "indicators": indicators
            }
            
            result = self.evaluate_trade_decision(decision_data)
            
            # --- SIGNAL HUB INTEGRATION ---
            # Construct levels (using simple high/low or placeholders for now)
            resistance = df["high"].max()
            support = df["low"].min()
            
            # Estimate IV from ATR proxy (annualised)
            # sqrt(75 bars/day * 252 days/year) approx 137.5
            iv_estimate = (atr / spot) * 137.5 * 100 if spot > 0 else 0
            
            adv_data = AdvMarketData(
                symbol=symbol,
                price=spot,
                resistance=resistance,
                support=support,
                atr=atr,
                chop=chop_val,
                bb_upper=0, bb_lower=0, # placeholders
                macd=macd_val,
                macd_signal=macd_sig,
                pcr=1.0, # Placeholder
                call_oi=0, put_oi=0, # placeholders
                iv=iv_estimate
            )
            self.adv_strat.detect_state(adv_data)
            
            if result["decision"] == "NO_TRADE":
                self.log(f"Scan {symbol}: NO_TRADE - {result['reason']}")
                return

            self.log(f"DECISION ENGINE: {result['decision']} on {symbol} (Score: {result['score']}, Regime: {result['regime']})")
            
            # Strategy Router Integration
            if result["regime"] == "TREND":
                # 1. Check Breakout Strategy
                # (We'd need to restore support/resistance calculation here if needed)
                # For brevity and following the requested 'simple' orchestrator flow,
                # we will use the technical alignment as the primary TREND trigger.
                
                tech_signal = "HOLD"
                if macd_val > macd_sig and spot > ema21: tech_signal = "BUY_CALL"
                elif macd_val < macd_sig and spot < ema21: tech_signal = "BUY_PUT"

                if tech_signal != "HOLD":
                    sig = {
                        "signal": "BUY_CE" if tech_signal == "BUY_CALL" else "BUY_PE",
                        "reason": f"Trend Alignment (Score: {result['score']})",
                        "regime": result["regime"],
                        "bias": result["bias"],
                        "score": result["score"],
                        "conviction": result["signal"],
                        "atr": atr,
                        "vix": vix_pct
                    }
                    self._execute_signal(symbol, sig)
                
            elif result["regime"] == "RANGE":
                # Only MaxPain
                self.log(f"RANGE Regime on {symbol}. Strategy: MAXPAIN.")
                # (Max Pain logic call here)
                pass

        except Exception as e:
            self.log(f"Error analyzing {symbol}: {e}")
    def evaluate_trade_decision(self, data: dict):
        """
        Master Orchestrator Pipeline:
        DATA → REGIME → BIAS → STRATEGY → SCORING → RISK → EXECUTION
        """
        symbol = data["symbol"]
        spot = data["spot"]
        chop = data["chop"]
        atr = data["atr"]
        macd = data["macd"]
        macd_signal = data["macd_signal"]
        vix = data.get("vix", 15.0)
        
        # 1. REGIME DETECTION
        regime = self.detect_regime(chop, atr, macd, macd_signal)
        if regime == "NO_TRADE":
            return {"decision": "NO_TRADE", "reason": f"Chop ({chop}) indicates no clear regime."}

        # 2. VOLATILITY FILTER
        if vix > self.config.vix_threshold:
             # Part 3: If high IV, switch to spreads or reject buying
             # For now, we'll flag it or reject if buying
             pass 

        # 3. HIGHER TIMEFRAME BIAS
        bias = self.get_htf_bias(spot, data["vwap"], data["ema21"], data["ema50"])
        self.state.current_bias = bias
        
        # 4. STRATEGY ROUTER
        strategy_type = ""
        if regime == "RANGE":
            strategy_type = "MAXPAIN"
        elif regime == "TREND":
            strategy_type = "TREND_FOLLOWING" # Breakout or Tech
        
        # 5. ADAPTIVE SCORING
        score = self.compute_score(data["indicators"], regime)
        
        # 6. SIGNAL CLASSIFICATION
        signal_conviction = "NO_TRADE"
        if score >= 70:
            signal_conviction = "HIGH_CONVICTION"
        elif score >= 50:
            signal_conviction = "MEDIUM"
        else:
            return {"decision": "NO_TRADE", "reason": f"Low score: {score}"}

        # 7. FINAL FILTERS
        # Consecutive losses filter
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
             return {"decision": "NO_TRADE", "reason": "Max consecutive losses reached."}

        return {
            "decision": "EXECUTE",
            "regime": regime,
            "bias": bias,
            "score": score,
            "signal": signal_conviction,
            "strategy": strategy_type
        }

    def detect_regime(self, chop, atr, macd, macd_signal):
        threshold = 0.5 # MACD threshold
        if chop > 55:
            return "RANGE"
        elif chop < 35 and abs(macd - macd_signal) > threshold:
            return "TREND"
        else:
            return "NO_TRADE"

    def get_htf_bias(self, price, vwap, ema21, ema50):
        if price > vwap and ema21 > ema50:
            return "BULLISH"
        elif price < vwap and ema21 < ema50:
            return "BEARISH"
        return "NEUTRAL"

    def compute_score(self, indicators, regime):
        score = 0
        if regime == "TREND":
            if indicators.get("macd_hist", 0) > 0: score += 30
            if indicators.get("ema_alignment", False): score += 20
            if indicators.get("price_above_bb", False): score += 15
            if indicators.get("rsi", 50) > 55: score += 10
        elif regime == "RANGE":
            if indicators.get("rsi_extreme", False): score += 25
            if indicators.get("bb_reversal", False): score += 25
            if indicators.get("maxpain_distance", 0) < 50: score += 20
        return score

    def _execute_signal(self, symbol: str, signal_data: Dict):
        # Safety Check: only trade during allowed hours and if engine state allows
        allowed_state, reason = can_trade(self.state, self.config)
        if not allowed_state:
            self.log(f"Trade blocked: {reason}")
            return
            
        if not can_take_new_trade_time():
            self.log(f"Trade blocked: Market hours closed.")
            return

        opt_type = "CE" if signal_data["signal"] == "BUY_CE" else "PE"
        spot = self.stream.get_price(symbol)
        
        # Risk Check
        intraday_pct = signal_data.get("intraday_pct", 0.5)
        regime = signal_data.get("regime", "TREND")
        
        # --- FINAL TRADE FILTER GATE (Part 10) ---
        if signal_data.get("conviction") == "NO_TRADE":
            self.log(f"Rejected: Low conviction signal")
            return

        if opt_type == "CE" and signal_data.get("bias") != "BULLISH":
             self.log(f"Rejected: Bias mismatch (CE requires BULLISH, got {signal_data.get('bias')})")
             return
        if opt_type == "PE" and signal_data.get("bias") != "BEARISH":
             self.log(f"Rejected: Bias mismatch (PE requires BEARISH, got {signal_data.get('bias')})")
             return
             
        if regime == "RANGE" and opt_type in ["CE", "PE"] and "MAXPAIN" not in signal_data.get("reason", ""):
             # If it's a directional breakout in a range regime, reject
             self.log("Rejected: Regime mismatch (Directional trade blocked in RANGE regime)")
             return

        # Time Filter Gate
        curr_time_str = datetime.now().strftime("%H:%M")
        if curr_time_str < "09:30" or curr_time_str > "14:45":
             self.log(f"Rejected: Time filter gate ({curr_time_str} outside 09:30-14:45)")
             return

        # Daily Profit Target / Consecutive Losses (already handled in evaluate_trade_decision or can_trade)
        
        valid, reason = validate_entry(opt_type, self.state.current_bias, 0.5, self.config)
        if not valid:
            self.log(f"Rejected: Validation layer: {reason}")
            return

        # Create Position using Premium and ATR-based Expected Move (Part 12)
        premium = spot # In production, fetch actual option LTP
        from nifty_options_trading.options_engine import get_dynamic_lot_size
        lot_size = get_dynamic_lot_size(symbol)
        
        atr = signal_data.get("atr", 10.0)
        expected_move_ratio = atr / spot if spot > 0 else 0.05
        
        qty, risk, _, _ = calculate_position_size(50000, premium, atr, lot_size, self.config)
        
        if opt_type == "CE":
            sl = premium * (1 - expected_move_ratio * 0.8)
            target = premium * (1 + expected_move_ratio * 2.0)
        else:
            sl = premium * (1 + expected_move_ratio * 0.8)
            target = premium * (1 - expected_move_ratio * 2.0)
        
        pos = Position(
            type=opt_type, 
            entry_price=premium, 
            qty=qty, 
            sl_price=sl, 
            target_price=target
        )
        self.state.active_positions[symbol] = pos
        self.state.trades_today += 1
        self.state.last_trade_time = datetime.now()
        
        mode = "LIVE (BETA)" if not self.config.paper_trade else "PAPER TRADE"
        conviction = signal_data.get("conviction", "UNKNOWN")
        score = signal_data.get("score", 0)
        
        msg = (f"🚀 **ENGINE ENTRY Executed ({mode})**\n"
               f"Symbol: {symbol} | Type: {opt_type}\n"
               f"Conviction: {conviction} (Score: {score})\n"
               f"Entry: {spot:.2f} | Qty: {qty}\n"
               f"Reason: {signal_data['reason']}")
        
        self.log(f"ENTRY [{conviction}]: {opt_type} at {spot:.2f} (Score: {score})")
        send_alert(msg)

    def _finalize_trade(self, symbol: str, reason: str, pnl: float):
        if pnl > 0: update_profit(self.state, pnl)
        else: update_loss(self.state, pnl)
        
        self.log(f"TRADE CLOSED [{symbol}]: {reason} | PnL: ₹{pnl:.2f}")
        
        mode = "LIVE (BETA)" if not self.config.paper_trade else "PAPER TRADE"
        msg = (f"🛑 **ENGINE EXIT [{symbol}] ({mode})**\n"
               f"Reason: {reason}\n"
               f"Realized PnL: ₹{pnl:.2f}\n"
               f"Daily PnL: ₹{self.state.daily_pnl:.2f}")
        send_alert(msg)
        if symbol in self.state.active_positions:
            del self.state.active_positions[symbol]
        self.breakout_strat.reset_state(symbol)
