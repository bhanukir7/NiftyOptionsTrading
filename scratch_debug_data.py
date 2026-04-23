import os
from nifty_options_trading.evaluate_contract_V3 import initialize_breeze, fetch_multiday_data
import pandas as pd

def debug_nifty_data():
    try:
        breeze = initialize_breeze()
        print("Fetching NIFTY data...")
        df = fetch_multiday_data(breeze, "NIFTY", "NSE", "5minute", days_back=2)
        
        if df.empty:
            print("DataFrame is empty!")
            return
            
        print(f"Columns: {df.columns.tolist()}")
        print(f"Sample data:\n{df.head()}")
        print(f"NaN count:\n{df.isna().sum()}")
        print(f"Volume sample: {df['volume'].head().tolist()}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_nifty_data()
