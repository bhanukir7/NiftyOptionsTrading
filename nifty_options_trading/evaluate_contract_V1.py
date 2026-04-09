"""
Intraday Options Engine V1 (Dynamic Volatility)
Evaluates trailing market momentum using ATR to define dynamic variable stop-loss targets.

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

def fetch_multiday_data(breeze: BreezeConnect, stock_code: str, exchange_code: str, interval: str, days_back=5) -> pd.DataFrame:
    try:
        now_dt = datetime.now()
        iso_date = now_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") 
        # go back `days_back` days to ensure we get enough data for indicators and 2 trading days
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
        
        if response and response.get("Status") == 200 and "Success" in response:
            df = pd.DataFrame(response['Success'])
            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["datetime"] = pd.to_datetime(df["datetime"])
            # Filter specifically for the last 2 unique trading days
            df['date_only'] = df['datetime'].dt.date
            unique_dates = sorted(df['date_only'].unique())
            if len(unique_dates) > 2:
                last_two_days = unique_dates[-2:]
                df = df[df['date_only'].isin(last_two_days)].copy()
            df = df.reset_index(drop=True)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Exception during historical data fetch: {e}")
        return pd.DataFrame()

def calculate_choppiness_index(df: pd.DataFrame, window=14) -> pd.Series:
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum(abs(df['high'] - df['close'].shift(1)), 
                               abs(df['low'] - df['close'].shift(1))))
    sum_tr = tr.rolling(window=window).sum()
    highest_high = df['high'].rolling(window=window).max()
    lowest_low = df['low'].rolling(window=window).min()
    
    chop = 100 * np.log10(sum_tr / (highest_high - lowest_low)) / np.log10(window)
    return chop

def analyze_advanced_indicators(df: pd.DataFrame) -> dict:
    """
    Applies MACD, ATR, Bollinger Bands and Choppiness index.
    Returns the latest indicator values and a trend verdict.
    """
    if df is None or len(df) < 50:
        return {"signal": "HOLD", "reason": "Not enough data"}

    # 1. MACD
    macd_obj = MACD(close=df["close"])
    df["MACD"] = macd_obj.macd()
    df["MACD_Signal"] = macd_obj.macd_signal()
    df["MACD_Hist"] = macd_obj.macd_diff()

    # 2. Average True Range (ATR)
    atr_obj = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["ATR"] = atr_obj.average_true_range()

    # 3. Bollinger Bands
    bb_obj = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_High"] = bb_obj.bollinger_hband()
    df["BB_Low"] = bb_obj.bollinger_lband()
    df["BB_Mid"] = bb_obj.bollinger_mavg()
    df["BB_Width"] = bb_obj.bollinger_wband()   # Percent width

    # 4. Choppiness Index (CHOP)
    df["CHOP"] = calculate_choppiness_index(df, window=14)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Analysis Logic
    is_trending = latest["CHOP"] < 38.2
    is_choppy = latest["CHOP"] > 61.8

    macd_bullish = latest["MACD"] > latest["MACD_Signal"] and latest["MACD_Hist"] > 0
    macd_bearish = latest["MACD"] < latest["MACD_Signal"] and latest["MACD_Hist"] < 0

    above_bb_mid = latest["close"] > latest["BB_Mid"]
    below_bb_mid = latest["close"] < latest["BB_Mid"]

    # Basic Trend Rule
    signal = "HOLD"
    reason = "Market lacks clear aggressive momentum."

    if is_trending:
        if macd_bullish and above_bb_mid:
            signal = "BUY_CALL"
            reason = "Trending Market (CHOP < 38.2) + MACD Bullish + Price > BB Mid."
        elif macd_bearish and below_bb_mid:
            signal = "BUY_PUT"
            reason = "Trending Market (CHOP < 38.2) + MACD Bearish + Price < BB Mid."
    else:
        if is_choppy:
            reason = "Choppy Market (CHOP > 61.8). Expect reversals at BB margins; directional trades highly risky."
            # Maybe faded extremes?
            if latest["close"] <= latest["BB_Low"] and latest["MACD_Hist"] > prev["MACD_Hist"]:
                 signal = "BUY_CALL"
                 reason = "Choppy Reversal setup: Price at BB Low + MACD Hist rising."
            elif latest["close"] >= latest["BB_High"] and latest["MACD_Hist"] < prev["MACD_Hist"]:
                 signal = "BUY_PUT"
                 reason = "Choppy Reversal setup: Price at BB High + MACD Hist falling."
        else:
            reason = "Range-bound/Normal consolidation phase. Wait for CHOP to dictate trend."
            if macd_bullish and latest["close"] > latest["BB_Mid"]:
                 signal = "BUY_CALL_WEAK"
            elif macd_bearish and latest["close"] < latest["BB_Mid"]:
                 signal = "BUY_PUT_WEAK"

    return {
        "signal": signal,
        "reason": reason,
        "macd": latest["MACD"],
        "macd_hist": latest["MACD_Hist"],
        "atr": latest["ATR"],
        "bb_high": latest["BB_High"],
        "bb_low": latest["BB_Low"],
        "bb_mid": latest["BB_Mid"],
        "chop": latest["CHOP"],
        "close": latest["close"]
    }

def generate_verdict(signal_data: dict, opt_type: str) -> str:
    signal = signal_data["signal"]
    verdict = ""
    
    if opt_type == "CE":
         if signal == "BUY_CALL":
             verdict = "🟢 HIGH CONVICTION BUY TRIGGERED (Aligned with bullish indicators)"
         elif signal == "BUY_CALL_WEAK":
             verdict = "🟡 SCALP BUY (Weak bullish momentum, target small points)"
         elif signal in ["BUY_PUT", "BUY_PUT_WEAK"]:
             verdict = "🛑 REJECT (Trend is Bearish, avoid CALLs)"
         else:
             verdict = f"⚪ HOLD / AVOID: {signal_data['reason']}"
    else:
         if signal == "BUY_PUT":
             verdict = "🔴 HIGH CONVICTION BUY TRIGGERED (Aligned with bearish indicators)"
         elif signal == "BUY_PUT_WEAK":
             verdict = "🟡 SCALP BUY (Weak bearish momentum, target small points)"
         elif signal in ["BUY_CALL", "BUY_CALL_WEAK"]:
             verdict = "🛑 REJECT (Trend is Bullish, avoid PUTs)"
         else:
             verdict = f"⚪ HOLD / AVOID: {signal_data['reason']}"
             
    return verdict

def print_report(parsed: dict, opt_ltp: float, num_lots: int, lot_size: int, capital_req: float, signal_data: dict):
    print("\n" + "="*70)
    print(f" 📊 V1 ADVANCED EVALUATOR: {parsed['stock_code']} {parsed['expiry_date']} {parsed['strike']} {parsed['opt_type']}")
    print(f"    (Focus: MACD, ATR, Bollinger, CHOP for Last 2 Days)")
    print("="*70)
    
    if opt_ltp > 0:
        print(f"💸 Live Premium        : ₹{opt_ltp}")
        available = float(os.getenv("AVAILABLE_FUNDS", "50000"))
        
        if num_lots > 0:
            print(f"📦 Affordability        : {num_lots} Lots [{num_lots * lot_size} Qty] using ₹{available} budget")
        else:
            print(f"⚠️ Warning              : Budget insufficient. 1 lot costs ₹{round(opt_ltp * lot_size, 2)}")
            
        print("-"*70)
        target = opt_ltp + (signal_data.get('atr', 0) * 0.2) # example target based on ATR
        sl = opt_ltp - (signal_data.get('atr', 0) * 0.1)     # example sl based on ATR
        
        print(f"🚀 VOLATILITY PARAMETERS:")
        print(f"   Target          : Opt Price + (Premium ATR ~20%) [~₹{round(target, 2)}]")
        print(f"   Dynamic Stop-Loss: Opt Price - (Premium ATR ~10%) [~₹{round(sl, 2)}]")
    else:
        print("⚠️ Live Premium       : Contract NOT FOUND in current active chain.")
        
    print("-"*70)
    print(f"📡 5-Min Spot Technical Data (Last 2 Trading Days):")
    print(f"   Spot Price    : {signal_data.get('close', 0):.2f}")
    print(f"   MACD Hist     : {signal_data.get('macd_hist', 0):.2f}")
    print(f"   ATR           : {signal_data.get('atr', 0):.2f} (Volatility)")
    print(f"   Bollinger     : Low={signal_data.get('bb_low', 0):.2f} | Mid={signal_data.get('bb_mid', 0):.2f} | High={signal_data.get('bb_high', 0):.2f}")
    
    chop_val = signal_data.get('chop', 50)
    chop_str = "TRENDING" if chop_val < 38.2 else "CHOPPY/RANGE" if chop_val > 61.8 else "NORMAL"
    print(f"   CHOP Index    : {chop_val:.2f} ({chop_str})")
    
    print(f"\n   >> SIGNAL      : {signal_data.get('signal', 'HOLD')}")
    print(f"   >> REASON      : {signal_data.get('reason', '')}")
    
    print("="*70)
    final_decision = generate_verdict(signal_data, parsed['opt_type'])
    print(f"🎯 FINAL VERDICT: {final_decision}")
    print("="*70 + "\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluate_contract_V1.py \"<CONTRACT_STRING>\"")
        print("Example: python evaluate_contract_V1.py \"cnxban 28 Apr 48800 PE\"")
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
        
    print(f"Fetching 5-Minute Live Technicals (Last 2 Days) & Verifying Contract...")
    
    # Fetch 5 min trend
    spot_df = fetch_multiday_data(breeze, parsed['stock_code'], "NSE", "5minute", days_back=7)
    
    if spot_df.empty:
        print("[ERROR] Could not fetch historic data. Check API or trading hours.")
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
