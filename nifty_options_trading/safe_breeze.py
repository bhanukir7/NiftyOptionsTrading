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

    def get_positions(self) -> List[Dict]:
        """Fetch positions from Breeze, aggregate them, and filter closed ones."""
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_portfolio_positions()
        self.rate_limiter.record_call()
        
        # Aggregate positions by: (stock_code, expiry_date, strike_price, right)
        aggregated = {}

        success_data = res.get("Success")
        if res.get("Status") == 200 and isinstance(success_data, list):
            for pos in success_data:
                stock = pos.get("stock_code")
                expiry = pos.get("expiry_date") or ""
                strike = pos.get("strike_price") or ""
                right = pos.get("right") or ""
                exchange = pos.get("exchange_code") or "NSE"
                
                # Identify segment
                product = pos.get("product_type", "").lower()
                segment = "equity"
                if expiry or strike or product in ["options", "futures"]:
                    segment = "fno"

                # Unique key for aggregation
                key = (stock, expiry, strike, right)
                
                # Determine net quantity
                # Breeze can return 'quantity' or 'net_quantity' or 'position_quantity'
                q = 0
                raw_q = pos.get("net_quantity") or pos.get("quantity") or pos.get("position_quantity")
                try:
                    q = int(raw_q) if raw_q is not None else 0
                except:
                    q = 0
                
                # Handle signed vs unsigned quantity + action
                # If quantity is unsigned, use 'action' to determine sign
                if q > 0 and pos.get("action", "").lower() == "sell":
                    q = -q

                avg_price = float(pos.get("average_price") or 0)
                ltp = float(pos.get("ltp") or 0)
                # pnl can be 'unrealized_profit_loss' or 'pnl' or 'ur_pnl'
                pnl = pos.get("unrealized_profit_loss") or pos.get("pnl") or pos.get("ur_pnl")
                
                if key not in aggregated:
                    aggregated[key] = {
                        "symbol": stock,
                        "expiry": expiry,
                        "strike": strike,
                        "right": right,
                        "quantity": 0,
                        "total_cost": 0,
                        "ltp": ltp,
                        "pnl": 0,
                        "exchange": exchange,
                        "segment": segment
                    }
                
                entry = aggregated[key]
                entry["quantity"] += q
                if q > 0: # Long side contribution to average price
                    entry["total_cost"] += (avg_price * q)
                elif q < 0 and entry["total_cost"] == 0: # Short entry
                    entry["total_cost"] = (avg_price * abs(q))
                
                entry["ltp"] = ltp
                if pnl is not None:
                    entry["pnl"] += float(pnl)

            # Finalize and filter
            normalized = []
            for entry in aggregated.values():
                if entry["quantity"] != 0:
                    # Final average price calculation
                    if abs(entry["quantity"]) > 0:
                        entry["average_price"] = entry["total_cost"] / abs(entry["quantity"])
                    else:
                        entry["average_price"] = 0
                    
                    # If PnL wasn't provided or was 0, calculate it
                    if entry["pnl"] == 0:
                        entry["pnl"] = (entry["ltp"] - entry["average_price"]) * entry["quantity"]
                    
                    # Remove temporary keys
                    if "total_cost" in entry: del entry["total_cost"]
                    normalized.append(entry)
            
            print(f"[POSITIONS] Found {len(normalized)} active positions.")
            return normalized
        
        if success_data and not isinstance(success_data, list):
            print(f"[POSITIONS] Non-list success data from Breeze: {success_data}")
        return []

    def get_option_greeks(self, symbol: str, expiry: str, strike: str, right: str, exchange: str = "NFO") -> Dict:
        """Fetch live IV from Breeze."""
        self.rate_limiter.wait_if_needed()
        res = self.breeze.get_option_chain_quotes(
            stock_code=symbol,
            exchange_code=exchange,
            expiry_date=expiry,
            product_type="options",
            right=right.lower(),
            strike_price=strike
        )
        self.rate_limiter.record_call()
        
        iv = 0.15 # Default
        print(f"[GREEKS] Fetching for {symbol} {expiry} {strike} {right}")
        if res.get("Status") == 200 and res.get("Success"):
            target_strike = float(strike)
            for row in res["Success"]:
                try:
                    row_strike = float(row.get("strike_price", 0))
                    if abs(row_strike - target_strike) < 0.1:
                        iv_val = row.get("implied_volatility")
                        print(f"  MATCH FOUND: Strike={row_strike}, IV={iv_val}")
                        if iv_val and float(iv_val) > 0:
                            iv = float(iv_val) / 100 
                            break
                except: continue
        else:
            print(f"  FETCH FAILED or NO DATA: {res.get('Error')}")
        return {"iv": iv}

    def log_api_usage(self):
        """Prints current API usage metrics to the console."""
        print(f"[API STATS] Used this minute: {len(self.rate_limiter.call_timestamps)}/100 | Used today: {self.rate_limiter.daily_calls}/5000")
