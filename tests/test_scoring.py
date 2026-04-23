import pytest
from unittest.mock import MagicMock
from nifty_options_trading.trading_engine import AutonomousEngine

@pytest.fixture
def engine():
    breeze = MagicMock()
    return AutonomousEngine(breeze)

def test_compute_score_trend_strong(engine):
    # Part 5: Strong trend inputs → score ≥ 70
    indicators = {
        "macd_hist": 1,
        "ema_alignment": True,
        "price_above_bb": True,
        "rsi": 60
    }
    # TREND: macd_hist(30) + ema_alignment(20) + price_above_bb(15) + rsi>55(10) = 75
    score = engine.compute_score(indicators, "TREND")
    assert score >= 70

def test_compute_score_trend_medium(engine):
    # Part 5: Medium inputs → score between 50–69
    indicators = {
        "macd_hist": 1,
        "ema_alignment": True,
        "price_above_bb": False,
        "rsi": 50
    }
    # TREND: macd_hist(30) + ema_alignment(20) = 50
    score = engine.compute_score(indicators, "TREND")
    assert 50 <= score <= 69

def test_compute_score_trend_weak(engine):
    # Part 5: Weak inputs → score < 50
    indicators = {
        "macd_hist": -1,
        "ema_alignment": False,
        "price_above_bb": False,
        "rsi": 40
    }
    score = engine.compute_score(indicators, "TREND")
    assert score < 50

def test_signal_classification_high(engine):
    data = {
        "symbol": "NIFTY", "spot": 22000, "vwap": 22000, "ema21": 22000, "ema50": 21900,
        "macd": 1, "macd_signal": 0, "chop": 30, "atr": 10,
        "indicators": {
            "macd_hist": 1, "ema_alignment": True, "price_above_bb": True, "rsi": 60
        }
    }
    result = engine.evaluate_trade_decision(data)
    assert result["signal"] == "HIGH_CONVICTION"

def test_signal_classification_medium(engine):
    data = {
        "symbol": "NIFTY", "spot": 22000, "vwap": 22000, "ema21": 22000, "ema50": 21900,
        "macd": 1, "macd_signal": 0, "chop": 30, "atr": 10,
        "indicators": {
            "macd_hist": 1, "ema_alignment": True, "price_above_bb": False, "rsi": 50
        }
    }
    result = engine.evaluate_trade_decision(data)
    assert result["signal"] == "MEDIUM"
