"""
Core Data Pipeline Engine
Handles API connections to ICICI Breeze to parse option grids and chain dataframes.

Author: Aditya Kota
"""
import pandas as pd
from datetime import datetime
from nifty_options_trading.broker_interface import BaseBroker

def get_option_chain(broker: BaseBroker, stock_code: str, expiry_date: str) -> pd.DataFrame:
    """
    Fetches the option chain for a given stock code and expiry date using the Breeze API.
    Returns a pandas DataFrame containing strike prices, calls, and puts data.
    
    Parameters:
        breeze: Authenticated BreezeConnect instance.
        stock_code: Symbol (e.g., "NIFTY").
        expiry_date: Expiry date string in ISO format "YYYY-MM-DD" or format required by API.
    """
    print(f"Fetching Option Chain for {stock_code} expiring on {expiry_date}")
    
    # Standardize BSE Index symbols for Breeze
    s = stock_code.upper()
    if s in ["SENSEX", "BSESN", "BSESEN"]:
        stock_code = "BSESEN"
    if s == "BANKEX":
        stock_code = "BANKEX"
        
    # Determine the correct exchange code (NFO vs BFO)
    exch_code = "BFO" if stock_code.upper() in ["BSESEN", "BANKEX"] else "NFO"

    try:
        # Breeze get_option_chain_quotes API can sometimes be finicky with "others".
        # We will fetch Call and Put options separately and combine them.
        calls_response = broker.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code=exch_code,
            product_type="options",
            expiry_date=f"{expiry_date}T06:00:00.000Z",
            right="Call" 
        )
        puts_response = broker.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code=exch_code,
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
            df['strike_price'] = pd.to_numeric(df['strike_price'], errors='coerce').fillna(0)
            df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)
            df['last_traded_price'] = pd.to_numeric(df.get('ltp', df.get('last_traded_price', 0)), errors='coerce')
            return df
        else:
            # Only print if not after hours or if session is actually valid
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
            
        nse_txt_path = os.path.join(log_dir, f"FONSEScripMaster_{today_date_str}.txt")
        bse_txt_path = os.path.join(log_dir, f"FOBSEScripMaster_{today_date_str}.txt")
        zip_path = os.path.join(log_dir, "SecurityMaster.zip")
        
        if not os.path.exists(nse_txt_path) or not os.path.exists(bse_txt_path):
            # Cleanup old master files before downloading new one
            import glob
            old_masters = glob.glob(os.path.join(log_dir, "*ScripMaster_*.txt"))
            for old_file in old_masters:
                try:
                    print(f"  [-] Cleaning up old master file: {os.path.basename(old_file)}")
                    os.remove(old_file)
                except:
                    pass

            print(f"Downloading ICICI SecurityMaster for {today_date_str} to extract live Lot Sizes...")
            try:
                urllib.request.urlretrieve("https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip", zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(log_dir) # Extract all files
                
                # Rename the specific files we need for F&O
                for prefix in ["FONSEScripMaster", "FOBSEScripMaster"]:
                    src = os.path.join(log_dir, f"{prefix}.txt")
                    dst = os.path.join(log_dir, f"{prefix}_{today_date_str}.txt")
                    if os.path.exists(src):
                        os.rename(src, dst)
                        
                if os.path.exists(zip_path):
                    os.remove(zip_path)  # cleanup
            except Exception as e:
                print(f"Failed to download Security Master: {e}")
                return 1  # Fallback on error

        # Load CSVs into memory — include all columns useful for trading
        dfs_to_concat = []
        for pth in [nse_txt_path, bse_txt_path]:
            if os.path.exists(pth):
                try:
                    _df = pd.read_csv(
                        pth,
                        usecols=[
                            'Token', 'InstrumentName', 'ShortName',
                            'ExpiryDate', 'StrikePrice', 'OptionType',
                            'LotSize', 'TickSize',
                            'LowPriceRange', 'HighPriceRange',
                        ],
                        dtype=str,
                    )
                    dfs_to_concat.append(_df)
                except Exception as e:
                    print(f"Failed to parse {os.path.basename(pth)}: {e}")
                    
        if dfs_to_concat:
            cls._master_df = pd.concat(dfs_to_concat, ignore_index=True)
            # Normalise numeric columns
            cls._master_df['LotSize']     = pd.to_numeric(cls._master_df['LotSize'],     errors='coerce').fillna(1).astype(int)
            cls._master_df['StrikePrice'] = pd.to_numeric(cls._master_df['StrikePrice'], errors='coerce').fillna(0)
            cls._master_df['TickSize']    = pd.to_numeric(cls._master_df['TickSize'],    errors='coerce').fillna(0.05)
            # Parse ExpiryDate → datetime (format "28-Apr-2026")
            cls._master_df['ExpiryDate']  = pd.to_datetime(
                cls._master_df['ExpiryDate'], format='%d-%b-%Y', errors='coerce'
            )
            cls._last_date = today_date_str
            row = cls._master_df[cls._master_df['ShortName'] == stock_code]
            if not row.empty:
                return int(row.iloc[0]['LotSize'])

        return 1

    @classmethod
    def _ensure_loaded(cls):
        """Load today's master if not already in memory."""
        cls.get_lot_size("_WARMUP_")  # triggers the load path

    @classmethod
    def get_token(cls, stock_code: str, strike: float, option_type: str, expiry_date) -> str | None:
        """
        Look up the Breeze instrument Token for a specific option contract.
        expiry_date can be a datetime.date or datetime.datetime object.
        Returns the token string, or None if not found.
        """
        cls._ensure_loaded()
        if cls._master_df is None:
            return None
        import datetime as _dt
        if isinstance(expiry_date, (_dt.date,)):
            expiry_dt = pd.Timestamp(expiry_date)
        else:
            expiry_dt = pd.Timestamp(expiry_date)
        df = cls._master_df
        # Match: short name, option type (CE/PE → Call/Put mapping in file is CE/PE directly)
        mask = (
            (df['ShortName'] == stock_code.upper()) &
            (df['OptionType'].str.upper() == option_type.upper()) &
            (df['StrikePrice'] == float(strike)) &
            (df['ExpiryDate'] == expiry_dt)
        )
        rows = df[mask]
        if not rows.empty:
            return rows.iloc[0]['Token']
        return None

    @classmethod
    def get_expiries(cls, stock_code: str, option_type: str = 'CE') -> list:
        """
        Return sorted list of available expiry dates (as date objects) for a symbol.
        """
        cls._ensure_loaded()
        if cls._master_df is None:
            return []
        df = cls._master_df
        mask = (
            (df['ShortName'] == stock_code.upper()) &
            (df['OptionType'].str.upper() == option_type.upper())
        )
        expiries = df[mask]['ExpiryDate'].dropna().drop_duplicates().sort_values()
        return [d.date() for d in expiries]

    @classmethod
    def get_strikes(cls, stock_code: str, expiry_date, option_type: str = 'CE') -> list:
        """
        Return sorted list of available strikes for a symbol + expiry from the local file.
        """
        cls._ensure_loaded()
        if cls._master_df is None:
            return []
        import datetime as _dt
        expiry_dt = pd.Timestamp(expiry_date)
        df = cls._master_df
        mask = (
            (df['ShortName'] == stock_code.upper()) &
            (df['OptionType'].str.upper() == option_type.upper()) &
            (df['ExpiryDate'] == expiry_dt)
        )
        return sorted(df[mask]['StrikePrice'].dropna().unique().tolist())

    @classmethod
    def get_tick_size(cls, stock_code: str) -> float:
        """Return the tick size for a symbol (default 0.05)."""
        cls._ensure_loaded()
        if cls._master_df is None:
            return 0.05
        row = cls._master_df[cls._master_df['ShortName'] == stock_code.upper()]
        if not row.empty:
            return float(row.iloc[0]['TickSize'])
        return 0.05


def get_dynamic_lot_size(stock_code: str) -> int:
    """Public wrapper to fetch lot size transparently."""
    s = stock_code.upper()
    if s in ["SENSEX", "BSESN", "BSESEN"]: stock_code = "BSESEN"
    if s == "BANKEX": stock_code = "BANKEX"
    return SecurityMasterCache.get_lot_size(stock_code)

def get_expiries(stock_code: str, option_type: str = 'CE') -> list:
    """Public wrapper to list available expiry dates from the Security Master."""
    s = stock_code.upper()
    if s in ["SENSEX", "BSESN", "BSESEN"]: stock_code = "BSESEN"
    if s == "BANKEX": stock_code = "BANKEX"
    return SecurityMasterCache.get_expiries(stock_code, option_type)

def get_strikes(stock_code: str, expiry_date, option_type: str = 'CE') -> list:
    """Public wrapper to list available strikes from the Security Master."""
    s = stock_code.upper()
    if s in ["SENSEX", "BSESN", "BSESEN"]: stock_code = "BSESEN"
    if s == "BANKEX": stock_code = "BANKEX"
    return SecurityMasterCache.get_strikes(stock_code, expiry_date, option_type)
