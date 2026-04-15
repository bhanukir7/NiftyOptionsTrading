import time
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Literal

from nifty_options_trading.alerts import send_alert

class MarketState(Enum):
    RANGE = "RANGE"
    BREAKOUT_SETUP = "BREAKOUT_SETUP"
    TREND = "TREND"
    NO_TRADE = "NO_TRADE"

class PositionType(Enum):
    NONE = "NONE"
    CE = "CALL"
    PE = "PUT"

@dataclass
class MarketData:
    symbol: str
    price: float
    resistance: float
    support: float
    atr: float
    chop: float
    bb_upper: float
    bb_lower: float
    macd: float
    macd_signal: float
    pcr: float
    call_oi: float
    put_oi: float
    iv: float

@dataclass
class StrategyPosition:
    type: PositionType = PositionType.NONE
    entry_price: float = 0.0
    option_price: float = 0.0
    entry_time: float = 0.0
    max_price_seen: float = 0.0

class BreakoutStrategy:
    """Multi-symbol state-based breakout logic derived from newtradinglogic."""
    def __init__(self):
        self.symbol_states = {}

    def get_state(self, symbol: str) -> Dict:
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = {
                "state": MarketState.NO_TRADE,
                "position": StrategyPosition(),
                "break_time": None
            }
        return self.symbol_states[symbol]

    def reset_state(self, symbol: str):
        if symbol in self.symbol_states:
            del self.symbol_states[symbol]

    def process_tick(self, data: MarketData, option_ltp: float) -> Optional[Dict]:
        """
        Main runner returning an action dict if a trade signal or exit is generated.
        Returns:
            {"action": "ENTER", "type": "CE"|"PE", "data": ...}
            {"action": "EXIT", "reason": "...", "pnl": float}
            None
        """
        self.detect_state(data)
        
        s = self.get_state(data.symbol)
        
        # If currently in a position, manage exit
        if s["position"].type != PositionType.NONE:
            exit_reason = self.manage_trade(data, option_ltp)
            if exit_reason:
                pos = s["position"]
                pnl = (option_ltp - pos.option_price) if pos.type == PositionType.CE else (option_ltp - pos.option_price)
                # Ensure we reset cleanly
                type_enum = pos.type
                self.exit_trade(data.symbol, "Internal cleanup")
                return {"action": "EXIT", "reason": exit_reason, "pnl": pnl, "type": type_enum.name}
            return None
        else:
            # Check entry
            return self.check_entry(data)

    def detect_state(self, data: MarketData):
        s = self.get_state(data.symbol)
        # Prevent overriding if deeply in a trend
        if s["state"] == MarketState.TREND:
            return

        if data.chop > 55 and data.atr < 10:
            s["state"] = MarketState.RANGE
        elif data.price > data.resistance or data.price < data.support:
            s["state"] = MarketState.BREAKOUT_SETUP
        else:
            s["state"] = MarketState.NO_TRADE

    def oi_pcr_filter(self, data: MarketData, direction: PositionType):
        # PCR logic
        if direction == PositionType.CE and data.pcr < 0.8:
            return True
        if direction == PositionType.PE and data.pcr > 1.2:
            return True

        # OI dominance
        if direction == PositionType.CE and data.call_oi < data.put_oi:
            return False
        if direction == PositionType.PE and data.put_oi < data.call_oi:
            return False

        return True

    def iv_filter(self, data: MarketData):
        # Avoid very low IV (no movement) or extreme IV spikes
        # Updated defaults for dynamic compatibility
        if data.iv < 8:
            return False
        if data.iv > 40:
            return False
        return True

    def check_entry(self, data: MarketData) -> Optional[Dict]:
        s = self.get_state(data.symbol)

        if s["state"] != MarketState.BREAKOUT_SETUP:
            s["break_time"] = None
            return None

        if s["break_time"] is None:
            s["break_time"] = time.time()
            return None

        if time.time() - s["break_time"] < 300: # Wait 5 minutes for breakout confirmation
            return None

        # Confirm breakout + filters
        if data.price > data.resistance:
            if self.oi_pcr_filter(data, PositionType.CE) and self.iv_filter(data):
                return self.enter_trade(data.symbol, PositionType.CE, data)

        elif data.price < data.support:
            if self.oi_pcr_filter(data, PositionType.PE) and self.iv_filter(data):
                return self.enter_trade(data.symbol, PositionType.PE, data)
                
        return None

    def enter_trade(self, symbol, pos_type, data) -> Dict:
        s = self.get_state(symbol)

        # Temporary setting before global execution takes over
        s["position"] = StrategyPosition(
            type=pos_type,
            entry_price=data.price,
            option_price=data.price, # Overridden later by execution
            entry_time=time.time(),
            max_price_seen=data.price
        )
        s["state"] = MarketState.TREND
        
        return {"action": "ENTER", "type": pos_type.name, "data": data, "reason": f"Breakout strategy triggered {pos_type.name} setup"}

    def manage_trade(self, data: MarketData, option_ltp: float) -> Optional[str]:
        """Evaluates active position and returns an exit reason if rules are hit, otherwise None."""
        s = self.get_state(data.symbol)
        pos = s["position"]

        if pos.type == PositionType.NONE:
            return None

        # Track max
        if option_ltp > pos.max_price_seen:
            pos.max_price_seen = option_ltp

        # Peak exit
        if option_ltp >= pos.option_price * 1.2:
            if pos.type == PositionType.CE and data.price <= data.resistance:
                 return "Spike but no underlying breakout holding"
            if pos.type == PositionType.PE and data.price >= data.support:
                 return "Spike but no underlying breakdown holding"

        # Time-based exit (15 minutes)
        if time.time() - pos.entry_time > 900:
            if abs(data.price - pos.entry_price) < 5:
                return "Time decay / No movement"

        # Breakout failures
        if pos.type == PositionType.CE and data.price < data.resistance:
            return "Breakout failed (Price dipped below resistance)"

        if pos.type == PositionType.PE and data.price > data.support:
            return "Breakdown failed (Price recovered above support)"

        # Trailing stop
        if option_ltp < pos.max_price_seen * 0.9:
            return "Trailing stop triggered"
            
        return None

    def exit_trade(self, symbol, reason):
        s = self.get_state(symbol)
        s["position"] = StrategyPosition()
        s["state"] = MarketState.NO_TRADE
        s["break_time"] = None
