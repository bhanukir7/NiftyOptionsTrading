"""
Base Option Pricing Engine
Connects to live ICICI Option Chains to measure contract affordability metrics.

Author: Aditya Kota
"""
import os
import sys
import re
from datetime import datetime
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from breeze_connect import BreezeConnect
from nifty_options_trading.options_engine import get_option_chain
from nifty_options_trading.unified_monitor import fetch_historical_data
from strategy import analyze_and_generate_signal

load_dotenv(os.path.join(parent_dir, '.env'))

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

def initialize_breeze() -> BreezeConnect:
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    return breeze

def parse_input_string(contract_str: str) -> dict:
    parts = re.split(r'\s+', contract_str.strip())
    if len(parts) < 5:
        raise ValueError("Invalid format. Expected: 'SYMBOL DD MMM STRIKE TYPE' (e.g. 'cnxban 28 apr 48800 PE')")
        
    stock_code = parts[0].upper()
    day = parts[1]
    month = parts[2].capitalize()
    strike = float(parts[3])
    opt_type = parts[4].upper()
    
    if opt_type not in ["CE", "CALL", "PE", "PUT"]:
        raise ValueError(f"Invalid option type: {opt_type}. Expected CE or PE.")
        
    current_year = datetime.now().year
    date_str = f"{day} {month} {current_year}"
    
    try:
        parsed_dt = datetime.strptime(date_str, "%d %b %Y")
        iso_expiry = parsed_dt.strftime("%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Could not parse date '{date_str}': {e}")
        
    return {
        "stock_code": stock_code,
        "expiry_date": iso_expiry,
        "strike": strike,
        "opt_type": "CE" if opt_type in ["CE", "CALL"] else "PE" 
    }

def generate_verdict(spot_signal: str, opt_type: str) -> str:
    # 1. 1-Minute Hyper Momentum Rule
    verdict = ""
    
    if opt_type == "CE":
        if spot_signal == "BUY_CALL": 
            verdict = "🔥 ULTRA-SCALP BUY TRIGGERED! (1-Min Momentum confirms Breakout)"
        elif spot_signal == "BUY_PUT": 
            verdict = "🛑 REJECT / FIGHTING MOMENTUM (1-Min Trend is Bearish)"
        else: 
            verdict = "🟡 SCALP RANGE-BOUND / Wait for 1-minute volume breakout."
    else: # PE
        if spot_signal == "BUY_PUT": 
            verdict = "🔥 ULTRA-SCALP BUY TRIGGERED! (1-Min Momentum confirms Breakdown)"
        elif spot_signal == "BUY_CALL": 
            verdict = "🛑 REJECT / FIGHTING MOMENTUM (1-Min Trend is Bullish)"
        else: 
            verdict = "🟡 SCALP RANGE-BOUND / Wait for 1-minute volume breakdown."
            
    return verdict

def print_report(parsed: dict, opt_ltp: float, num_lots: int, lot_size: int, capital_req: float, spot_signal: str):
    print("\n" + "="*60)
    print(f" ⚡ HYPER-SCALP EVALUATOR: {parsed['stock_code']} {parsed['expiry_date']} {parsed['strike']} {parsed['opt_type']}")
    print("="*60)
    
    # 1. Price Sizing & Tactical Structure
    if opt_ltp > 0:
        print(f"💸 Live Premium        : ₹{opt_ltp}")
        available = float(os.getenv("AVAILABLE_FUNDS", "50000"))
        
        if num_lots > 0:
            print(f"📦 Affordability        : {num_lots} Lots [{num_lots * lot_size} Qty] using ₹{available} budget")
        else:
            print(f"⚠️ Warning              : Budget insufficient. 1 lot costs ₹{round(opt_ltp * lot_size, 2)}")
            
        print("-"*60)
        # Scalper Trade Parameters
        print(f"🚀 SCALP PARAMETERS (10-Minute Execution Strategy):")
        print(f"   Target        : +5% Premium (Take Profit at ~₹{round(opt_ltp * 1.05, 2)})")
        print(f"   Stop-Loss     : -3% to -5% Premium (Cut Loss at ~₹{round(opt_ltp * 0.96, 2)})")
        print(f"   Time Stop     : Exit trade entirely after 10 minutes.")
    else:
        print("⚠️ Live Premium       : Contract NOT FOUND in current active chain.")
        
    print("-"*60)
    print(f"📡 1-Min Spot Technical : {spot_signal}")
    
    # 2. FINAL VERDICT
    print("="*60)
    final_decision = generate_verdict(spot_signal, parsed['opt_type'])
    print(f"🎯 FINAL VERDICT: {final_decision}")
    print("="*60 + "\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluate_contract.py \"<CONTRACT_STRING>\"")
        print("Example: python evaluate_contract.py \"cnxban 28 Apr 48800 PE\"")
        sys.exit(1)
        
    raw_input = sys.argv[1]
    
    try:
        parsed = parse_input_string(raw_input)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
        
    print(f"Connecting to Breeze API...")
    
    try:
        breeze = initialize_breeze()
    except Exception as e:
        print(f"[ERROR] API Authentication Failed. {e}")
        sys.exit(1)
        
    print(f"Fetching 1-Minute Live Technicals & Verifying Contract...")
    
    # Fetch 1 min trend purely for hyper-scalping
    spot_df = fetch_historical_data(breeze, parsed['stock_code'], "NSE", "1minute")
    spot_signal = "HOLD"
    if spot_df is not None and not spot_df.empty:
        spot_signal = analyze_and_generate_signal(spot_df)
        
    chain_df = get_option_chain(breeze, parsed['stock_code'], parsed['expiry_date'])
    
    opt_ltp = 0.0
    num_lots = 0
    lot_size = 1
    capital_req = 0.0
    
    if chain_df is not None and not chain_df.empty:
        opt_type_full = "CALL" if parsed['opt_type'] == "CE" else "PUT"
        target_row = chain_df[(chain_df['strike_price'] == float(parsed['strike'])) & 
                              (chain_df['right'].str.upper().isin([opt_type_full, parsed['opt_type']]))]
                              
        if not target_row.empty:
            opt_ltp = float(target_row.iloc[0]['last_traded_price'])
            lot_sizes = {"NIFTY": 65, "CNXBAN": 20, "VEDLIM": 1150}
            lot_size = lot_sizes.get(parsed['stock_code'], 1)
            available_funds = float(os.getenv("AVAILABLE_FUNDS", "50000"))
            
            if opt_ltp > 0:
                lot_cost = opt_ltp * lot_size
                num_lots = int(available_funds / lot_cost)
                capital_req = num_lots * lot_cost
                
    print_report(parsed, opt_ltp, num_lots, lot_size, capital_req, spot_signal)

if __name__ == "__main__":
    main()
