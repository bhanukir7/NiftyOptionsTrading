"""
Controlled Telegram Trading Engine
Executes continuous polling against Breeze to generate and manage live trades
using strict Rule Engine constraints and discipline.

Author: Aditya Kota
"""
import os
import sys

# Ensure the parent directory is in the python path to prevent ModuleNotFoundError
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from breeze_connect import BreezeConnect
from nifty_options_trading.strategy import analyze_and_generate_signal
from nifty_options_trading.alerts import send_alert
from nifty_options_trading.rule_engine import (
    StateManager, Config, determine_bias, can_trade, Position,
    validate_entry, calculate_position_size, can_take_new_trade_time, manage_trade, update_profit, update_loss
)

# Load environment variables
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
AVAILABLE_CAPITAL = float(os.getenv("AVAILABLE_FUNDS", "50000"))

def initialize_breeze() -> BreezeConnect:
    """Initialize the Breeze API connection."""
    print("Initializing Breeze API...")
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    print("Breeze API successfully initialized.")
    return breeze

def fetch_historical_data(breeze: BreezeConnect, stock_code: str, exchange_code: str, interval: str) -> pd.DataFrame:
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
            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["volume"] = df["volume"].astype(float) if "volume" in df else 1.0
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df
        return None
    except Exception as e:
        print(f"Exception during data fetch: {e}")
        return None

def finalize_trade(state: StateManager, reason: str, pnl: float):
    """Helper to cleanly close a position, update PnL, and notify."""
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
        print(f"[ERROR] Failed to initialize Breeze API. {e}")
        return
        
    STOCK_CODES = ["NIFTY", "CNXBAN", "VEDLIM"]
    EXCHANGE_CODE = "NSE"
    INTERVAL = "5minute" 
    
    print(f"Starting Multi-Stock Controlled Trading Engine (Interval: {INTERVAL})...")
    
    # 1. Initialize State
    state = StateManager()
    config = Config()
    
    while True:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 8. Manage Trades Loop (Continuously monitor active trades)
        if state.active_position is not None:
            # We strictly enforce Single Active Position. We ONLY manage the open trade.
            stock_code = getattr(state.active_position, "_debug_stock", "NIFTY") 
            df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, "1minute")
            if df is not None and not df.empty:
                current_price = df.iloc[-1]["close"]  # Mocking Premium drift using Spot Price proxy
                
                is_closed, reason, real_pnl = manage_trade(state.active_position, current_price, state, config)
                
                # If partial profits were harvested
                if not is_closed and reason.startswith("Partial"):
                    send_alert(f"🎯 **PARTIAL PROFIT BOOKED**\n{reason}\nHarvested: ₹{real_pnl:.2f}")
                
                # If trade hit SL or was manually closed
                if is_closed:
                    finalize_trade(state, reason, real_pnl)
            
            time.sleep(15) # Faster polling when managing a live trade
            continue
            
        print(f"\n[{current_time_str}] Scanning for Entry Setups...")
        
        for stock_code in STOCK_CODES:
            # 3. Enforce Time Filter before analysis
            if not can_take_new_trade_time():
                print(f"[{current_time_str}] End of Trading Day cutoff reached. No new positions allowed.")
                # We can safely break the ticker loop, but daemon stays alive
                break
                
            # 4. Enforce Risk Engine
            allowed, risk_reason = can_trade(state, config)
            if not allowed:
                 print(f"[{current_time_str}] RISK ENGINE BLOCKED ENTRY: {risk_reason}")
                 break # Sleep until next cycle if risk block is hit entirely
                 
            df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, INTERVAL)
            
            if df is not None and not df.empty:
                # 2. Integrate Bias Engine
                spot_price = df.iloc[-1]["close"]
                
                # Compute VWAP. Using cumsum over historical slice.
                if 'volume' in df.columns and df['volume'].sum() > 0:
                    df['cum_volume'] = df['volume'].cumsum()
                    df['cum_price_vol'] = (df['close'] * df['volume']).cumsum()
                    vwap = df['cum_price_vol'].iloc[-1] / df['cum_volume'].iloc[-1]
                else:
                    vwap = df['close'].mean() # Proxy
                    
                state.current_bias = determine_bias(spot_price, vwap)
                
                signal = analyze_and_generate_signal(df)
                
                if signal != "HOLD":
                    # 5. Validate Entry
                    opt_type = "CE" if signal == "BUY_CALL" else "PE"
                    day_open = df.iloc[0]["open"]
                    intraday_pct = abs(spot_price - day_open) / day_open * 100
                    
                    is_valid, validation_reason = validate_entry(opt_type, state.current_bias, intraday_pct, config)
                    
                    if not is_valid:
                         print(f"[{current_time_str}] Filtered {signal} on {stock_code}. Reason: {validation_reason}")
                         continue
                        
                    # 6. Create Position & Calculate Sizing
                    # We mock premium entry with current Spot Price. SL move will scale 1:1.
                    entry_price = spot_price 
                    qty, risk_amount, sl_move = calculate_position_size(AVAILABLE_CAPITAL, entry_price, config)
                    
                    # Prevent zero quantity failures
                    if qty <= 0:
                         qty = 1
                         
                    if qty > 0:
                        atm_strike = int(round(spot_price / 100.0) * 100)
                        
                        target = entry_price * (1 + config.sl_pct * 1.5) # Example RR
                        sl = entry_price - sl_move if opt_type == "CE" else entry_price + sl_move
                        
                        new_pos = Position(
                            type=opt_type,
                            entry_price=entry_price,
                            qty=qty,
                            sl_price=sl,
                            target_price=target,
                            partial_booked=False
                        )
                        # Temporary dynamic binding for loop tracking
                        setattr(new_pos, "_debug_stock", stock_code) 
                        state.active_position = new_pos
                        state.trades_today += 1
                        state.last_trade_time = datetime.now()
                        
                        # 7. Replace Alert Logic (Send ONLY when executed)
                        msg = (f"🚀 **ENTRY EXECUTED (Rule Engine Validated)**\n"
                               f"Instrument: {stock_code} {atm_strike} {opt_type}\n"
                               f"Spot Exec Price: {entry_price:.2f}\n"
                               f"Bias: {state.current_bias}\n"
                               f"Qty: {qty} | Risk Allocated: ₹{risk_amount:.2f}\n"
                               f"Daily Trade Count: {state.trades_today}/{config.max_trades_per_day}")
                        send_alert(msg)
                        
                        print(f"[{current_time_str}] ENTRY EXECUTED: {stock_code} {opt_type}")
                        # 9. Ensure Single Active Position: Break inner loop, shift to Management Mode
                        break 
                        
            # Sleep 1 second to avoid hitting ICICIdirect RPS limit 
            time.sleep(1)
            
        time.sleep(60)

if __name__ == "__main__":
    main()
