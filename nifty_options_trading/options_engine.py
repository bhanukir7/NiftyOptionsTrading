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

import os
import zipfile
import urllib.request

class SecurityMasterCache:
    _master_df = None
    _last_date = None

    @classmethod
    def get_lot_size(cls, stock_code: str) -> int:
        today_date_str = datetime.now().strftime("%Y%m%d")
        
        # In-memory cache hit
        if cls._master_df is not None and cls._last_date == today_date_str:
            row = cls._master_df[cls._master_df['ShortName'] == stock_code]
            if not row.empty:
                return int(row.iloc[0]['LotSize'])
            return 1 # Fallback
            
        # Download and extract if missing
        file_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(file_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        txt_path = os.path.join(log_dir, f"FONSEScripMaster_{today_date_str}.txt")
        zip_path = os.path.join(log_dir, "SecurityMaster.zip")
        
        if not os.path.exists(txt_path):
            print(f"Downloading ICICI SecurityMaster for {today_date_str} to extract live Lot Sizes...")
            try:
                urllib.request.urlretrieve("https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip", zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extract("FONSEScripMaster.txt", log_dir)
                os.rename(os.path.join(log_dir, "FONSEScripMaster.txt"), txt_path)
                if os.path.exists(zip_path):
                    os.remove(zip_path) # cleanup
            except Exception as e:
                print(f"Failed to download Security Master: {e}")
                return 1 # Fallback on error
                
        # Load CSV into memory
        if os.path.exists(txt_path):
            try:
                cls._master_df = pd.read_csv(txt_path, usecols=['ShortName', 'LotSize'])
                cls._last_date = today_date_str
                row = cls._master_df[cls._master_df['ShortName'] == stock_code]
                if not row.empty:
                    return int(row.iloc[0]['LotSize'])
            except Exception as e:
                print(f"Failed to parse Security Master: {e}")
                
        return 1

def get_dynamic_lot_size(stock_code: str) -> int:
    """Public wrapper to fetch lot size transparently."""
    return SecurityMasterCache.get_lot_size(stock_code)
