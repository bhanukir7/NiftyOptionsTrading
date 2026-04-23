import pytest
from nifty_options_trading.rule_engine import calculate_position_size, Config, StateManager, manage_trade, Position

def test_position_sizing_logic():
    # Part 7: capital=100000, premium=100, sl_pct=0.2
    config = Config()
    config.risk_per_trade_pct = 0.02 # 2%
    config.sl_pct = 0.2
    config.max_lots = 10
    
    capital = 100000
    premium = 100
    lot_size = 50
    
    qty, risk, sl_dist, target_dist = calculate_position_size(capital, premium, 10, lot_size, config)
    
    # max_risk = 100000 * 0.02 = 2000
    # risk_per_lot = 100 * 0.2 * 50 = 1000
    # lots = 2000 // 1000 = 2
    # qty = 2 * 50 = 100
    assert qty == 100
    assert qty <= config.max_lots * lot_size
    assert (qty // lot_size) * (premium * config.sl_pct * lot_size) <= capital * config.risk_per_trade_pct

def test_partial_profit_booking():
    # Part 11: Partial profit at +50%
    config = Config()
    config.partial_profit_pct = 0.5
    state = StateManager()
    
    pos = Position(type="CE", entry_price=100, qty=100, sl_price=80, target_price=200)
    
    # Current price 150 (+50%)
    is_closed, reason, pnl = manage_trade(pos, 150, state, config)
    
    assert is_closed == False
    assert "Partial booked" in reason
    assert pos.qty == 50
    assert pos.sl_price == 100 # SL moved to cost
    assert pnl == (150 - 100) * 50

def test_sl_hit():
    config = Config()
    state = StateManager()
    pos = Position(type="CE", entry_price=100, qty=100, sl_price=80, target_price=200)
    
    # Current price 75 (SL hit)
    is_closed, reason, pnl = manage_trade(pos, 75, state, config)
    assert is_closed == True
    assert "Stop Loss Hit" in reason
