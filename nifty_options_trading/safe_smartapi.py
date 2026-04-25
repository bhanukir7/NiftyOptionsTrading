import os
import time
from typing import Dict, List, Optional, Any
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pyotp
from nifty_options_trading.api_rate_limiter import RateLimiter
from nifty_options_trading.cache_manager import CacheManager
from nifty_options_trading.broker_interface import BaseBroker

class SafeSmartAPI(BaseBroker):
    """
    A unified wrapper around the Angel One SmartAPI.
    Enforces Rate Limiting controls and leverages caching.
    """
    def __init__(self, api_key: str):
        self.smart = SmartConnect(api_key=api_key)
        self.rate_limiter = RateLimiter(max_per_min=180, max_per_day=10000) # Angle has higher limits
        self.cache_manager = CacheManager()
        self._on_ticks_callback = None
        self.token_map = {} # Mapping from symbol to token
        self.token_to_symbol_map = {} # Mapping from token to symbol
        self._download_master()
        
    def _download_master(self):
        """Downloads and parses the Angle One instrument master."""
        import requests
        import json
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        try:
            print("[SmartAPI] Downloading Instrument Master...")
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                self.master_data = data # Store full list for complex filtering
                for item in data:
                    symbol = item['symbol']
                    token = item['token']
                    self.token_map[symbol] = token
                    self.token_to_symbol_map[token] = symbol
                print(f"[SmartAPI] Loaded {len(self.token_map)} instruments.")
        except Exception as e:
            print(f"[SmartAPI] Error downloading instrument master: {e}")
        
    def generate_session(self, client_code: str, password: str, totp_secret: str, **kwargs):
        """Silent authentication using TOTP."""
        totp = pyotp.TOTP(totp_secret).now()
        res = self.smart.generateSession(client_code, password, totp)
        if res.get('status'):
            print(f"[SmartAPI] Login successful for {client_code}")
            return res
        else:
            raise Exception(f"SmartAPI Login Failed: {res.get('message')}")

    def get_historical_data(self, stock_code: str, interval: str, from_date: str, to_date: str, **kwargs):
        # Angle One interval mapping
        angle_interval = {
            "5minute": "FIVE_MINUTE",
            "1day": "ONE_DAY",
            "1minute": "ONE_MINUTE"
        }.get(interval, interval)
        
        cache_key = f"hist_angle_{stock_code}_{interval}_{to_date}"
        ttl = 3600 if interval == "1day" else 60
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        token = self._get_token(stock_code)
        if not token:
            return {"Status": 404, "Error": f"Symbol {stock_code} not found in master"}
            
        self.rate_limiter.wait_if_needed()
        res = self.smart.getCandleData({
            "exchange": kwargs.get("exchange", "NSE"),
            "symboltoken": token,
            "interval": angle_interval,
            "fromdate": from_date,
            "todate": to_date
        })
        self.rate_limiter.record_call()
        
        translated = {"Status": 200, "Success": []}
        if res.get('status') and res.get('data'):
            for candle in res['data']:
                translated["Success"].append({
                    "datetime": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                })
        
        self.cache_manager.set(cache_key, translated, ttl)
        return translated

    def get_option_chain_quotes(self, stock_code: str, expiry_date: str, right: str, **kwargs):
        """
        Simulates an option chain by filtering the scrip master and fetching market data.
        Breeze expiry_date: YYYY-MM-DD
        Angle One expiry format: DDMMMYYYY (e.g., 25APR2024)
        """
        # Convert YYYY-MM-DD to DDMMMYYYY
        try:
            dt_obj = datetime.strptime(expiry_date.split('T')[0], "%Y-%m-%d")
            angle_expiry = dt_obj.strftime("%d%b%Y").upper()
        except Exception:
            angle_expiry = expiry_date # Fallback

        # Filter master for options
        # stock_code might be 'NIFTY'
        # item['name'] is 'NIFTY'
        # item['instrumenttype'] is 'OPTIDX' or 'OPTSTK'
        # item['expiry'] matches angle_expiry
        
        # We need to map 'Call'/'Put' to 'CE'/'PE' suffix in symbol or look at optiontype if available
        opt_type = "CE" if right.lower() in ["call", "ce"] else "PE"
        
        filtered_tokens = []
        token_to_strike = {}
        
        if not hasattr(self, 'master_data'):
            return {"Status": 500, "Error": "Instrument master not loaded"}

        for item in self.master_data:
            if (item['name'] == stock_code.upper() and 
                item['expiry'] == angle_expiry and 
                item['symbol'].endswith(opt_type)):
                
                filtered_tokens.append(item['token'])
                token_to_strike[item['token']] = float(item['strike']) / 100 if '.' not in item['strike'] else float(item['strike'])
                # Angle One strike can be '2250000' for 22500.00 sometimes, but usually it has decimal.
                # Standardizing:
                strike_val = item['strike']
                try:
                    token_to_strike[item['token']] = float(strike_val)
                except:
                    pass

        if not filtered_tokens:
            return {"Status": 404, "Error": f"No options found for {stock_code} on {angle_expiry}"}

        # Fetch market data for these tokens (limited to 50 per call in some APIs, but getMarketData supports more?)
        # Let's chunk if necessary.
        chunk_size = 50
        all_results = []
        
        for i in range(0, len(filtered_tokens), chunk_size):
            chunk = filtered_tokens[i : i + chunk_size]
            payload = {
                "mode": "LTP", # Or FULL for OI
                "exchangeTokens": {
                    kwargs.get("exchange_segment", "NFO"): chunk
                }
            }
            self.rate_limiter.wait_if_needed()
            res = self.smart.getMarketData(payload['mode'], payload['exchangeTokens'])
            self.rate_limiter.record_call()
            
            if res.get('status') and res.get('data'):
                # res['data']['fetched'] is a list of objects
                all_results.extend(res['data']['fetched'])

        # Translate to Breeze-like format
        # Breeze needs: strike_price, last_traded_price, open_interest, right
        translated = {"Status": 200, "Success": []}
        for item in all_results:
            token = item.get('symbolToken')
            strike = token_to_strike.get(token, 0)
            translated["Success"].append({
                "strike_price": strike,
                "last_traded_price": item.get('ltp', 0),
                "open_interest": item.get('oi', 0),
                "right": "Call" if opt_type == "CE" else "Put",
                "symbol": self.token_to_symbol_map.get(token, "")
            })
            
        return translated

    def get_ltp(self, stock_code: str, exchange: str = "NSE", product_type: str = "cash") -> float:
        token = self._get_token(stock_code)
        if not token: return 0.0
        
        self.rate_limiter.wait_if_needed()
        res = self.smart.getLtpData(exchange, stock_code, token)
        self.rate_limiter.record_call()
        
        if res.get('status'):
            return float(res['data'].get('ltp', 0))
        return 0.0

    def place_order(self, **kwargs) -> Dict:
        self.rate_limiter.wait_if_needed()
        res = self.smart.placeOrder(kwargs)
        self.rate_limiter.record_call()
        return res

    # WebSocket
    def ws_connect(self):
        """Connect to the Angle One market data WebSocket."""
        jwt = self.smart.access_token
        client_code = os.getenv("ANGLE_CLIENT_CODE")
        
        self.sws = SmartWebSocketV2(jwt, self.smart.api_key, client_code, os.getenv("ANGLE_FEED_TOKEN", ""))
        
        def on_data(wsapp, msg):
            if self._on_ticks_callback:
                token = msg.get('token')
                symbol = self.token_to_symbol_map.get(token, token)
                translated = {
                    'stock_code': symbol,
                    'last_traded_price': msg.get('last_traded_price', 0)
                }
                self._on_ticks_callback(translated)

        def on_open(wsapp):
            print("[SmartAPI] WebSocket Connected.")
            
        def on_error(wsapp, error):
            print(f"[SmartAPI] WebSocket Error: {error}")

        def on_close(wsapp):
            print("[SmartAPI] WebSocket Closed.")

        self.sws.on_data = on_data
        self.sws.on_open = on_open
        self.sws.on_error = on_error
        self.sws.on_close = on_close
        
        import threading
        threading.Thread(target=self.sws.connect, daemon=True).start()

    def ws_disconnect(self):
        if hasattr(self, 'sws'):
            self.sws.close()

    def subscribe_feeds(self, stock_code: str, **kwargs):
        token = self._get_token(stock_code)
        if token:
            correlation_id = f"sub_{stock_code}"
            mode = 1   # 1 for LTP
            # Map exchange_code to exchangeType
            # NSE=1, NFO=2, BSE=3, BFO=4
            exch = kwargs.get("exchange_code", "NSE")
            exch_type = 1
            if exch == "NFO": exch_type = 2
            elif exch == "BSE": exch_type = 3
            elif exch == "BFO": exch_type = 4
            
            self.sws.subscribe(correlation_id, mode, [{"exchangeType": exch_type, "tokens": [token]}])
            print(f"[SmartAPI] Subscribed to {stock_code} ({token})")

    def unsubscribe_feeds(self, stock_code: str, **kwargs):
        token = self._get_token(stock_code)
        if token:
            correlation_id = f"unsub_{stock_code}"
            mode = 1
            exch = kwargs.get("exchange_code", "NSE")
            exch_type = 1
            if exch == "NFO": exch_type = 2
            self.sws.unsubscribe(correlation_id, mode, [{"exchangeType": exch_type, "tokens": [token]}])

    def get_expiries(self, stock_code: str) -> List[str]:
        if not hasattr(self, 'master_data'): return []
        expiries = set()
        for item in self.master_data:
            if item['name'] == stock_code.upper() and item['instrumenttype'] in ['OPTIDX', 'OPTSTK']:
                # Angle One expiry: DDMMMYYYY
                try:
                    dt = datetime.strptime(item['expiry'], "%d%b%Y")
                    expiries.add(dt.strftime("%Y-%m-%d"))
                except:
                    expiries.add(item['expiry'])
        return sorted(list(expiries))

    def get_strikes(self, stock_code: str, expiry_date: str) -> List[float]:
        if not hasattr(self, 'master_data'): return []
        # expiry_date is YYYY-MM-DD
        try:
            dt_obj = datetime.strptime(expiry_date, "%Y-%m-%d")
            angle_expiry = dt_obj.strftime("%d%b%Y").upper()
        except:
            angle_expiry = expiry_date

        strikes = set()
        for item in self.master_data:
            if (item['name'] == stock_code.upper() and 
                item['expiry'] == angle_expiry and 
                item['instrumenttype'] in ['OPTIDX', 'OPTSTK']):
                try:
                    strikes.add(float(item['strike']))
                except:
                    pass
        return sorted(list(strikes))

    @property
    def on_ticks(self):
        return self._on_ticks_callback

    @on_ticks.setter
    def on_ticks(self, value):
        self._on_ticks_callback = value

    def _get_token(self, symbol: str) -> Optional[str]:
        # Try direct match
        s_upper = symbol.upper()
        token = self.token_map.get(s_upper)
        if token: return token
        
        # Try fuzzy match if it's an index
        if s_upper == "NIFTY": 
            return self.token_map.get("Nifty 50") or self.token_map.get("NIFTY50")
        if s_upper == "CNXBAN" or s_upper == "BANKNIFTY": 
            return self.token_map.get("Nifty Bank") or self.token_map.get("BANKNIFTY")
        if s_upper == "FINNIFTY":
            return self.token_map.get("Nifty Fin Services")
        
        return None

