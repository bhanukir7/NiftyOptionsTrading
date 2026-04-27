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

from nifty_options_trading.safe_breeze import SafeBreeze
from nifty_options_trading.options_engine import get_option_chain, get_dynamic_lot_size

load_dotenv(os.path.join(parent_dir, '.env'))

from nifty_options_trading.global_cues import fetch_world_markets, derive_btst_cues

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

def initialize_breeze() -> SafeBreeze:
    breeze = SafeBreeze(api_key=API_KEY)
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

def fetch_multiday_data(breeze: SafeBreeze, stock_code: str, exchange_code: str, interval: str, days_back=90) -> pd.DataFrame:
    # --- YFINANCE FALLBACK LOGIC ---
    # Common symbols for fallback
    ticker_map = {
        "BSESN": "^BSESN", "BSEX": "^BSEBANK", "SENSEX": "^BSESN", "BANKEX": "^BSEBANK",
        "NIFTY": "^NSEI", "CNXBAN": "^NSEBANK", "BANKNIFTY": "^NSEBANK", "NIFTY50": "^NSEI"
    }
    
    def try_yf_fallback(symbol, interval_str, days):
        try:
            import yfinance as yf
            ticker = ticker_map.get(symbol.upper(), symbol.upper())
            
            yf_interval = {"5minute": "5m", "1day": "1d", "1minute": "1m"}.get(interval_str, "1d")
            # Use Ticker.history for reliable data
            data = yf.Ticker(ticker).history(period=f"{days}d", interval=yf_interval)
            if not data.empty:
                df = data.reset_index()
                df.columns = [str(c).lower() for c in df.columns]
                # Map yf columns to breeze format
                rename_map = {'date': 'datetime', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'}
                df.rename(columns=rename_map, inplace=True)
                # Ensure datetime is pd.to_datetime
                if 'datetime' in df.columns:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                return df
        except Exception:
            pass
        return pd.DataFrame()

    # Try Breeze for all exchanges first
    try:
        now_dt = datetime.now()
        iso_date = now_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") 
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
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"])
                df = df.reset_index(drop=True)
                return df
            else:
                print(f"[BREEZE SDK] Missing 'datetime' column in response: {df.columns}")
        else:
            print(f"[BREEZE SDK] Historical data error: {response}")
            # If Breeze fails for known indices, try yfinance fallback
            if stock_code.upper() in ticker_map:
                return try_yf_fallback(stock_code, interval, days_back)
                
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
        return {"close_strength": 50, "close": 0, "macd_bullish": False, "above_bb_mid": False}

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

    return {
        "macd": latest["MACD"],
        "macd_hist": latest["MACD_Hist"],
        "bb_high": latest["BB_High"],
        "bb_low": latest["BB_Low"],
        "bb_mid": latest["BB_Mid"],
        "close_strength": close_strength_pct,
        "close": latest["close"],
        "macd_bullish": macd_bullish,
        "macd_bearish": macd_bearish,
        "above_bb_mid": above_bb_mid,
        "below_bb_mid": below_bb_mid
    }

def analyze_oi(chain_df: pd.DataFrame, spot_price: float) -> dict:
    if chain_df is None or chain_df.empty:
        return {"support_below": False, "pcr": 1.0}
        
    try:
        total_call_oi = chain_df[chain_df['right'].str.title() == 'Call']['open_interest'].sum()
        total_put_oi = chain_df[chain_df['right'].str.title() == 'Put']['open_interest'].sum()
        
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0
        
        put_df = chain_df[chain_df['right'].str.title() == 'Put']
        if not put_df.empty:
            highest_oi_idx = put_df['open_interest'].idxmax()
            highest_put_strike = float(put_df.loc[highest_oi_idx, 'strike_price'])
            support_below = highest_put_strike < spot_price
        else:
            support_below = False
            
        return {"support_below": support_below, "pcr": round(pcr, 2)}
    except Exception as e:
        print(f"Error analyzing OI: {e}")
        return {"support_below": False, "pcr": 1.0}

def estimate_iv(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 14:
        return {"iv_percentile": 50}
    
    try:
        atr_obj = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_obj.average_true_range()
        
        iv_proxy = (atr / df['close']) * 100
        last_iv = iv_proxy.iloc[-1]
        
        lookback = min(60, len(iv_proxy))
        recent_ivs = iv_proxy.iloc[-lookback:].dropna()
        
        if len(recent_ivs) > 0:
            percentile = (recent_ivs < last_iv).mean() * 100
        else:
            percentile = 50
            
        return {"iv_percentile": min(max(int(percentile), 0), 100)}
    except Exception as e:
        print(f"Error estimating IV: {e}")
        return {"iv_percentile": 50}

def get_automated_global_cues() -> dict:
    """Fetch live world markets and derive cues for BTST."""
    print("Fetching live world market data (yfinance)...")
    world = fetch_world_markets()
    markets = world.get("markets", [])
    cue_data = derive_btst_cues(markets)
    return cue_data

def compute_btst_score(signal_data: dict, oi_data: dict, iv_data: dict, global_data: dict, is_put: bool = False) -> int:
    score = 0
    
    # A. Price Action (35 points)
    if is_put:
        if signal_data.get("macd_bearish", False):
            score += 10
        if signal_data.get("below_bb_mid", False):
            score += 10
        # For puts, low closing strength (closing near day low) is bearish/good for carry
        cs = signal_data.get("close_strength", 50)
        cs_points = int(((100 - cs) / 100.0) * 15)
        score += cs_points
    else:
        if signal_data.get("macd_bullish", False):
            score += 10
        if signal_data.get("above_bb_mid", False):
            score += 10
        cs = signal_data.get("close_strength", 50)
        cs_points = int((cs / 100.0) * 15)
        score += cs_points
    
    # B. OI + PCR (25 points)
    # PCR is generally bullish if high (>1.0), but extreme (>1.5) might be overextended
    # Support below is always good for a trade (floor for calls, ceiling for puts?) 
    # Actually, for Puts, we want "Resistance Above". 
    # To keep it simple, we use PCR and support logic.
    if oi_data.get("support_below", False):
        score += 15
    pcr = oi_data.get("pcr", 1.0)
    if 0.8 <= pcr <= 1.2:
        score += 10
        
    # C. IV (10 points) - IV rising is generally good for buying options (if it continues)
    iv_p = iv_data.get("iv_percentile", 50)
    if iv_p < 60:
        score += 10
    elif iv_p > 80:
        score -= 5
        
    # D. Global Cues (30 points total)
    # Using 40/60 Weightage between Indian Core and International
    
    # Core India (40% weight -> 12 points)
    core_cue = global_data.get("derived_cues", {}).get("core_india", {})
    core_sig = core_cue.get("signal", "FLAT")
    
    # International (60% weight -> 18 points)
    global_cue = global_data.get("derived_cues", {}).get("global_market", {})
    global_sig = global_cue.get("signal", "FLAT")

    if is_put:
        # For Puts, DOWN is good
        if core_sig == "DOWN": score += 12
        elif core_sig == "UP":   score -= 8
        
        if global_sig == "DOWN": score += 18
        elif global_sig == "UP":   score -= 12
    else:
        # For Calls, UP is good
        if core_sig == "UP":     score += 12
        elif core_sig == "DOWN": score -= 8
        
        if global_sig == "UP":   score += 18
        elif global_sig == "DOWN": score -= 12

    return min(max(score, 0), 100)

def generate_score_verdict(score: int) -> str:
    if score >= 75:
        return "HIGH PROBABILITY (not guaranteed)"
    elif 60 <= score < 75:
        return "MODERATE EDGE"
    elif 45 <= score < 60:
        return "LOW EDGE"
    else:
        return "NO TRADE"

def print_report(parsed: dict, opt_ltp: float, num_lots: int, lot_size: int, capital_req: float, 
                 signal_data: dict, oi_data: dict, iv_data: dict, global_data: dict, score: int):
    print("\n" + "="*75)
    print(f" BTST PROBABILISTIC EVALUATOR: {parsed['stock_code']} {parsed['expiry_date']} {parsed['strike']} {parsed['opt_type']}")
    print(f"    (Focus: Price Action, Options Data, Global Cues)")
    print("="*75)
    
    if opt_ltp > 0:
        print(f"Live Premium        : Rs.{opt_ltp}")
        available = float(os.getenv("AVAILABLE_FUNDS", "50000"))
        
        if num_lots > 0:
            print(f"Affordability        : {num_lots} Lots [{num_lots * lot_size} Qty] using Rs.{available} budget")
        else:
            print(f"Warning              : Budget insufficient. 1 lot costs Rs.{round(opt_ltp * lot_size, 2)}")
            
        print("-" * 75)
        # Wider targets for BTST given opening volatility
        target1 = opt_ltp * 1.15
        target2 = opt_ltp * 1.30
        sl = opt_ltp * 0.90
        
        print(f"BTST OPENING TARGETS (High Volatility Setup):")
        print(f"   Target 1 (+15%) : [~Rs.{round(target1, 2)}] (Take early profit on gap)")
        print(f"   Target 2 (+30%) : [~Rs.{round(target2, 2)}] (Hold runner)")
        print(f"   Stop-Loss (-10%): [~Rs.{round(sl, 2)}] (Strict stop if gap fails)")
    else:
        print("Live Premium       : Contract NOT FOUND in current active chain.")
        
    print("-" * 75)
    print(f"PROBABILISTIC INSIGHTS:")
    print(f"   BTST Score    : {score}/100")
    print(f"   PCR           : {oi_data.get('pcr', 1.0)}")
    print(f"   Support Below : {'YES' if oi_data.get('support_below', False) else 'NO'}")
    print(f"   IV Percentile : {iv_data.get('iv_percentile', 50)}/100")
    
    print(f"   Global Cues   : Gift Nifty={global_data.get('gift_nifty', 'FLAT')} | US={global_data.get('us_market', 'FLAT')} | Europe={global_data.get('europe_market', 'FLAT')} | Asia={global_data.get('asia_market', 'FLAT')}")
    print(f"   India VIX     : {global_data.get('vix', 0.0):+.2f}% ({'Calm' if global_data.get('vix', 0.0) < 0 else 'Rising Fear'})")
    
    print("-" * 75)
    final_decision = generate_score_verdict(score)
    print(f"BTST VERDICT: [{score}/100] {final_decision}")
    
    print("\n   DISCLAIMERS:")
    print("   - BTST is probability-based, not guaranteed.")
    print("   - Option premium may decay due to IV changes overnight.")
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
    exchange = "BSE" if parsed['stock_code'] in ["BSESEN", "SENSEX", "BANKEX"] else "NSE"
    spot_df = fetch_multiday_data(breeze, parsed['stock_code'], exchange, "1day", days_back=90)
    
    if spot_df.empty:
        print("[ERROR] Could not fetch historic 1D data. Check API or trading hours.")
        sys.exit(1)
        
    signal_data = analyze_advanced_indicators(spot_df)
        
    chain_df = get_option_chain(breeze, parsed['stock_code'], parsed['expiry_date'])
    
    # 3. Analyze OI
    spot_price = signal_data.get("close", 0.0)
    oi_data = analyze_oi(chain_df, spot_price)
    
    # 4. Estimate IV
    iv_data = estimate_iv(spot_df)
    
    # 5. Get Automated Global Cues
    global_data = get_automated_global_cues()
    
    # 6. Compute BTST Score
    is_put = (parsed['opt_type'] == "PE")
    score = compute_btst_score(signal_data, oi_data, iv_data, global_data, is_put=is_put)
    
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
            lot_size = get_dynamic_lot_size(parsed['stock_code'])
            available_funds = float(os.getenv("AVAILABLE_FUNDS", "50000"))
            
            if opt_ltp > 0:
                lot_cost = opt_ltp * lot_size
                num_lots = int(available_funds / lot_cost)
                capital_req = num_lots * lot_cost
                
    print_report(parsed, opt_ltp, num_lots, lot_size, capital_req, signal_data, oi_data, iv_data, global_data, score)
    breeze.log_api_usage()

if __name__ == "__main__":
    main()
