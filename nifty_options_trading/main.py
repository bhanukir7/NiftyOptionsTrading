"""
Controlled Telegram Trading Engine (Refactored)
Executes a task-based scheduler leveraging Websockets for live ticking
and caching mechanisms to avoid ICICIdirect API limits.

Author: Aditya Kota
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from nifty_options_trading.safe_breeze import SafeBreeze
from nifty_options_trading.market_stream import MarketStream
from nifty_options_trading.strict_validator import validate_strict_signal
from nifty_options_trading.alerts import send_alert
from nifty_options_trading.rule_engine import (
    StateManager, Config, determine_bias, can_trade, Position,
    validate_entry, calculate_position_size, can_take_new_trade_time, manage_trade, update_profit, update_loss
)

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
AVAILABLE_CAPITAL = float(os.getenv("AVAILABLE_FUNDS", "50000"))

STOCK_CODES = ["NIFTY", "CNXBAN", "VEDLIM", "MAZDOC", "RELIND", "COCSHI"]
EXCHANGE_CODE = "NSE"
INTERVAL = "5minute"

def initialize_breeze() -> SafeBreeze:
    """Initialize the SafeBreeze API wrapper."""
    print("Initializing SafeBreeze API wrapper...")
    breeze = SafeBreeze(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    print("SafeBreeze API successfully initialized.")
    return breeze

def fetch_historical_data(breeze: SafeBreeze, stock_code: str, exchange_code: str, interval: str) -> pd.DataFrame:
    """Fetch historical data for a given stock code to calculate indicators."""
    try:
        now_dt = datetime.now()
        iso_date = now_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") 
        start_date = f"{now_dt.strftime('%Y-%m-%d')}T00:00:00.000Z"
        
        response = breeze.get_historical_data(
            interval=interval,
            from_date=start_date,
            to_date=iso_date,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type="cash"
        )
        
        if response and response.get("Status") == 200 and "Success" in response:
            df = pd.DataFrame(response['Success'])
            df["close"] = pd.to_numeric(df["close"], errors='coerce')
            df["open"] = pd.to_numeric(df["open"], errors='coerce')
            df["high"] = pd.to_numeric(df["high"], errors='coerce')
            df["low"] = pd.to_numeric(df["low"], errors='coerce')
            df["volume"] = pd.to_numeric(df["volume"], errors='coerce') if "volume" in df else 1.0
            
            df.fillna(0, inplace=True)
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df
        return None
    except Exception as e:
        print(f"Exception during data fetch: {e}")
        return None

def finalize_trade(state: StateManager, reason: str, pnl: float):
    if pnl > 0:
        update_profit(state, pnl)
    else:
        update_loss(state, pnl)
    
    pos = state.active_position
    msg = (f"🛑 **TRADE CLOSED** ({pos.type})\n"
           f"Reason: {reason}\n"
           f"Realized PnL: ₹{pnl:.2f}\n"
           f"Daily PnL Tracking: ₹{state.daily_pnl:.2f}")
    send_alert(msg)
    print(f"[TRADE CLOSED] {reason} | PnL: {pnl:.2f}")
    state.active_position = None

def main():
    if not API_KEY or not API_SECRET or not SESSION_TOKEN:
        print("[ERROR] Missing API config in .env.")
        return

    try:
        breeze = initialize_breeze()
    except Exception as e:
        print(f"[ERROR] Failed to initialize API. {e}")
        return
        
    print(f"Starting Multi-Stock Controlled Trading Engine (Interval: {INTERVAL})...")
    
    # Init Market Stream
    stream = MarketStream(breeze)
    stream.subscribe(STOCK_CODES)
    
    state = StateManager()
    config = Config()
    
    # Scheduler variables
    last_5s = time.time()
    last_60s = time.time() - 60  # trigger immediately
    last_180s = time.time() - 180
    
    try:
        while True:
            now = time.time()
            
            # Rate Limiter Safeguard
            if breeze.rate_limiter.daily_calls >= breeze.rate_limiter.max_per_day * 0.9:
                print("CRITICAL TRIGGER: API Limit at 90%. Suspending all non-critical polling for 60s.")
                time.sleep(60)
                continue
                
            # 1. LIVE TRADE MANAGEMENT (Every 5 Seconds)
            if now - last_5s >= 5:
                last_5s = now
                
                if state.active_position is not None:
                    stock_code = getattr(state.active_position, "_debug_stock", "NIFTY") 
                    
                    # Fetch from Websocket Layer
                    current_price = stream.get_price(stock_code)
                    
                    # Fallback to polling if websocket fails
                    if current_price is None:
                        df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, "1minute")
                        if df is not None and not df.empty:
                            current_price = df.iloc[-1]["close"]
                            
                    if current_price is not None:
                        is_closed, reason, real_pnl = manage_trade(state.active_position, current_price, state, config)
                        
                        if not is_closed and reason.startswith("Partial"):
                            send_alert(f"🎯 **PARTIAL PROFIT BOOKED**\n{reason}\nHarvested: ₹{real_pnl:.2f}")
                        
                        if is_closed:
                            finalize_trade(state, reason, real_pnl)
                            
                    continue # Skip entry scanning while managing trade
                    
            # 2. ENTRY SETUPS & INDICATORS PIPELINE (Every 60 Seconds)
            if now - last_60s >= 60 and state.active_position is None:
                last_60s = now
                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{current_time_str}] Scanning Entry Setups (via Cached historical indicators)...")
                
                if not can_take_new_trade_time():
                    print(f"[{current_time_str}] End of Trading Day cutoff reached.")
                else:
                    allowed, risk_reason = can_trade(state, config)
                    if not allowed:
                         print(f"[{current_time_str}] RISK ENGINE BLOCKED ENTRY: {risk_reason}")
                    else:
                        for stock_code in STOCK_CODES:
                            df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, INTERVAL)
                            if df is not None and not df.empty:
                                spot_price = stream.get_price(stock_code)
                                if spot_price is None:
                                    spot_price = df.iloc[-1]["close"]
                                    
                                if 'volume' in df.columns and df['volume'].sum() > 0:
                                    df['cum_volume'] = df['volume'].cumsum()
                                    df['cum_price_vol'] = (df['close'] * df['volume']).cumsum()
                                    vwap = df['cum_price_vol'].iloc[-1] / df['cum_volume'].iloc[-1]
                                else:
                                    vwap = df['close'].mean()
                                    
                                state.current_bias = determine_bias(spot_price, vwap)
                                strict_res = validate_strict_signal(df)
                                signal = "HOLD"
                                if strict_res["signal"] == "BUY": signal = "BUY_CALL"
                                if strict_res["signal"] == "SELL": signal = "BUY_PUT"

                                if signal != "HOLD":
                                    print(f"[{current_time_str}] STRICT SIGNAL: {signal} | Confidence: {strict_res['confidence']}%")
                                    print(f"[{current_time_str}] Reasons: {', '.join(strict_res['reasons'])}")
                                    opt_type = "CE" if signal == "BUY_CALL" else "PE"
                                    day_open = df.iloc[0]["open"]
                                    intraday_pct = abs(spot_price - day_open) / day_open * 100
                                    
                                    is_valid, validation_reason = validate_entry(opt_type, state.current_bias, intraday_pct, config)
                                    if not is_valid:
                                         print(f"[{current_time_str}] Filtered {signal} on {stock_code}. Reason: {validation_reason}")
                                         continue
                                         
                                    entry_price = spot_price 
                                    qty, risk_amount, sl_move = calculate_position_size(AVAILABLE_CAPITAL, entry_price, config)
                                    
                                    if qty <= 0: qty = 1
                                    
                                    if qty > 0:
                                        atm_strike = int(round(spot_price / 100.0) * 100)
                                        target = entry_price * (1 + config.sl_pct * 1.5)
                                        sl = entry_price - sl_move if opt_type == "CE" else entry_price + sl_move
                                        
                                        new_pos = Position(type=opt_type, entry_price=entry_price, qty=qty, sl_price=sl, target_price=target, partial_booked=False)
                                        setattr(new_pos, "_debug_stock", stock_code) 
                                        state.active_position = new_pos
                                        state.trades_today += 1
                                        state.last_trade_time = datetime.now()
                                        
                                        msg = (f"🚀 **ENTRY EXECUTED (Rule Engine Validated)**\n"
                                               f"Instrument: {stock_code} {atm_strike} {opt_type}\n"
                                               f"Spot Exec Price: {entry_price:.2f}\n"
                                               f"Bias: {state.current_bias}\n"
                                               f"Confidence: {strict_res['confidence']}%\n"
                                               f"Reasons: {', '.join(strict_res['reasons'])}\n"
                                               f"Qty: {qty} | Risk Allocated: ₹{risk_amount:.2f}\n"
                                               f"Daily Trade Count: {state.trades_today}/{config.max_trades_per_day}")
                                        send_alert(msg)
                                        print(f"[{current_time_str}] ENTRY EXECUTED: {stock_code} {opt_type}")
                                        break
                                        
            # 3. BACKGROUND DATA PREFETCH (Every 180 Seconds)
            if now - last_180s >= 180:
                last_180s = now
                breeze.log_api_usage()
                
            time.sleep(1) # Base tick rate

    except KeyboardInterrupt:
        print("Stopping... Disconnecting Stream...")
        stream.disconnect()
        
if __name__ == "__main__":
    main()
