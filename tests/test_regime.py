import pytest
from unittest.mock import MagicMock
from nifty_options_trading.trading_engine import AutonomousEngine

@pytest.fixture
def engine():
    breeze = MagicMock()
    return AutonomousEngine(breeze)

def test_detect_regime_range(engine):
    # Part 2: chop=60 → expect "RANGE"
    assert engine.detect_regime(chop=60, atr=10, macd=1, macd_signal=0.5) == "RANGE"

def test_detect_regime_trend(engine):
    # Part 2: chop=25, strong MACD → expect "TREND"
    # macd - macd_signal = 1 - 0 = 1 > threshold (0.5)
    assert engine.detect_regime(chop=25, atr=10, macd=1, macd_signal=0) == "TREND"

def test_detect_regime_no_trade(engine):
    # Part 2: chop=40 → expect "NO_TRADE"
    assert engine.detect_regime(chop=40, atr=10, macd=1, macd_signal=0.5) == "NO_TRADE"

def test_no_trade_stops_evaluation(engine):
    # Part 2: assert NO_TRADE stops further evaluation in evaluate_trade_decision
    data = {
        "symbol": "NIFTY",
        "spot": 22000,
        "vwap": 22000,
        "ema21": 22000,
        "ema50": 22000,
        "macd": 1,
        "macd_signal": 0.5,
        "chop": 40,
        "atr": 10,
        "indicators": {}
    }
    result = engine.evaluate_trade_decision(data)
    assert result["decision"] == "NO_TRADE"
    assert "indicates no clear regime" in result["reason"]
