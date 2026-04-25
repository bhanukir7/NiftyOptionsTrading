from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class BaseBroker(ABC):
    """
    Abstract Base Class for all trading brokers.
    Ensures a consistent interface across ICICI Breeze, Angle One, and Zerodha.
    """
    
    @abstractmethod
    def generate_session(self, **kwargs):
        """Perform authentication and establish a session."""
        pass

    @abstractmethod
    def get_historical_data(self, stock_code: str, interval: str, from_date: str, to_date: str, **kwargs) -> Dict:
        """Fetch historical candle data."""
        pass

    @abstractmethod
    def get_option_chain_quotes(self, stock_code: str, expiry_date: str, right: str, **kwargs) -> Dict:
        """Fetch option chain quotes."""
        pass

    @abstractmethod
    def get_ltp(self, stock_code: str, exchange: str = "NSE", product_type: str = "cash") -> float:
        """Fetch the latest traded price for a symbol."""
        pass

    @abstractmethod
    def place_order(self, **kwargs) -> Dict:
        """Place a new order."""
        pass

    @abstractmethod
    def get_expiries(self, stock_code: str) -> List[str]:
        """Fetch available expiry dates for a symbol."""
        pass

    @abstractmethod
    def get_strikes(self, stock_code: str, expiry_date: str) -> List[float]:
        """Fetch available strike prices for a symbol and expiry."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """Fetch current open positions from the broker."""
        pass

    @abstractmethod
    def get_option_greeks(self, symbol: str, expiry: str, strike: str, right: str, exchange: str = "NFO") -> Dict:
        """Fetch live greeks (IV, Delta, etc.) for a specific option."""
        pass

    # WebSocket Methods
    @abstractmethod
    def ws_connect(self):
        """Connect to the market data WebSocket."""
        pass

    @abstractmethod
    def ws_disconnect(self):
        """Disconnect from the market data WebSocket."""
        pass

    @abstractmethod
    def subscribe_feeds(self, stock_code: str, **kwargs):
        """Subscribe to live market feeds for a symbol."""
        pass

    @abstractmethod
    def unsubscribe_feeds(self, stock_code: str, **kwargs):
        """Unsubscribe from live market feeds for a symbol."""
        pass

    @property
    @abstractmethod
    def on_ticks(self):
        """Getter for the tick callback function."""
        pass

    @on_ticks.setter
    @abstractmethod
    def on_ticks(self, value):
        """Setter for the tick callback function."""
        pass
