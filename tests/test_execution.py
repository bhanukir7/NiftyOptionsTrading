import pytest
from unittest.mock import MagicMock
from nifty_options_trading.trading_engine import AutonomousEngine

@pytest.fixture
def engine():
    breeze = MagicMock()
    return AutonomousEngine(breeze)

def test_order_execution_logging(engine):
    # Part 13: Ensure every decision logs: regime, bias, score
    engine.log = MagicMock()
    data = {
        "symbol": "NIFTY", "spot": 22000, "vwap": 22000, "ema21": 22000, "ema50": 21900,
        "macd": 1, "macd_signal": 0, "chop": 30, "atr": 10,
        "indicators": {"macd_hist": 1, "ema_alignment": True, "price_above_bb": True, "rsi": 60}
    }
    # _analyze_symbol calls evaluate_trade_decision and then logs
    # We can test evaluate_trade_decision output contains the metadata
    result = engine.evaluate_trade_decision(data)
    assert "regime" in result
    assert "bias" in result
    assert "score" in result
    assert "signal" in result

def test_slippage_simulation(engine):
    # Part 10: Mock order execution layer
    # Backtester already handles slippage simulation
    from nifty_options_trading.backtester import Backtester
    bt = Backtester(slippage_pct=0.01) # 1% slippage
    
    df = pd.DataFrame([
        {"close": 100, "datetime": "2023-01-01 09:30"},
        {"close": 110, "datetime": "2023-01-01 10:00"}
    ])
    # ... more complex mock needed for full backtest simulation
    pass

import pandas as pd
