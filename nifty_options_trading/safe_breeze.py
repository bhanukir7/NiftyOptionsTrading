from typing import Dict, List, Optional, Any
from breeze_connect import BreezeConnect
from nifty_options_trading.api_rate_limiter import RateLimiter
from nifty_options_trading.cache_manager import CacheManager
from nifty_options_trading.broker_interface import BaseBroker

class SafeBreeze(BaseBroker):
    """
    A unified wrapper around the ICICI Breeze API.
    Enforces Rate Limiting controls and leverages caching to heavily
    reduce external API pings and avoid limits.
    """
    def __init__(self, api_key: str):
        self.breeze = BreezeConnect(api_key=api_key)
        self.rate_limiter = RateLimiter(max_per_min=100, max_per_day=5000)
        self.cache_manager = CacheManager()
        self._on_ticks_callback = None
        
    def generate_session(self, api_secret: str = None, session_token: str = None, **kwargs):
        """Pass-through authentication to Breeze."""
        secret = api_secret or kwargs.get('api_secret')
        token = session_token or kwargs.get('session_token')
        self.breeze.generate_session(api_secret=secret, session_token=token)

    # Websocket Pass-throughs
    @property
    def on_ticks(self):
        return self.breeze.on_ticks
        
    @on_ticks.setter
    def on_ticks(self, value):
        self.breeze.on_ticks = value

    def ws_connect(self):
        self.breeze.ws_connect()

    def ws_disconnect(self):
        self.breeze.ws_disconnect()

    def subscribe_feeds(self, stock_code: str, exchange_code: str = "NSE", product_type: str = "cash", **kwargs):
        self.breeze.subscribe_feeds(stock_code=stock_code, exchange_code=exchange_code, product_type=product_type, **kwargs)

    def unsubscribe_feeds(self, stock_code: str, exchange_code: str = "NSE", product_type: str = "cash", **kwargs):
        self.breeze.unsubscribe_feeds(stock_code=stock_code, exchange_code=exchange_code, product_type=product_type, **kwargs)

    # Wrapped API Methods with Caching and Limits
    def get_historical_data(self, stock_code: str, interval: str, from_date: str, to_date: str, **kwargs):
        exchange = kwargs.get("exchange_code", "NSE")
        # Construct unique key
        cache_key = f"hist_{stock_code}_{exchange}_{interval}_{to_date}"
        
        # TTL Rules from specs: 1 hour for daily data (to catch intraday updates), 1 min for shorter
        ttl = 3600 if interval == "1day" else 60
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_historical_data(
            stock_code=stock_code,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
            **kwargs
        )
        self.rate_limiter.record_call()
        
        self.cache_manager.set(cache_key, res, ttl)
        return res

    def get_option_chain_quotes(self, stock_code: str, expiry_date: str, right: str, **kwargs):
        cache_key = f"opt_{stock_code}_{expiry_date}_{right}"
        ttl = 15 # 15 seconds refresh for high-frequency strategy analysis
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_option_chain_quotes(
            stock_code=stock_code,
            expiry_date=expiry_date,
            right=right,
            **kwargs
        )
        self.rate_limiter.record_call()
        
        self.cache_manager.set(cache_key, res, ttl)
        return res

    def get_ltp(self, stock_code: str, exchange: str = "NSE", product_type: str = "cash") -> float:
        """Fetch the latest traded price for a symbol."""
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_quotes(stock_code=stock_code, exchange_code=exchange, product_type=product_type)
        self.rate_limiter.record_call()
        if res.get("Status") == 200 and res.get("Success"):
            return float(res["Success"][0].get("last_traded_price", 0))
        return 0.0

    def place_order(self, **kwargs) -> Dict:
        """Place a new order through Breeze."""
        self.rate_limiter.wait_if_needed()
        res = self.breeze.place_order(**kwargs)
        self.rate_limiter.record_call()
        return res

    def get_expiries(self, stock_code: str) -> List[str]:
        from nifty_options_trading.options_engine import get_expiries
        dates = get_expiries(stock_code)
        return [d.isoformat() for d in dates]

    def get_strikes(self, stock_code: str, expiry_date: str) -> List[float]:
        from nifty_options_trading.options_engine import get_strikes
        import datetime
        try:
            dt = datetime.date.fromisoformat(expiry_date)
        except:
            dt = expiry_date
        return get_strikes(stock_code, dt)

    def log_api_usage(self):
        """Prints current API usage metrics to the console."""
        print(f"[API STATS] Used this minute: {len(self.rate_limiter.call_timestamps)}/100 | Used today: {self.rate_limiter.daily_calls}/5000")
