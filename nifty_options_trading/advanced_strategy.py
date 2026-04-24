import time
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional

# ===================== ENUMS =====================
class MarketState(Enum):
    RANGE = "RANGE"
    BREAKOUT_SETUP = "BREAKOUT_SETUP"
    TREND = "TREND"
    NO_TRADE = "NO_TRADE"

class PositionType(Enum):
    NONE = "NONE"
    CE = "CALL"
    PE = "PUT"

# ===================== DATA STRUCTURES =====================
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
    call_oi_change: float = 0.0
    put_oi_change: float = 0.0
    iv: float = 0.0
    volume: float = 0.0

@dataclass
class Position:
    type: PositionType = PositionType.NONE
    entry_price: float = 0.0
    option_price: float = 0.0
    entry_time: float = 0.0
    max_price_seen: float = 0.0
    breakout_level: float = 0.0
    last_momentum: float = 0.0
    scale_out_done: bool = False

@dataclass
class Signal:
    symbol: str
    signal_type: str
    price: float
    timestamp: float
    metadata: dict

# ===================== STRATEGY =====================
class AdvancedBreakoutStrategy:
    def __init__(self):
        self.symbol_states = {}
        self.signal_log = []
        self.last_signal = {} # symbol -> {"type": str, "timestamp": float}

    def get_state(self, symbol):
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = {
                "state": MarketState.NO_TRADE,
                "position": Position(),
                "break_time": None,
                "candle_buffer": [],
                "volume_buffer": [],
                "last_pcr": 1.0,
                "last_iv": 0.0
            }
            self.last_signal[symbol] = {"type": None, "timestamp": 0}
        return self.symbol_states[symbol]

    def _emit_signal(self, symbol, signal_type, price, metadata=None):
        from nifty_options_trading.alerts import send_alert
        
        now = time.time()
        last = self.last_signal.get(symbol, {"type": None, "timestamp": 0})
        
        # Duplicate protection (60s check for same type)
        if last["type"] == signal_type and (now - last["timestamp"]) < 60:
            return

        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            timestamp=now,
            metadata=metadata or {}
        )
        
        self.signal_log.append(signal)
        if len(self.signal_log) > 100:
            self.signal_log.pop(0)
            
        self.last_signal[symbol] = {"type": signal_type, "timestamp": now}

        # Telegram Alerts for High-Priority signals
        if signal_type in ["BREAKOUT_CONFIRMED", "ENTRY_CE", "ENTRY_PE", "SCALE_OUT", "EXIT"]:
            side_str = metadata.get("side", "") if metadata else ""
            reason = metadata.get("reason", "") if metadata else ""
            msg = (f"🚨 **SIGNAL HUB ALERT [{symbol}]**\n"
                   f"Type: {signal_type} {side_str}\n"
                   f"Price: {price:.2f}\n"
                   f"Context: {reason}")
            send_alert(msg)

        return signal

    def get_symbol_snapshot(self, symbol):
        s = self.get_state(symbol)
        pos = s["position"]
        
        pnl = 0.0
        if pos.type != PositionType.NONE:
            pnl = pos.max_price_seen - pos.option_price if pos.type == PositionType.CE else pos.option_price - pos.max_price_seen

        return {
            "symbol": symbol,
            "state": s["state"].value,
            "position": pos.type.value,
            "entry_price": round(pos.entry_price, 2),
            "pnl_estimate": round(pnl, 2), 
            "breakout_level": round(pos.breakout_level, 2),
            "momentum": round(pos.last_momentum, 4),
            "oi_bias": "BULLISH" if s.get("last_pcr", 1.0) > 1.0 else "BEARISH",
            "iv": round(s.get("last_iv", 0.0), 2),
            "last_signal": self.last_signal[symbol]["type"],
            "timestamp": time.time()
        }

    def detect_state(self, data: MarketData):
        s = self.get_state(data.symbol)
        if s["state"] == MarketState.TREND:
            return # Let manage_trade handle it

        reason = ""
        if data.chop > 55:
            s["state"] = MarketState.RANGE
            reason = f"Choppy Market (Chop: {data.chop:.1f})"
            self._emit_signal(data.symbol, "RANGE_DETECTED", data.price, {"reason": reason})
        elif data.price > data.resistance:
            s["state"] = MarketState.BREAKOUT_SETUP
            reason = f"Bullish Setup - Price ({data.price:.1f}) > Res ({data.resistance:.1f})"
            self._emit_signal(data.symbol, "SETUP_DETECTED", data.price, {"reason": reason, "side": "UP"})
        elif data.price < data.support:
            s["state"] = MarketState.BREAKOUT_SETUP
            reason = f"Bearish Setup - Price ({data.price:.1f}) < Supp ({data.support:.1f})"
            self._emit_signal(data.symbol, "SETUP_DETECTED", data.price, {"reason": reason, "side": "DOWN"})
        else:
            s["state"] = MarketState.NO_TRADE
            reason = f"Idle - Within Range ({data.support:.1f} - {data.resistance:.1f})"
            self._emit_signal(data.symbol, "NO_TRADE", data.price, {"reason": reason})
        
        s["last_pcr"] = data.pcr
        s["last_iv"] = data.iv

    def oi_pcr_filter(self, data: MarketData, direction: PositionType):
        if direction == PositionType.CE:
            if data.pcr < 0.8 and data.call_oi_change > 0:
                return True
        if direction == PositionType.PE:
            if data.pcr > 1.2 and data.put_oi_change > 0:
                return True
        return False

    def iv_filter(self, data: MarketData):
        return 8 < data.iv < 40

    def volume_spike(self, symbol, current_volume):
        s = self.get_state(symbol)
        vol_buf = s["volume_buffer"]
        vol_buf.append(current_volume)
        if len(vol_buf) > 20: vol_buf.pop(0)
        avg_vol = sum(vol_buf) / len(vol_buf) if vol_buf else 0
        return current_volume > avg_vol * 1.5 if avg_vol > 0 else False

    def candle_confirm(self, symbol, price, level, direction):
        s = self.get_state(symbol)
        candles = s["candle_buffer"]
        candles.append(price)
        if len(candles) > 3: candles.pop(0)
        if len(candles) < 2: return False
        if direction == PositionType.CE:
            return all(p > level for p in candles[-2:])
        if direction == PositionType.PE:
            return all(p < level for p in candles[-2:])
        return False

    def check_entry(self, data: MarketData):
        s = self.get_state(data.symbol)
        if s["state"] != MarketState.BREAKOUT_SETUP: return None

        if s["break_time"] is None:
            s["break_time"] = time.time()
            return None

        if time.time() - s["break_time"] < 60: return None

        if data.price > data.resistance:
            if (self.candle_confirm(data.symbol, data.price, data.resistance, PositionType.CE)
                and self.volume_spike(data.symbol, data.volume)
                and self.oi_pcr_filter(data, PositionType.CE)
                and self.iv_filter(data)):
                self._emit_signal(data.symbol, "BREAKOUT_CONFIRMED", data.price, {"side": "CE"})
                return self.enter_trade(data.symbol, PositionType.CE, data)
        elif data.price < data.support:
            if (self.candle_confirm(data.symbol, data.price, data.support, PositionType.PE)
                and self.volume_spike(data.symbol, data.volume)
                and self.oi_pcr_filter(data, PositionType.PE)
                and self.iv_filter(data)):
                self._emit_signal(data.symbol, "BREAKOUT_CONFIRMED", data.price, {"side": "PE"})
                return self.enter_trade(data.symbol, PositionType.PE, data)
        return None

    def enter_trade(self, symbol, pos_type, data):
        s = self.get_state(symbol)
        breakout_level = data.resistance if pos_type == PositionType.CE else data.support
        
        s["position"] = Position(
            type=pos_type,
            entry_price=data.price,
            option_price=data.price,
            entry_time=time.time(),
            max_price_seen=data.price,
            breakout_level=breakout_level,
            last_momentum=abs(data.macd - data.macd_signal)
        )
        s["state"] = MarketState.TREND
        
        sig_type = "ENTRY_CE" if pos_type == PositionType.CE else "ENTRY_PE"
        self._emit_signal(symbol, sig_type, data.price)
        self._emit_signal(symbol, "TRAIL_ACTIVE", data.price)
        
        return {"action": "ENTER", "type": pos_type.value, "price": data.price}

    def manage_trade(self, data: MarketData, option_ltp: float):
        s = self.get_state(data.symbol)
        pos = s["position"]
        if pos.type == PositionType.NONE: return None

        current_momentum = abs(data.macd - data.macd_signal)
        if option_ltp > pos.max_price_seen: pos.max_price_seen = option_ltp

        exit_reason = None
        if option_ltp >= pos.option_price * 1.2:
            if pos.type == PositionType.CE and data.price <= pos.breakout_level:
                exit_reason = "Spike no breakout"
        elif time.time() - pos.entry_time > 900:
            exit_reason = "Time exit"
        elif current_momentum < pos.last_momentum * 0.6 and not pos.scale_out_done:
            pos.scale_out_done = True
            self._emit_signal(data.symbol, "SCALE_OUT", data.price, {"ltp": option_ltp})
        elif pos.type == PositionType.CE and data.price < pos.breakout_level:
            exit_reason = "Breakout failed"
        elif pos.type == PositionType.PE and data.price > pos.breakout_level:
            exit_reason = "Breakdown failed"
        elif option_ltp < pos.max_price_seen * 0.9:
            exit_reason = "Trailing stop"

        pos.last_momentum = current_momentum
        
        if exit_reason:
            return self.exit_trade(data.symbol, exit_reason)
        return None

    def exit_trade(self, symbol, reason):
        s = self.get_state(symbol)
        pos = s["position"]
        
        sig = self._emit_signal(symbol, "EXIT", pos.entry_price, {"reason": reason})
        
        s["position"] = Position()
        s["state"] = MarketState.NO_TRADE
        s["break_time"] = None
        
        return {"action": "EXIT", "reason": reason}
