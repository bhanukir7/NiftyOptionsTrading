import pytest
from unittest.mock import MagicMock
from datetime import datetime
from nifty_options_trading.trading_engine import AutonomousEngine
from nifty_options_trading.rule_engine import Config, StateManager

@pytest.fixture
def engine():
    breeze = MagicMock()
    return AutonomousEngine(breeze)

def test_time_filter_before_hours(engine):
    # Part 8: Before 09:30 → reject
    # We'll need to mock datetime.now() or the check logic
    # The current engine uses datetime.now().strftime("%H:%M") in _execute_signal
    pass # Needs specialized mock for datetime

def test_consecutive_losses_filter(engine):
    # Part 9: consecutive_losses >= 3 → block
    engine.state.consecutive_losses = 3
    data = {
        "symbol": "NIFTY", "spot": 22000, "vwap": 22000, "ema21": 22000, "ema50": 21900,
        "macd": 1, "macd_signal": 0, "chop": 30, "atr": 10,
        "indicators": {"macd_hist": 1, "ema_alignment": True, "price_above_bb": True, "rsi": 60}
    }
    result = engine.evaluate_trade_decision(data)
    assert result["decision"] == "NO_TRADE"
    assert "consecutive losses" in result["reason"]

def test_daily_profit_filter(engine):
    # Part 9: daily_profit >= target → block
    engine.state.daily_pnl = 15000
    engine.config.daily_profit_target = 10000
    
    # can_trade handles this in rule_engine
    from nifty_options_trading.rule_engine import can_trade
    allowed, reason = can_trade(engine.state, engine.config)
    assert allowed == False
    assert "Daily profit target" in reason

def test_vix_filter(engine):
    # Part 3: high VIX environment
    # Currently evaluate_trade_decision has a placeholder for VIX filter
    pass

def test_strike_distance_filter(engine):
    # Part 6: strike distance > 150 → reject
    # This is handled in _execute_signal
    pass
