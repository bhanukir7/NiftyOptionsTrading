import os
import time
from typing import Dict, List, Optional, Any
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
from nifty_options_trading.api_rate_limiter import RateLimiter
from nifty_options_trading.cache_manager import CacheManager
from nifty_options_trading.broker_interface import BaseBroker

class SafeKite(BaseBroker):
    """
    A unified wrapper around the Zerodha Kite Connect API.
    Enforces Rate Limiting controls and leverages caching.
    """
    def __init__(self, api_key: str):
        self.kite = KiteConnect(api_key=api_key)
        self.rate_limiter = RateLimiter(max_per_min=180, max_per_day=10000)
        self.cache_manager = CacheManager()
        self._on_ticks_callback = None
        self.token_map = {} # Mapping from symbol to token
        self.token_to_symbol_map = {} # Mapping from token to symbol
        self.master_data = []
        self._download_master()
        
    def _download_master(self):
        """Downloads and parses the Zerodha instrument master."""
        try:
            print("[SafeKite] Downloading Instrument Master...")
            # Kite Connect's instruments() returns a list of dicts
            instruments = self.kite.instruments()
            self.master_data = instruments
            for item in instruments:
                symbol = item['tradingsymbol']
                token = item['instrument_token']
                self.token_map[symbol] = token
                self.token_to_symbol_map[token] = symbol
            print(f"[SafeKite] Loaded {len(self.token_map)} instruments.")
        except Exception as e:
            print(f"[SafeKite] Error downloading instrument master: {e}")
            
    def generate_session(self, api_secret: str, request_token: str, **kwargs):
        """Exchange request_token for access_token."""
        data = self.kite.generate_session(request_token, api_secret=api_secret)
        self.kite.set_access_token(data["access_token"])
        print(f"[SafeKite] Login successful for {data['user_id']}")
        return data

    def get_historical_data(self, stock_code: str, interval: str, from_date: str, to_date: str, **kwargs):
        # Kite interval mapping
        # Breeze: '5minute', '1day'
        # Kite: '5minute', 'day'
        kite_interval = {
            "5minute": "5minute",
            "1day": "day",
            "1minute": "minute"
        }.get(interval, interval)
        
        cache_key = f"hist_kite_{stock_code}_{interval}_{to_date}"
        ttl = 3600 if interval == "1day" else 60
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        token = self._get_token(stock_code)
        if not token:
            return {"Status": 404, "Error": f"Symbol {stock_code} not found in master"}
            
        self.rate_limiter.wait_if_needed()
        try:
            # Kite expects datetime objects
            from datetime import datetime
            f_dt = datetime.fromisoformat(from_date.replace("Z", ""))
            t_dt = datetime.fromisoformat(to_date.replace("Z", ""))
            
            res = self.kite.historical_data(token, f_dt, t_dt, kite_interval)
            self.rate_limiter.record_call()
            
            # Translate Kite format to Breeze-like format
            translated = {"Status": 200, "Success": []}
            for candle in res:
                translated["Success"].append({
                    "datetime": candle["date"].strftime("%Y-%m-%d %H:%M:%S"),
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle["volume"]
                })
            
            self.cache_manager.set(cache_key, translated, ttl)
            return translated
        except Exception as e:
            return {"Status": 500, "Error": str(e)}

    def get_option_chain_quotes(self, stock_code: str, expiry_date: str, right: str, **kwargs):
        """
        Simulates an option chain by filtering instruments and fetching quotes.
        Breeze expiry_date: YYYY-MM-DD
        """
        # Filter master for options
        opt_type = "CE" if right.lower() in ["call", "ce"] else "PE"
        
        filtered_tokens = []
        token_to_strike = {}
        
        # Kite expiry in instrument list is a date object
        from datetime import datetime
        try:
            target_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        except:
            target_expiry = expiry_date

        for item in self.master_data:
            if (item['name'] == stock_code.upper() and 
                item['expiry'] == target_expiry and 
                item['instrument_type'] == opt_type):
                
                token = item['instrument_token']
                filtered_tokens.append(token)
                token_to_strike[token] = float(item['strike'])

        if not filtered_tokens:
            return {"Status": 404, "Error": f"No options found for {stock_code} on {expiry_date}"}

        # Fetch quotes (Kite.quote supports up to 500 tokens)
        self.rate_limiter.wait_if_needed()
        try:
            quotes = self.kite.quote(filtered_tokens)
            self.rate_limiter.record_call()
            
            translated = {"Status": 200, "Success": []}
            for token_str, q_data in quotes.items():
                token = int(token_str)
                strike = token_to_strike.get(token, 0)
                translated["Success"].append({
                    "strike_price": strike,
                    "last_traded_price": q_data.get('last_price', 0),
                    "open_interest": q_data.get('oi', 0),
                    "right": "Call" if opt_type == "CE" else "Put",
                    "symbol": self.token_to_symbol_map.get(token, "")
                })
            return translated
        except Exception as e:
            return {"Status": 500, "Error": str(e)}

    def get_ltp(self, stock_code: str, exchange: str = "NSE", product_type: str = "cash") -> float:
        token = self._get_token(stock_code)
        if not token: return 0.0
        
        self.rate_limiter.wait_if_needed()
        try:
            res = self.kite.ltp([token])
            self.rate_limiter.record_call()
            return float(res.get(str(token), {}).get('last_price', 0))
        except:
            return 0.0

    def place_order(self, **kwargs) -> Dict:
        self.rate_limiter.wait_if_needed()
        # Map generic kwargs to Kite params
        params = {
            "variety": kwargs.get("variety", self.kite.VARIETY_REGULAR),
            "exchange": kwargs.get("exchange", self.kite.EXCHANGE_NSE),
            "tradingsymbol": kwargs.get("tradingsymbol"),
            "transaction_type": kwargs.get("transaction_type"),
            "quantity": kwargs.get("quantity"),
            "product": kwargs.get("product", self.kite.PRODUCT_MIS),
            "order_type": kwargs.get("order_type", self.kite.ORDER_TYPE_MARKET),
            "price": kwargs.get("price"),
            "validity": kwargs.get("validity", self.kite.VALIDITY_DAY),
            "disclosed_quantity": kwargs.get("disclosed_quantity"),
            "trigger_price": kwargs.get("trigger_price"),
            "squareoff": kwargs.get("squareoff"),
            "stoploss": kwargs.get("stoploss"),
            "trailing_stoploss": kwargs.get("trailing_stoploss"),
            "tag": kwargs.get("tag")
        }
        res = self.kite.place_order(**params)
        self.rate_limiter.record_call()
        return res

    def get_expiries(self, stock_code: str) -> List[str]:
        expiries = set()
        for item in self.master_data:
            if item['name'] == stock_code.upper() and item['instrument_type'] in ['CE', 'PE']:
                if item['expiry']:
                    expiries.add(item['expiry'].isoformat())
        return sorted(list(expiries))

    def get_strikes(self, stock_code: str, expiry_date: str) -> List[float]:
        from datetime import datetime
        try:
            target_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        except:
            target_expiry = expiry_date
            
        strikes = set()
        for item in self.master_data:
            if (item['name'] == stock_code.upper() and 
                item['expiry'] == target_expiry and 
                item['instrument_type'] in ['CE', 'PE']):
                strikes.add(float(item['strike']))
        return sorted(list(strikes))

    # WebSocket
    def ws_connect(self):
        """Connect to the Zerodha Kite Ticker WebSocket."""
        self.kws = KiteTicker(self.kite.api_key, self.kite.access_token)
        
        def on_ticks(ws, ticks):
            if self._on_ticks_callback:
                for tick in ticks:
                    token = tick.get('instrument_token')
                    symbol = self.token_to_symbol_map.get(token, str(token))
                    translated = {
                        'stock_code': symbol,
                        'last_traded_price': tick.get('last_price', 0)
                    }
                    self._on_ticks_callback(translated)

        def on_connect(ws, response):
            print("[SafeKite] WebSocket Connected.")
            
        self.kws.on_ticks = on_ticks
        self.kws.on_connect = on_connect
        
        import threading
        threading.Thread(target=self.kws.connect, daemon=True).start()

    def ws_disconnect(self):
        if hasattr(self, 'kws'):
            self.kws.close()

    def subscribe_feeds(self, stock_code: str, **kwargs):
        token = self._get_token(stock_code)
        if token and hasattr(self, 'kws'):
            self.kws.subscribe([token])
            self.kws.set_mode(self.kws.MODE_LTP, [token])
            print(f"[SafeKite] Subscribed to {stock_code} ({token})")

    def unsubscribe_feeds(self, stock_code: str, **kwargs):
        token = self._get_token(stock_code)
        if token and hasattr(self, 'kws'):
            self.kws.unsubscribe([token])

    @property
    def on_ticks(self):
        return self._on_ticks_callback

    @on_ticks.setter
    def on_ticks(self, value):
        self._on_ticks_callback = value

    def _get_token(self, symbol: str) -> Optional[int]:
        # Try direct match
        s_upper = symbol.upper()
        token = self.token_map.get(s_upper)
        if token: return token
        
        # Zerodha indices are usually NSE:NIFTY 50, etc.
        if s_upper == "NIFTY": return self.token_map.get("NIFTY 50")
        if s_upper == "CNXBAN" or s_upper == "BANKNIFTY": return self.token_map.get("NIFTY BANK")
        
        return None
