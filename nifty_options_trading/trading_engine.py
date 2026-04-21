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
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional, Literal

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
        # Allow multiple concurrent scans if capacity allows
        
        allowed, reason = can_trade(self.state, self.config)
        if not allowed:
            self.last_signal = {"timestamp": datetime.now().isoformat(), "signal": "BLOCKED", "reason": reason}
            return

        if not can_take_new_trade_time():
            self.log("Market closing hours reached. Scanning suspended.")
            return

        for symbol in self.stock_codes:
            if symbol in self.state.active_positions:
                continue # Already in a trade for this symbol
            self._analyze_symbol(symbol)

    def _analyze_symbol(self, symbol: str):
        # 1. Fetch Technical Data (from 5min historical)
        try:
            hist_res = self.breeze.get_historical_data(
                interval="5minute", 
                from_date=datetime.now().strftime("%Y-%m-%dT00:00:00.000Z"),
                to_date=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                stock_code=symbol,
                exchange_code=self.exchange,
                product_type="cash"
            )
            if not hist_res or hist_res.get("Status") != 200: return
            
            df = pd.DataFrame(hist_res["Success"])
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=["close"], inplace=True)
            
            spot = self.stream.get_price(symbol) or df.iloc[-1]["close"]
            vwap = df["close"].mean() # Simplified
            bias = determine_bias(spot, vwap)
            self.state.current_bias = bias
            
            # Extract basic technically approximated values for Breakout Logic
            atr = (df["high"] - df["low"]).mean() # Proxy
            bb_upper = df["close"].rolling(20).mean().iloc[-1] + (2 * df["close"].rolling(20).std().iloc[-1])
            bb_lower = df["close"].rolling(20).mean().iloc[-1] - (2 * df["close"].rolling(20).std().iloc[-1])
            resistance = df["high"].max() # Using intraday high as resistance
            support = df["low"].min()     # Using intraday low as support
            
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

            # Feed Breakout Strategy
            market_data = MarketData(
                symbol=symbol, price=spot, resistance=resistance, support=support,
                atr=atr, chop=56, bb_upper=bb_upper, bb_lower=bb_lower,
                macd=1, macd_signal=0.5, pcr=pcr, call_oi=call_oi, put_oi=put_oi, iv=15
            )
            
            # Feed Advanced Strategy for Signal Hub observability
            adv_data = AdvMarketData(
                symbol=symbol, price=spot, resistance=resistance, support=support,
                atr=atr, chop=56, bb_upper=bb_upper, bb_lower=bb_lower,
                macd=1, macd_signal=0.5, pcr=pcr, call_oi=call_oi, put_oi=put_oi,
                call_oi_change=0, put_oi_change=0, iv=15, volume=df.iloc[-1]["volume"] if "volume" in df.columns else 0
            )
            self.adv_strat.detect_state(adv_data)
            self.adv_strat.check_entry(adv_data)
            
            action = self.breakout_strat.process_tick(market_data, spot)
            if action and action["action"] == "ENTER":
                self.log(f"BREAKOUT STRATEGY SIGNAL: {action['type']} on {symbol}")
                sig = {
                    "signal": f"BUY_{action['type']}",
                    "reason": action["reason"],
                    "target": spot * 1.05,
                    "stop_loss": spot * 0.97
                }
                self._execute_signal(symbol, sig)
                return

            # Keep Technical Strategy Fallback if breakout doesn't trigger
            tech_signal = analyze_and_generate_signal(df)
            if tech_signal != "HOLD":
                self.log(f"TECHNICAL SIGNAL: {tech_signal} on {symbol}")
                sig = {
                    "signal": "BUY_CE" if tech_signal == "BUY_CALL" else "BUY_PE",
                    "reason": "EMA Cross + MACD Alignment",
                    "target": spot * 1.05,
                    "stop_loss": spot * 0.97
                }
                self._execute_signal(symbol, sig)

        except Exception as e:
            self.log(f"Error analyzing {symbol}: {e}")

    def _execute_signal(self, symbol: str, signal_data: Dict):
        opt_type = "CE" if signal_data["signal"] == "BUY_CE" else "PE"
        spot = self.stream.get_price(symbol)
        
        # Risk Check
        day_open = spot # simple placeholder
        intraday_pct = 0.5
        valid, reason = validate_entry(opt_type, self.state.current_bias, intraday_pct, self.config)
        
        if not valid:
            self.log(f"Signal filtered: {reason}")
            return

        # Create Position
        qty, risk, sl_move = calculate_position_size(50000, spot, self.config)
        sl = spot - sl_move if opt_type == "CE" else spot + sl_move
        
        pos = Position(
            type=opt_type, 
            entry_price=spot, 
            qty=qty, 
            sl_price=sl, 
            target_price=signal_data.get("targets", {}).get("t1", spot*1.05)
        )
        self.state.active_positions[symbol] = pos
        self.state.trades_today += 1
        self.state.last_trade_time = datetime.now()
        
        mode = "LIVE (BETA)" if not self.config.paper_trade else "PAPER TRADE"
        msg = (f"🚀 **ENGINE ENTRY Executed ({mode})**\n"
               f"Symbol: {symbol} | Type: {opt_type}\n"
               f"Entry: {spot:.2f} | Qty: {qty}\n"
               f"Reason: {signal_data['reason']}")
        
        self.log(f"ENTRY: {opt_type} at {spot:.2f} ({mode})")
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
