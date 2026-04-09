"""
End-of-Day BTST Gap-Up Predictor
Uses daily moving averages and EOD closing strength to validate gap-up holding potential.

Author: Aditya Kota
"""
import os
import sys
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from ta.trend import MACD
from ta.volatility import AverageTrueRange, BollingerBands

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from breeze_connect import BreezeConnect
from nifty_options_trading.options_engine import get_option_chain

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

def fetch_multiday_data(breeze: BreezeConnect, stock_code: str, exchange_code: str, interval: str, days_back=90) -> pd.DataFrame:
    try:
        now_dt = datetime.now()
        iso_date = now_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") 
        # go back `days_back` days to ensure we get enough data for indicators to 'burn in'
        start_date_dt = now_dt - timedelta(days=days_back)
        start_date = f"{start_date_dt.strftime('%Y-%m-%d')}T00:00:00.000Z"
        
        response = breeze.get_historical_data(
            interval=interval,
            from_date=start_date,
            to_date=iso_date,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type="cash"
        )
        
        if response and response.get("Status") == 200 and "Success" in response and response['Success']:
            df = pd.DataFrame(response['Success'])
            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.reset_index(drop=True)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Exception during historical data fetch: {e}")
        return pd.DataFrame()

def analyze_advanced_indicators(df: pd.DataFrame) -> dict:
    """
    Applies MACD and Bollinger Bands on a Daily Timeframe.
    Evaluates End-of-Day closing strength for BTST Gap-Up/Down setups.
    """
    if df is None or len(df) < 30:
        return {"signal": "HOLD", "reason": "Not enough data for Daily Indicators"}

    # 1. MACD
    macd_obj = MACD(close=df["close"])
    df["MACD"] = macd_obj.macd()
    df["MACD_Signal"] = macd_obj.macd_signal()
    df["MACD_Hist"] = macd_obj.macd_diff()

    # 2. Bollinger Bands
    bb_obj = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_High"] = bb_obj.bollinger_hband()
    df["BB_Low"] = bb_obj.bollinger_lband()
    df["BB_Mid"] = bb_obj.bollinger_mavg()

    # Focus exclusively on the latest data points
    latest = df.iloc[-1]

    # Analysis Logic
    macd_bullish = latest["MACD"] > latest["MACD_Signal"] and latest["MACD_Hist"] > 0
    macd_bearish = latest["MACD"] < latest["MACD_Signal"] and latest["MACD_Hist"] < 0

    above_bb_mid = latest["close"] > latest["BB_Mid"]
    below_bb_mid = latest["close"] < latest["BB_Mid"]
    
    # Calculate Closing Strength (Percentage of range where candle closed)
    candle_range = latest["high"] - latest["low"]
    if candle_range > 0:
        close_strength = (latest["close"] - latest["low"]) / candle_range
    else:
        close_strength = 0.5
        
    close_strength_pct = round(close_strength * 100, 2)

    signal = "HOLD"
    reason = f"Market lacks BTST momentum. Daily Close Strength is {close_strength_pct}%."

    # BTST GAP UP LOGIC
    if macd_bullish and above_bb_mid and close_strength >= 0.70:
        signal = "BUY_CALL_BTST"
        reason = f"Strong BTST Gap-Up Setup: Price > BB Mid, Bullish MACD, and closed very strong ({close_strength_pct}% of daily range)."
    # BTST GAP DOWN LOGIC
    elif macd_bearish and below_bb_mid and close_strength <= 0.30:
        signal = "BUY_PUT_BTST"
        reason = f"Strong BTST Gap-Down Setup: Price < BB Mid, Bearish MACD, and closed very weak ({close_strength_pct}% of daily range)."
    # Weak/Hold setups
    elif close_strength > 0.60 and above_bb_mid:
        signal = "BUY_CALL_WEAK"
        reason = f"Moderate upward close ({close_strength_pct}%). Risky Gap-Up setup lacking full momentum."
    elif close_strength < 0.40 and below_bb_mid:
        signal = "BUY_PUT_WEAK"
        reason = f"Moderate downward close ({close_strength_pct}%). Risky Gap-Down setup lacking full momentum."

    return {
        "signal": signal,
        "reason": reason,
        "macd": latest["MACD"],
        "macd_hist": latest["MACD_Hist"],
        "bb_high": latest["BB_High"],
        "bb_low": latest["BB_Low"],
        "bb_mid": latest["BB_Mid"],
        "close_strength": close_strength_pct,
        "close": latest["close"]
    }

def generate_verdict(signal_data: dict, opt_type: str) -> str:
    signal = signal_data["signal"]
    verdict = ""
    
    if opt_type == "CE":
         if signal == "BUY_CALL_BTST":
             verdict = "🟩 HIGH CONVICTION BTST (Expect Gap-Up Opening)"
         elif signal == "BUY_CALL_WEAK":
             verdict = "🟨 WEAK BTST (Moderate Gap-Up chance, keep strict SL)"
         elif signal in ["BUY_PUT_BTST", "BUY_PUT_WEAK"]:
             verdict = "🛑 REJECT (Daily Trend/Close is Bearish, avoid BTST CALLs)"
         else:
             verdict = f"⚪ AVOID BTST: {signal_data['reason']}"
    else:
         if signal == "BUY_PUT_BTST":
             verdict = "🟥 HIGH CONVICTION BTST (Expect Gap-Down Opening)"
         elif signal == "BUY_PUT_WEAK":
             verdict = "🟨 WEAK BTST (Moderate Gap-Down chance, keep strict SL)"
         elif signal in ["BUY_CALL_BTST", "BUY_CALL_WEAK"]:
             verdict = "🛑 REJECT (Daily Trend/Close is Bullish, avoid BTST PUTs)"
         else:
             verdict = f"⚪ AVOID BTST: {signal_data['reason']}"
             
    return verdict

def print_report(parsed: dict, opt_ltp: float, num_lots: int, lot_size: int, capital_req: float, signal_data: dict):
    print("\n" + "="*75)
    print(f" 📊 BTST EOD EVALUATOR: {parsed['stock_code']} {parsed['expiry_date']} {parsed['strike']} {parsed['opt_type']}")
    print(f"    (Focus: 1-Day Timeframe, End-Of-Day Closing Strength)")
    print("="*75)
    
    if opt_ltp > 0:
        print(f"💸 Live Premium        : ₹{opt_ltp}")
        available = float(os.getenv("AVAILABLE_FUNDS", "50000"))
        
        if num_lots > 0:
            print(f"📦 Affordability        : {num_lots} Lots [{num_lots * lot_size} Qty] using ₹{available} budget")
        else:
            print(f"⚠️ Warning              : Budget insufficient. 1 lot costs ₹{round(opt_ltp * lot_size, 2)}")
            
        print("-" * 75)
        # Wider targets for BTST given opening volatility
        target1 = opt_ltp * 1.15
        target2 = opt_ltp * 1.30
        sl = opt_ltp * 0.90
        
        print(f"🚀 BTST OPENING TARGETS (High Volatility Setup):")
        print(f"   Target 1 (+15%) : [~₹{round(target1, 2)}] (Take early profit on gap)")
        print(f"   Target 2 (+30%) : [~₹{round(target2, 2)}] (Hold runner)")
        print(f"   Stop-Loss (-10%): [~₹{round(sl, 2)}] (Strict stop if gap fails)")
    else:
        print("⚠️ Live Premium       : Contract NOT FOUND in current active chain.")
        
    print("-" * 75)
    print(f"📡 Daily (1-Day) Spot Technical Data:")
    print(f"   Daily Close   : {signal_data.get('close', 0):.2f}")
    
    cs = signal_data.get('close_strength', 0)
    cs_indicator = "STRONG" if cs >= 70 else "WEAK" if cs <= 30 else "NEUTRAL"
    print(f"   Close Strength: {cs}% ({cs_indicator} EOD Momentum)")
    
    print(f"   Daily MACD    : {signal_data.get('macd_hist', 0):.2f}")
    print(f"   Bollinger 20D : Low={signal_data.get('bb_low', 0):.2f} | Mid={signal_data.get('bb_mid', 0):.2f} | High={signal_data.get('bb_high', 0):.2f}")
    
    print(f"\n   >> SIGNAL      : {signal_data.get('signal', 'HOLD')}")
    print(f"   >> REASON      : {signal_data.get('reason', '')}")
    
    print("="*75)
    final_decision = generate_verdict(signal_data, parsed['opt_type'])
    print(f"🎯 BTST VERDICT: {final_decision}")
    print("="*75 + "\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluate_btst.py \"<CONTRACT_STRING>\"")
        print("Example: python evaluate_btst.py \"cnxban 28 Apr 48800 CE\"")
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
        
    print(f"Fetching Daily (1-Day) Technicals for BTST Analysis...")
    
    # Fetch 90 days to ensure proper Daily MACD and BB generation
    spot_df = fetch_multiday_data(breeze, parsed['stock_code'], "NSE", "1day", days_back=90)
    
    if spot_df.empty:
        print("[ERROR] Could not fetch historic 1D data. Check API or trading hours.")
        sys.exit(1)
        
    signal_data = analyze_advanced_indicators(spot_df)
        
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
                
    print_report(parsed, opt_ltp, num_lots, lot_size, capital_req, signal_data)

if __name__ == "__main__":
    main()
