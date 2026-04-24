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
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for item in data:
                    # Map symbol to token for easy lookup
                    # Example: item['symbol'] = 'NIFTY25APR2422500CE', item['token'] = '12345'
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
        # Breeze: '5minute', '1day'
        # SmartAPI: 'FIVE_MINUTE', 'ONE_DAY'
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
            return {"Status": 404, "Error": "Symbol not found in master"}
            
        self.rate_limiter.wait_if_needed()
        # SmartAPI params: exchange, symboltoken, interval, fromdate, todate
        res = self.smart.getCandleData({
            "exchange": kwargs.get("exchange", "NSE"),
            "symboltoken": token,
            "interval": angle_interval,
            "fromdate": from_date,
            "todate": to_date
        })
        self.rate_limiter.record_call()
        
        # Translate SmartAPI format to Breeze-like format for the engine
        # SmartAPI: {"status": True, "data": [[time, o, h, l, c, v], ...]}
        # Breeze: {"Status": 200, "Success": [{"datetime":..., "open":...}, ...]}
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
        # SmartAPI doesn't have a direct 'get_option_chain' like Breeze.
        # We usually fetch all tokens for the underlying and filter.
        # This is more complex and will be implemented in Step 5.
        return {"Status": 501, "Error": "Option Chain for SmartAPI coming soon"}

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
            # SmartAPI Tick → Unified format
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
            action = 1 # 1 for Subscribe
            mode = 1   # 1 for LTP
            exchange_type = 1 # 1 for NSE
            tokens = [token]
            self.sws.subscribe(correlation_id, mode, [{"exchangeType": exchange_type, "tokens": tokens}])
            print(f"[SmartAPI] Subscribed to {stock_code} ({token})")

    def unsubscribe_feeds(self, stock_code: str, **kwargs):
        token = self._get_token(stock_code)
        if token:
            correlation_id = f"unsub_{stock_code}"
            action = 0 # 0 for Unsubscribe
            mode = 1
            exchange_type = 1
            tokens = [token]
            self.sws.unsubscribe(correlation_id, mode, [{"exchangeType": exchange_type, "tokens": tokens}])

    @property
    def on_ticks(self):
        return self._on_ticks_callback

    @on_ticks.setter
    def on_ticks(self, value):
        self._on_ticks_callback = value

    def _get_token(self, symbol: str) -> Optional[str]:
        # Logic to lookup token from master list
        return self.token_map.get(symbol)
