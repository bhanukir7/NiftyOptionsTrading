from nifty_options_trading.safe_breeze import SafeBreeze

class MarketStream:
    """
    Subscribes to ICICI Breeze WebSocket to maintain live
    prices directly in-memory, completely bypassing API polling limits.
    """
    def __init__(self, safe_breeze: SafeBreeze):
        self.breeze = safe_breeze
        self.latest_prices = {}
        
    def on_ticks(self, ticks):
        if 'stock_code' in ticks and 'last_traded_price' in ticks:
            self.latest_prices[ticks['stock_code']] = float(ticks['last_traded_price'])

    def subscribe(self, stock_codes: list):
        self.breeze.on_ticks = self.on_ticks
        print("Connecting to Market WebSocket...")
        self.breeze.ws_connect()
        
        for code in stock_codes:
            print(f"Subscribing to feed for {code}...")
            self.breeze.subscribe_feeds(
                exchange_code="NSE", 
                stock_code=code, 
                product_type="cash", 
                get_exchange_quotes=True, 
                get_market_depth=False
            )
            
    def get_price(self, stock_code: str):
        """Returns the immediate last traded price, or None if no ticks received."""
        return self.latest_prices.get(stock_code, None)
        
    def disconnect(self):
        self.breeze.ws_disconnect()
