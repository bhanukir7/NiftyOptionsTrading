import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from breeze_connect import BreezeConnect
from strategy import analyze_and_generate_signal
from alerts import send_alert

# Load environment variables
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

def initialize_breeze() -> BreezeConnect:
    """Initialize the Breeze API connection."""
    print("Initializing Breeze API...")
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    print("Breeze API successfully initialized.")
    return breeze

def fetch_historical_data(breeze: BreezeConnect, stock_code: str, exchange_code: str, interval: str) -> pd.DataFrame:
    """
    Fetch historical data for a given stock code to calculate indicators.
    Normally you might use web sockets for live ticks, but this polls history for simplicity.
    """
    try:
        # Example: Fetching data for the current day
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
            # Ensure proper types
            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df
        else:
            print(f"Error fetching data: {response}")
            return None
    except Exception as e:
        print(f"Exception during data fetch: {e}")
        return None

def main():
    if not API_KEY or not API_SECRET or not SESSION_TOKEN:
        print("[ERROR] Missing API_KEY, API_SECRET, or SESSION_TOKEN in .env. Please configure them.")
        return

    try:
        breeze = initialize_breeze()
    except Exception as e:
        print(f"[ERROR] Failed to initialize Breeze API. Ensure your Session Token is valid for today, and IP is whitelisted. Details: {e}")
        return
        
    STOCK_CODES = ["NIFTY", "CNXBAN"] # Add more stocks to this list
    EXCHANGE_CODE = "NSE"
    INTERVAL = "5minute" # Can be 1minute, 5minute, etc.
    
    print(f"Starting Multi-Stock Options Alert Monitor (Interval: {INTERVAL})...")
    print(f"Monitoring: {', '.join(STOCK_CODES)}")
    
    # Store the last known signal for each stock so we don't spam duplicate alerts
    last_alerted_signals = {stock: "HOLD" for stock in STOCK_CODES}
    
    while True:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time_str}] Fetching data and analyzing...")
        
        for stock_code in STOCK_CODES:
            df = fetch_historical_data(breeze, stock_code, EXCHANGE_CODE, INTERVAL)
            
            if df is not None and not df.empty:
                signal = analyze_and_generate_signal(df)
                
                if signal != "HOLD" and signal != last_alerted_signals[stock_code]:
                    spot_price = df.iloc[-1]["close"]
                    
                    # Calculate exact At-The-Money (ATM) strike price rounded to nearest 100
                    atm_strike = int(round(spot_price / 100.0) * 100)
                    
                    # Determine whether we are buying a Call (CE) or Put (PE)
                    option_type = "CE" if signal == "BUY_CALL" else "PE"
                    recommended_contract = f"{stock_code} {atm_strike} {option_type}"
                    
                    message = (f"🚨 {signal} ALERT 🚨\n"
                               f"{stock_code} Spot Price: {spot_price}\n"
                               f"Recommended Trade: Buy {recommended_contract} (ATM)")
                               
                    send_alert(message)
                    last_alerted_signals[stock_code] = signal
                else:
                    print(f"[{current_time_str}] {stock_code} Signal: {signal}")
                    
            # Small 1-second pause between each stock to respect API rate limits
            time.sleep(1)
            
        # Wait 60 seconds before next overall check
        time.sleep(60)

if __name__ == "__main__":
    main()
