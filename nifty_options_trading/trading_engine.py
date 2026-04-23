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
from datetime import datetime, time
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

                # 2. Scanning Loop (Every 60s)
                if now - last_60s >= 60:
                    last_60s = now
                    self._scan_opportunities()

                # 3. Forced EOD Exit (After 15:20)
                if datetime.now().time() >= time(15, 20):
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
        # 1. Fetch Technical Data (from 5min historical)
        try:
            # Add day_open fetch
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
            
            day_open = df.iloc[0]["open"]
            spot = self.stream.get_price(symbol) or df.iloc[-1]["close"]
            vwap = df["close"].mean() # Simplified
            
            # New: EMA21 and EMA50 for Bias
            df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
            df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
            ema21 = df["ema21"].iloc[-1]
            ema50 = df["ema50"].iloc[-1]
            
            bias = determine_bias(spot, vwap, ema21, ema50)
            self.state.current_bias = bias
            
            # 1. ATR (Average True Range)
            df["tr"] = (df["high"] - df["low"])
            df["atr"] = df["tr"].rolling(14).mean()
            atr = df["atr"].iloc[-1]
            atr_prev = df["atr"].iloc[-2] if len(df) > 1 else atr
            
            # 3. MACD
            exp1 = df["close"].ewm(span=12, adjust=False).mean()
            exp2 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd_line"] = exp1 - exp2
            df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
            macd_val = df["macd_line"].iloc[-1]
            macd_sig = df["macd_signal"].iloc[-1]
            
            # 4. Chop Index (Simplified Proxy)
            df["std20"] = df["close"].rolling(20).std()
            chop_val = 60 if (df["std20"].iloc[-1] < atr * 1.5) else 40
            
            # Market Regime Detection
            regime = self.detect_market_regime(chop_val, atr, atr_prev, macd_val, macd_sig)
            
            # New: Technical indicators for scoring
            bb_mid = df["sma20"].iloc[-1] if 'sma20' in df.columns else spot
            macd_hist = df["macd_line"].iloc[-1] - df["macd_signal"].iloc[-1]
            
            # Intraday Move Validation
            intraday_pct = abs((spot - day_open) / day_open) * 100
            if 35 <= chop_val <= 45:
                self.log(f"NO TRADE ZONE: Chop index {chop_val} is in the unclear range (35-45). Skipping {symbol}.")
                return

            # Strategy Selection Layer
            if regime == "NO_TRADE":
                return
                
            if regime == "RANGE":
                # ONLY use MaxPainStrategy
                self.log(f"Market Regime: RANGE on {symbol}. Using Max Pain only.")
                expiries = get_expiries(symbol, "CE")
                if not expiries: return
                expiry = expiries[0].strftime("%Y-%m-%d")
                chain_df = get_option_chain(self.breeze, symbol, expiry)
                if chain_df is not None and not chain_df.empty:
                    max_pain = calculate_max_pain(chain_df)
                    # Simple placeholder for Max Pain signal integration
                    # In a real scenario, we'd call maxpain_strat.generate_signal()
                    pass
                return

            # TREND regime: allow Breakout and Technical
            self.log(f"Market Regime: TREND on {symbol}. Allowing Breakout/Technical.")
            
            # Fetch options chain to satisfy Breakout Logic requirements
            expiries = get_expiries(symbol, "CE")
            if not expiries: return
            expiry = expiries[0].strftime("%Y-%m-%d")
            chain_res = get_option_chain(self.breeze, symbol, expiry)
            
            call_oi, put_oi, pcr = 0, 0, 1.0
            if chain_res is not None and not chain_res.empty:
                call_oi = chain_res[chain_res["right"].str.upper().isin(["CALL", "CE"])]["open_interest"].sum()
                put_oi  = chain_res[chain_res["right"].str.upper().isin(["PUT", "PE"])]["open_interest"].sum()
                pcr = put_oi / call_oi if call_oi > 0 else 1.0
            
            iv = 15 # Default
            if chain_res is not None and not chain_res.empty:
                # Breeze sometimes returns 'iv' or 'implied_volatility'
                iv_col = None
                if "iv" in chain_res.columns:
                    iv_col = "iv"
                elif "implied_volatility" in chain_res.columns:
                    iv_col = "implied_volatility"
                
                if iv_col:
                    iv = pd.to_numeric(chain_res[iv_col], errors='coerce').head(5).mean() or 15

            # Feed Breakout Strategy
            market_data = MarketData(
                symbol=symbol, price=spot, resistance=resistance, support=support,
                atr=atr, chop=chop_val, bb_upper=bb_upper if 'bb_upper' in locals() else spot*1.01, 
                bb_lower=bb_lower if 'bb_lower' in locals() else spot*0.99,
                macd=macd_val, macd_signal=macd_sig, pcr=pcr, call_oi=call_oi, put_oi=put_oi, iv=iv
            )
            
            # Feed Advanced Strategy for Signal Hub observability
            adv_data = AdvMarketData(
                symbol=symbol, price=spot, resistance=resistance, support=support,
                atr=atr, chop=chop_val, bb_upper=bb_upper, bb_lower=bb_lower,
                macd=macd_val, macd_signal=macd_sig, pcr=pcr, call_oi=call_oi, put_oi=put_oi,
                call_oi_change=0, put_oi_change=0, iv=iv, volume=df.iloc[-1]["volume"] if "volume" in df.columns else 0
            )
            self.adv_strat.detect_state(adv_data)
            self.adv_strat.check_entry(adv_data)
            
            action = self.breakout_strat.process_tick(market_data, spot)
            if action and action["action"] == "ENTER":
                score, conviction = self.calculate_signal_score(df, spot, ema21, bb_mid, macd_hist, chop_val)
                if conviction == "NO_TRADE":
                    self.log(f"Rejected: Low score ({score}) for breakout on {symbol}")
                    return

                self.log(f"BREAKOUT STRATEGY SIGNAL: {action['type']} on {symbol} (Score: {score})")
                sig = {
                    "signal": f"BUY_{action['type']}",
                    "reason": action["reason"],
                    "target": spot + (atr * 1.5) if action['type'] == "CE" else spot - (atr * 1.5),
                    "stop_loss": spot - (atr * 0.5) if action['type'] == "CE" else spot + (atr * 0.5),
                    "regime": regime,
                    "intraday_pct": intraday_pct,
                    "score": score,
                    "conviction": conviction,
                    "atr": atr
                }
                self._execute_signal(symbol, sig)
                return

            # Keep Technical Strategy Fallback if breakout doesn't trigger
            tech_signal = analyze_and_generate_signal(df)
            if tech_signal != "HOLD":
                score, conviction = self.calculate_signal_score(df, spot, ema21, bb_mid, macd_hist, chop_val)
                if conviction == "NO_TRADE":
                    self.log(f"Rejected: Low score ({score}) for technical on {symbol}")
                    return

                self.log(f"TECHNICAL SIGNAL: {tech_signal} on {symbol} (Score: {score})")
                sig = {
                    "signal": "BUY_CE" if tech_signal == "BUY_CALL" else "BUY_PE",
                    "reason": "EMA Cross + MACD Alignment",
                    "target": spot + (atr * 1.5) if tech_signal == "BUY_CALL" else spot - (atr * 1.5),
                    "stop_loss": spot - (atr * 0.5) if tech_signal == "BUY_CALL" else spot + (atr * 0.5),
                    "regime": regime,
                    "intraday_pct": intraday_pct,
                    "score": score,
                    "conviction": conviction,
                    "atr": atr
                }
                self._execute_signal(symbol, sig)

        except Exception as e:
            self.log(f"Error analyzing {symbol}: {e}")

    def detect_market_regime(self, chop, atr, atr_prev, macd, macd_signal):
        threshold = 0.5 # MACD threshold
        if chop > 55:
            return "RANGE"
        elif abs(macd - macd_signal) > threshold and atr > atr_prev:
            return "TREND"
        else:
            return "NO_TRADE"

    def calculate_signal_score(self, df: pd.DataFrame, spot: float, ema21: float, bb_mid: float, macd_hist: float, chop: float) -> Tuple[int, str]:
        score = 0
        
        # 1. MACD Histogram (25 pts)
        if macd_hist > 0: score += 25
        
        # 2. Bollinger Mid (15 pts)
        if spot > bb_mid: score += 15
        
        # 3. RSI (15 pts)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 50 # fallback
        if not loss.empty and loss.iloc[-1] != 0:
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))
        if rsi > 55: score += 15
        
        # 4. Low Chop (15 pts)
        if chop < 38: score += 15
        
        # 5. EMA 21 (10 pts)
        if spot > ema21: score += 10
        
        # 6. Volume Spike (20 pts)
        avg_vol = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df.columns else 1
        last_vol = df['volume'].iloc[-1] if 'volume' in df.columns else 0
        if last_vol > avg_vol * 1.5: score += 20
        
        conviction = "NO_TRADE"
        if score >= 70: conviction = "HIGH_CONVICTION"
        elif score >= 50: conviction = "MEDIUM"
        
        return score, conviction

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
        
        # --- FINAL TRADE FILTER GATE ---
        if opt_type == "CE" and self.state.current_bias != "BULLISH":
             self.log("Rejected: HTF mismatch (CE needs BULLISH bias)")
             return
        if opt_type == "PE" and self.state.current_bias != "BEARISH":
             self.log("Rejected: HTF mismatch (PE needs BEARISH bias)")
             return
             
        if regime == "RANGE" and "BREAKOUT" in signal_data["signal"]:
             self.log("Rejected: Regime mismatch (Breakout blocked in RANGE)")
             return

        # OTM Distance Filter (Simulated)
        # Assuming ATM strike is close to spot. If distance > 150, reject.
        # In a real scenario, we'd check the specific contract's strike.
        strike_dist = 0 # simplified
        if strike_dist > self.config.max_strike_distance:
            self.log(f"Rejected: OTM too far ({strike_dist} pts)")
            return

        valid, reason = validate_entry(opt_type, self.state.current_bias, intraday_pct, self.config)
        if not valid:
            self.log(f"Rejected: Risk/Time limits: {reason}")
            return

        # Create Position using Premium and ATR-based SL/Target
        premium = spot # In production, fetch actual option LTP
        from nifty_options_trading.options_engine import get_dynamic_lot_size
        lot_size = get_dynamic_lot_size(symbol)
        
        # Fetch ATR for position sizing
        atr = signal_data.get("atr", 10.0) # fallback
        
        qty, risk, sl_dist, target_dist = calculate_position_size(50000, premium, atr, lot_size, self.config)
        sl = premium - sl_dist if opt_type == "CE" else premium + sl_dist
        target = premium + target_dist if opt_type == "CE" else premium - target_dist
        
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
