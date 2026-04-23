"""
rule_engine.py

Production-grade Rule Engine module for options trading discipline and execution control.
Provides strict execution rules and risk management layers.
"""

from typing import Literal, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, time

# --- A. Config Class ---
class Config:
    max_trades_per_day: int = 5
    max_consecutive_losses: int = 2
    daily_loss_limit: float = -5000.0
    risk_per_trade_pct: float = 0.02
    sl_pct: float = 0.25
    cooldown_minutes: int = 20
    max_intraday_move_pct: float = 2.5
    # New V2.0 Strategy Controls
    enable_maxpain_strategy: bool = True
    paper_trade: bool = True  # Setup for paper trade as requested
    max_concurrent_trades: int = 3
    partial_profit_pct: float = 0.5
    max_lots: int = 3
    late_entry_cutoff: str = "14:45"
    max_strike_distance: float = 150.0
    vix_threshold: float = 20.0
    daily_profit_target: float = 10000.0

# --- G. Trade Execution Model (Position class) ---
@dataclass
class Position:
    """Represents an active trading position."""
    type: Literal["CE", "PE"]
    entry_price: float
    qty: int
    sl_price: float
    target_price: float
    partial_booked: bool = False

# --- B. State Manager ---
class StateManager:
    """Tracks the trading state for the current day."""
    def __init__(self):
        self.trades_today: int = 0
        self.consecutive_losses: int = 0
        self.daily_pnl: float = 0.0
        self.last_trade_time: Optional[datetime] = None
        self.active_positions: dict[str, Position] = {}
        self.current_bias: Literal["BULLISH", "BEARISH", "NONE"] = "NONE"

    def reset(self):
        """Resets the state for a new trading day."""
        self.trades_today = 0
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.last_trade_time = None
        self.active_positions.clear()
        self.current_bias = "NONE"

# --- C. Bias Engine ---
def determine_bias(price: float, vwap: float, ema21: float, ema50: float) -> Literal["BULLISH", "BEARISH", "NONE"]:
    """Determines the market bias based on price vs VWAP and EMA alignment."""
    if price > vwap and ema21 > ema50:
        return "BULLISH"
    elif price < vwap and ema21 < ema50:
        return "BEARISH"
    return "NONE"

# --- D. Risk Engine ---
def can_trade(state: StateManager, config: Config = Config()) -> Tuple[bool, str]:
    """Evaluates if a new trade can be initiated based on risk checks."""
    if state.trades_today >= config.max_trades_per_day:
        return False, f"Max trades per day ({config.max_trades_per_day}) reached."
    
    if state.daily_pnl <= config.daily_loss_limit:
        return False, f"Daily loss limit ({config.daily_loss_limit}) reached or exceeded."
        
    if state.consecutive_losses >= config.max_consecutive_losses:
        return False, f"Max consecutive losses ({config.max_consecutive_losses}) reached."
        
    if state.last_trade_time:
        minutes_since_last_trade = (datetime.now() - state.last_trade_time).total_seconds() / 60.0
        if minutes_since_last_trade < config.cooldown_minutes:
             return False, f"Cooldown period active. Must wait {config.cooldown_minutes:.1f} mins."
             
    if len(state.active_positions) >= config.max_concurrent_trades:
        return False, f"Max concurrent active positions ({config.max_concurrent_trades}) reached."
        
    if state.daily_pnl >= config.daily_profit_target:
        return False, f"Daily profit target ({config.daily_profit_target}) reached. Trading halted."

    return True, "Trading allowed."

# --- E. Entry Wrapper ---
def validate_entry(signal: Literal["CE", "PE"], bias: Literal["BULLISH", "BEARISH", "NONE"], intraday_move_pct: float, config: Config = Config(), current_time: Optional[datetime] = None) -> Tuple[bool, str]:
    """Validates if the entry signal aligns with bias and market conditions."""
    if current_time is None:
        current_time = datetime.now()
        
    # Time Filter: Avoid late entries
    cutoff_h, cutoff_m = map(int, config.late_entry_cutoff.split(":"))
    if current_time.time() >= time(cutoff_h, cutoff_m):
        return False, f"Late entry risk: Current time {current_time.strftime('%H:%M')} exceeds cutoff {config.late_entry_cutoff}."

    if intraday_move_pct > config.max_intraday_move_pct:
        return False, f"Intraday move ({intraday_move_pct}%) exceeds max allowed ({config.max_intraday_move_pct}%)."
        
    if signal == "CE" and bias != "BULLISH":
        return False, "CE entry blocked: Bias is not BULLISH."
        
    if signal == "PE" and bias != "BEARISH":
        return False, "PE entry blocked: Bias is not BEARISH."
        
    return True, "Entry validated."

# --- F. Position Sizing ---
def calculate_position_size(capital: float, premium: float, atr: float, lot_size: int, config: Config = Config()) -> Tuple[int, float, float, float]:
    """
    Calculates position parameters based on premium-based risk.
    """
    max_risk_per_trade = capital * config.risk_per_trade_pct
    
    # Premium-based risk per lot
    risk_per_lot = premium * config.sl_pct
    
    if risk_per_lot <= 0:
        return 0, 0.0, 0.0, 0.0
        
    num_lots = int(max_risk_per_trade // risk_per_lot)
    num_lots = min(num_lots, config.max_lots)
    
    qty = num_lots * lot_size
    
    # SL/Target distances (will be applied in trading_engine or management)
    sl_dist = premium * config.sl_pct
    target_dist = premium * (config.sl_pct * 2) # Default 1:2 RR if ATR not used directly here
    
    return qty, max_risk_per_trade, sl_dist, target_dist

# --- H. Trade Manager ---
def manage_trade(position: Position, current_price: float, state: StateManager, config: Config = Config(), spot: float = 0.0, atr: float = 0.0) -> Tuple[bool, str, float]:
    """
    Manages an active trade. Handles stop-losses, trailing, and partial booking.
    Expected move logic from Part 12:
    expected_move = ATR / spot
    sl = premium * (1 - expected_move * 0.8)
    target = premium * (1 + expected_move * 2)
    """
    if position.type == "CE":
        pnl = (current_price - position.entry_price) * position.qty
        percent_gain = (current_price - position.entry_price) / position.entry_price
    else: # PE
        pnl = (position.entry_price - current_price) * position.qty
        percent_gain = (position.entry_price - current_price) / position.entry_price

    # Dynamic SL/Target adjustment if ATR/Spot provided (at inception or update)
    if spot > 0 and atr > 0:
        expected_move_ratio = atr / spot
        if position.type == "CE":
            position.sl_price = position.entry_price * (1 - expected_move_ratio * 0.8)
            position.target_price = position.entry_price * (1 + expected_move_ratio * 2.0)
        else:
            position.sl_price = position.entry_price * (1 + expected_move_ratio * 0.8)
            position.target_price = position.entry_price * (1 - expected_move_ratio * 2.0)

    # 1. Exit fully if SL hit
    if position.type == "CE" and current_price <= position.sl_price:
        return True, "Stop Loss Hit", pnl
    elif position.type == "PE" and current_price >= position.sl_price:
         return True, "Stop Loss Hit", pnl

    # 2. Partial Profit Booking at +50% premium
    if percent_gain >= config.partial_profit_pct and not position.partial_booked:
        qty_to_book = position.qty // 2
        partial_pnl = 0.0
        
        if qty_to_book > 0:
            if position.type == "CE":
                partial_pnl = (current_price - position.entry_price) * qty_to_book
            else:
                 partial_pnl = (position.entry_price - current_price) * qty_to_book
                 
            # Move SL to cost
            position.sl_price = position.entry_price
            position.qty -= qty_to_book
            position.partial_booked = True
            return False, f"Partial booked ({qty_to_book} qty) at +50% gain, SL moved to cost.", partial_pnl
            
    # 3. Trail SL after partial booking (Trail by 10%)
    if position.partial_booked:
        if position.type == "CE":
            trail_sl = current_price * (1 - 0.10)
            if trail_sl > position.sl_price:
                position.sl_price = trail_sl
        else:
             trail_sl = current_price * (1 + 0.10)
             if trail_sl < position.sl_price:
                  position.sl_price = trail_sl
                  
    return False, "Position open.", 0.0

# --- I. State Update Functions ---
def update_profit(state: StateManager, pnl: float):
    """Updates state after a profitable trade."""
    if pnl > 0:
        state.daily_pnl += pnl
        state.consecutive_losses = 0

def update_loss(state: StateManager, pnl: float):
    """Updates state after a losing trade."""
    if pnl < 0:
        state.daily_pnl += pnl
        state.consecutive_losses += 1

# --- J. Time Filter ---
def can_take_new_trade_time(current_time: Optional[datetime] = None) -> bool:
    """Blocks new trades after 3:25 PM."""
    if current_time is None:
        current_time = datetime.now()
    
    cutoff_time = time(15, 25) # 3:25 PM
    if current_time.time() >= cutoff_time:
        return False
    return True
