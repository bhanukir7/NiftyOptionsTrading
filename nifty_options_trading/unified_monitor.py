"""
Live Market Unified Monitor
Orchestrates multiple symbol tracking loops to actively report signal convergences.

Author: Aditya Kota
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from breeze_connect import BreezeConnect
from strategy import analyze_and_generate_signal
from alerts import send_alert
from nifty_options_trading.expiry_calc import get_dynamic_expiry, get_next_weekly_expiry
from nifty_options_trading.options_engine import get_option_chain, get_dynamic_lot_size
from nifty_options_trading.max_pain import calculate_max_pain
from nifty_options_trading.theta_defense import calculate_dte, evaluate_theta_risk

load_dotenv(os.path.join(parent_dir, '.env'))

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

def initialize_breeze() -> BreezeConnect:
    print("Initializing Breeze API for Unified Monitor...")
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    return breeze

def fetch_historical_data(breeze: BreezeConnect, stock_code: str, exchange_code: str, interval: str) -> pd.DataFrame:
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
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df
        return None
    except Exception as e:
        print(f"Exception during historical data fetch: {e}")
        return None

def run_unified_monitor():
    if not API_KEY or not API_SECRET or not SESSION_TOKEN:
        print("[ERROR] Missing API config in .env.")
        return
        
    try:
        breeze = initialize_breeze()
    except Exception as e:
        print(f"[ERROR] Breeze Init Failed: {e}")
        return
        
    STOCK_CODES = ["NIFTY", "CNXBAN", "VEDLIM"]
    EXCHANGE_CODE = "NSE"
    INTERVAL = "5minute"
    
    print(f"Starting Unified Monitor (Interval: {INTERVAL})...")
    print(f"Monitoring: {', '.join(STOCK_CODES)}")
    
    last_alerted_signals = {stock: "HOLD" for stock in STOCK_CODES}
    
    while True:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time_str}] Fetching data and analyzing...")
        
        for stock_code in STOCK_CODES:
            df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, INTERVAL)
            
            if df is not None and not df.empty:
                signal = analyze_and_generate_signal(df)
                spot_price = df.iloc[-1]["close"]
                
                if signal != "HOLD" and signal != last_alerted_signals[stock_code]:
                    option_type = "CE" if signal == "BUY_CALL" else "PE"
                    
                    # 1. Dynamic Expiry & OTM Strike Engine
                    expiry_date = get_dynamic_expiry(stock_code)
                    dte = calculate_dte(expiry_date)
                    
                    # Rollover logic: If NIFTY weekly expiry is too close (e.g. <= 3 DTE), roll to next week's expiry
                    if stock_code == "NIFTY" and dte <= 3:
                        from datetime import timedelta
                        front_expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                        # Feed a future date to get the subsequent weekly expiry
                        expiry_date = get_next_weekly_expiry(front_expiry_dt + timedelta(days=1))
                        dte = calculate_dte(expiry_date) # recalculate updated DTE 
                        
                    # Calculate strike ~2% OTM (configurable in .env)
                    otm_percentage = float(os.getenv("OTM_PERCENTAGE", "0.02"))
                    if option_type == "CE":
                        target_price = spot_price * (1 + otm_percentage)
                    else:
                        target_price = spot_price * (1 - otm_percentage)
                        
                    strike_step = 50.0 if stock_code == "NIFTY" else 100.0 if stock_code == "CNXBAN" else 5.0
                    otm_strike = int(round(target_price / strike_step) * strike_step)
                    atm_strike = int(round(spot_price / strike_step) * strike_step) # Just for perspective
                    
                    recommended_contract = f"{stock_code} {expiry_date} {otm_strike} {option_type}"
                    
                    # 2. Options Analytics Component
                    chain_df = get_option_chain(breeze, stock_code, expiry_date)
                    max_pain = 0.0
                    opt_ltp = 0.0
                    num_lots = 0
                    lot_size = 1
                    
                    if chain_df is not None and not chain_df.empty:
                        max_pain = calculate_max_pain(chain_df)
                        
                        # Extract the LTP of the recommended contract to calculate lot sizing
                        target_row = chain_df[(chain_df['strike_price'] == float(otm_strike)) & 
                                              (chain_df['right'].str.upper().isin(['CALL', 'CE'] if option_type == 'CE' else ['PUT', 'PE']))]
                        if not target_row.empty:
                            opt_ltp = float(target_row.iloc[0]['last_traded_price'])
                            
                        # Calculate quantity based on available funds
                        available_funds = float(os.getenv("AVAILABLE_FUNDS", "50000"))
                        lot_size = get_dynamic_lot_size(stock_code)
                        
                        if opt_ltp > 0:
                            lot_cost = opt_ltp * lot_size
                            num_lots = int(available_funds / lot_cost)
                        
                    # 3. Theta Risk Component (Elevated Defense for OTM buying)
                    # We already calculated DTE above, so we just run the evaluate function
                    theta_assessment = evaluate_theta_risk(dte, threshold=3)
                    
                    # 4. Construct Unified Telegram Alert
                    alert_msg = (
                        f"🚨 **UNIFIED TRADE ALERT** 🚨\n"
                        f"Underlying: {stock_code}\n"
                        f"Spot Price: {spot_price}\n"
                        f"Technical Signal: {signal}\n\n"
                        f"**Trade Setup (Targeting ~{otm_percentage*100}% OTM):**\n"
                    )
                    
                    if num_lots > 0:
                        alert_msg += f"🎯 **Buy {num_lots} Lots** ({num_lots * lot_size} Qty) of {recommended_contract}\n"
                        alert_msg += f"💰 Est. Premium: ₹{opt_ltp} | Capital Required: ₹{round(num_lots * opt_ltp * lot_size, 2)}\n"
                    else:
                        alert_msg += f"🎯 Buy Contract: {recommended_contract}\n"
                        if opt_ltp > 0:
                            alert_msg += f"⚠️ Insufficient funds for 1 lot. (Requires: ₹{round(opt_ltp * lot_size, 2)})\n"
                        else:
                            alert_msg += f"⚠️ Live premium data unavailable for sizing.\n"
                    
                    alert_msg += f"*(For reference, ATM strike is {atm_strike})*\n\n"
                    
                    if max_pain > 0:
                        alert_msg += f"📊 Options Max Pain: {max_pain}\n"
                        if (signal == "BUY_CALL" and max_pain > spot_price) or (signal == "BUY_PUT" and max_pain < spot_price):
                            alert_msg += "✅ Max Pain ALIGNS with Technical Signal!\n"
                        else:
                            alert_msg += "⚠️ Max Pain DIVERGES from Technical Signal.\n"
                    
                    if theta_assessment['defense_active']:
                        alert_msg += f"\n🛡️ **THETA DEFENSE ACTIVE:** {theta_assessment['message']}"
                    else:
                        alert_msg += f"\n✅ Theta Risk: Normal ({dte} DTE)"
                        
                    send_alert(alert_msg)
                    last_alerted_signals[stock_code] = signal
                else:
                    print(f"[{current_time_str}] {stock_code} Spot: ₹{spot_price} | Signal: {signal}")
                    
            time.sleep(1)
            
        time.sleep(60)

if __name__ == "__main__":
    run_unified_monitor()
