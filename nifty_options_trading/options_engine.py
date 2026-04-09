"""
Core Data Pipeline Engine
Handles API connections to ICICI Breeze to parse option grids and chain dataframes.

Author: Aditya Kota
"""
import pandas as pd
from datetime import datetime
from breeze_connect import BreezeConnect

def get_option_chain(breeze: BreezeConnect, stock_code: str, expiry_date: str) -> pd.DataFrame:
    """
    Fetches the option chain for a given stock code and expiry date using the Breeze API.
    Returns a pandas DataFrame containing strike prices, calls, and puts data.
    
    Parameters:
        breeze: Authenticated BreezeConnect instance.
        stock_code: Symbol (e.g., "NIFTY").
        expiry_date: Expiry date string in ISO format "YYYY-MM-DD" or format required by API.
    """
    print(f"Fetching Option Chain for {stock_code} expiring on {expiry_date}")
    
    try:
        # Breeze get_option_chain_quotes API can sometimes be finicky with "others".
        # We will fetch Call and Put options separately and combine them.
        calls_response = breeze.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code="NFO",
            product_type="options",
            expiry_date=f"{expiry_date}T06:00:00.000Z",
            right="Call" 
        )
        puts_response = breeze.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code="NFO",
            product_type="options",
            expiry_date=f"{expiry_date}T06:00:00.000Z",
            right="Put" 
        )
        
        all_chain_data = []
        if calls_response and calls_response.get('Status') == 200 and calls_response.get('Success'):
            all_chain_data.extend(calls_response['Success'])
        if puts_response and puts_response.get('Status') == 200 and puts_response.get('Success'):
            all_chain_data.extend(puts_response['Success'])
            
        if all_chain_data:
            df = pd.DataFrame(all_chain_data)
            df['strike_price'] = df['strike_price'].astype(float)
            df['open_interest'] = df['open_interest'].astype(float)
            df['last_traded_price'] = pd.to_numeric(df.get('ltp', df.get('last_traded_price', 0)), errors='coerce')
            return df
        else:
            print(f"Error fetching option chain. Ensure {expiry_date} is an exact NSE trading expiry date. API Response: {calls_response} / {puts_response}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"Exception during option chain fetch: {e}")
        return pd.DataFrame()
