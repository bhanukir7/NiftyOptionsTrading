"""
Intraday Options Engine V3 (Multi-Strike Evaluator)
Evaluates trailing market momentum using 5-minute technical indicators and selects 3 close strikes (ITM/ATM/OTM).
Evaluates their risk-reward targets based on the current market direction.

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

from nifty_options_trading.safe_breeze import SafeBreeze
from nifty_options_trading.options_engine import get_option_chain, get_dynamic_lot_size

load_dotenv(os.path.join(parent_dir, '.env'))

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

def initialize_breeze() -> SafeBreeze:
    breeze = SafeBreeze(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    return breeze

def parse_input_string(contract_str: str) -> dict:
    parts = re.split(r'\s+', contract_str.strip())
    if len(parts) < 4:
        raise ValueError("Invalid format. Expected: 'SYMBOL DD MMM TYPE' (e.g. 'cnxban 28 apr PE')")
        
    stock_code = parts[0].upper()
    day = parts[1]
    month = parts[2].capitalize()
    
    # Support both 4 and 5 parts if user accidentally provides a strike
    if len(parts) == 4:
        opt_type = parts[3].upper()
    else:
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
        "opt_type": "CE" if opt_type in ["CE", "CALL"] else "PE" 
    }

def fetch_multiday_data(breeze, stock_code: str, exchange_code: str, interval: str, days_back=7) -> pd.DataFrame:
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
        
        if response and response.get("Status") == 200 and "Success" in response:
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

    # Focus exclusively on the latest data points (Current Date Action)
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
            reason = "Choppy Market (CHOP > 61.8). Expect reversals at BB margins;"
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

def print_report(parsed: dict, chain_targets: pd.DataFrame, signal_data: dict):
    print("\n" + "="*80)
    print(f" 📊 V3 STRATEGY EVALUATOR: {parsed['stock_code']} {parsed['expiry_date']} MULTI-STRIKE {parsed['opt_type']}")
    print(f"    (Focus: Current Date Technicals & Up to 4 Strikes Above/Below)")
    print("="*80)
    
    print(f"📡 5-Min Spot Technical Data (Current Date Latest):")
    print(f"   Spot Price    : {signal_data.get('close', 0):.2f}")
    print(f"   MACD Hist     : {signal_data.get('macd_hist', 0):.2f}")
    print(f"   ATR           : {signal_data.get('atr', 0):.2f} (Volatility)")
    print(f"   Bollinger     : Low={signal_data.get('bb_low', 0):.2f} | Mid={signal_data.get('bb_mid', 0):.2f} | High={signal_data.get('bb_high', 0):.2f}")
    
    chop_val = signal_data.get('chop', 50)
    chop_str = "TRENDING" if chop_val < 38.2 else "CHOPPY/RANGE" if chop_val > 61.8 else "NORMAL"
    print(f"   CHOP Index    : {chop_val:.2f} ({chop_str})")
    
    print(f"\n   >> SIGNAL      : {signal_data.get('signal', 'HOLD')}")
    print(f"   >> REASON      : {signal_data.get('reason', '')}")
    
    print("="*80)
    final_decision = generate_verdict(signal_data, parsed['opt_type'])
    print(f"🎯 FINAL VERDICT: {final_decision}")
    print("="*80)
    
    if chain_targets.empty:
        print("\n⚠️ Note: No valid contracts found in the option chain for evaluation.")
    else:
        print("\n🚀 CLOSEST STRIKES EVALUATION:\n")
        available = float(os.getenv("AVAILABLE_FUNDS", "50000"))
        lot_size = get_dynamic_lot_size(parsed['stock_code'])
        
        for idx, row in chain_targets.iterrows():
            strike = row['strike_price']
            opt_ltp = float(row.get('last_traded_price', 0))
            
            print(f"✨ STRIKE: {strike} {parsed['opt_type']}")
            if opt_ltp > 0:
                print(f"   Live Premium  : ₹{opt_ltp}")
                lot_cost = opt_ltp * lot_size
                num_lots = int(available / lot_cost) if lot_cost > 0 else 0
                
                if num_lots > 0:
                    print(f"   Affordability : {num_lots} Lots [{num_lots * lot_size} Qty] using ₹{available} budget")
                else:
                    print(f"   Warning       : Budget insufficient. 1 lot costs ₹{round(lot_cost, 2)}")
                
                target1 = opt_ltp * 1.05
                target2 = opt_ltp * 1.10
                sl = opt_ltp * 0.97
                
                print(f"   Targets       : Target 1: ₹{round(target1, 2)} (+5%) | Target 2: ₹{round(target2, 2)} (+10%) | SL: ₹{round(sl, 2)} (-3%)")
            else:
                print("   Live Premium  : ₹0.0 (No trades or stale premium)")
            print("-" * 80)
    print("\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluate_contract_V3.py \"<CONTRACT_STRING>\"")
        print("Example: python evaluate_contract_V3.py \"cnxban 28 Apr PE\"")
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
        
    print(f"Fetching 5-Minute Live Technicals (Current Date)...")
    spot_df = fetch_multiday_data(breeze, parsed['stock_code'], "NSE", "5minute", days_back=7)
    
    if spot_df.empty:
        print("[ERROR] Could not fetch historic data. Check API or trading hours.")
        sys.exit(1)
        
    signal_data = analyze_advanced_indicators(spot_df)
    
    print(f"Fetching Option Chain Data to find optimal strikes...")
    chain_df = get_option_chain(breeze, parsed['stock_code'], parsed['expiry_date'])
    
    target_contracts = pd.DataFrame()
    if chain_df is not None and not chain_df.empty:
        spot_price = signal_data.get('close', 0)
        opt_type_full = "CALL" if parsed['opt_type'] == "CE" else "PUT"
        
        # Filter chain for CE/PE only
        chain_filtered = chain_df[chain_df['right'].str.upper().isin([opt_type_full, parsed['opt_type']])].copy()
        
        if not chain_filtered.empty and spot_price > 0:
            chain_filtered['strike_price'] = chain_filtered['strike_price'].astype(float)
            
            atm_diff = (chain_filtered['strike_price'] - spot_price).abs()
            atm_strike_idx = atm_diff.idxmin()
            atm_strike = chain_filtered.loc[atm_strike_idx, 'strike_price']
            
            unique_strikes = sorted(chain_filtered['strike_price'].unique())
            try:
                atm_pos = unique_strikes.index(atm_strike)
                start_pos = max(0, atm_pos - 4)
                end_pos = min(len(unique_strikes), atm_pos + 5)
                selected_strikes = unique_strikes[start_pos:end_pos]
            except ValueError:
                selected_strikes = []
                
            target_contracts = chain_filtered[chain_filtered['strike_price'].isin(selected_strikes)].copy()
            target_contracts = target_contracts.sort_values(by='strike_price')
            
    print_report(parsed, target_contracts, signal_data)
    breeze.log_api_usage()

if __name__ == "__main__":
    main()
