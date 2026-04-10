from breeze_connect import BreezeConnect
from nifty_options_trading.api_rate_limiter import RateLimiter
from nifty_options_trading.cache_manager import CacheManager

class SafeBreeze:
    """
    A unified wrapper around the ICICI Breeze API.
    Enforces Rate Limiting controls and leverages caching to heavily
    reduce external API pings and avoid limits.
    """
    def __init__(self, api_key: str):
        self.breeze = BreezeConnect(api_key=api_key)
        self.rate_limiter = RateLimiter(max_per_min=100, max_per_day=5000)
        self.cache_manager = CacheManager()
        
    def generate_session(self, api_secret: str, session_token: str):
        """Pass-through authentication to Breeze."""
        self.breeze.generate_session(api_secret=api_secret, session_token=session_token)

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

    def subscribe_feeds(self, **kwargs):
        self.breeze.subscribe_feeds(**kwargs)

    def unsubscribe_feeds(self, **kwargs):
        self.breeze.unsubscribe_feeds(**kwargs)

    # Wrapped API Methods with Caching and Limits
    def get_historical_data(self, **kwargs):
        # Construct unique key
        interval = kwargs.get('interval', '5minute')
        code = kwargs.get('stock_code', 'NIFTY')
        to_date = kwargs.get('to_date', '')
        
        cache_key = f"hist_{code}_{interval}_{to_date}"
        
        # TTL Rules from specs
        ttl = 86400 if interval == "1day" else 60
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_historical_data(**kwargs)
        self.rate_limiter.record_call()
        
        self.cache_manager.set(cache_key, res, ttl)
        return res

    def get_option_chain_quotes(self, **kwargs):
        code = kwargs.get('stock_code', 'NIFTY')
        exp = kwargs.get('expiry_date', '')
        right = kwargs.get('right', '')
        
        cache_key = f"opt_{code}_{exp}_{right}"
        ttl = 180 # 3 minutes strictly for Option Chain 
        
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
            
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_option_chain_quotes(**kwargs)
        self.rate_limiter.record_call()
        
        self.cache_manager.set(cache_key, res, ttl)
        return res

    def log_api_usage(self):
        """Prints current API usage metrics to the console."""
        print(f"[API STATS] Used this minute: {len(self.rate_limiter.call_timestamps)}/100 | Used today: {self.rate_limiter.daily_calls}/5000")
