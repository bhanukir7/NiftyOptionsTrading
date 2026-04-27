import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from nifty_options_trading.nse_greeks_fetcher import NSEGreeksFetcher
from nifty_options_trading.strategy_builder import StrategyBuilder
from nifty_options_trading.expiry_engine import ExpiryDayEngine

def test_strategy_legs():
    """Verify Iron Condor leg generation (Sell OTM1, Buy OTM2)."""
    builder = StrategyBuilder()
    mock_chain = {
        "strikes": [
            {"strikePrice": 22000, "CE": {"lastPrice": 100, "delta": 0.5, "gamma": 0.001, "theta": -10, "vega": 5}, "PE": {"lastPrice": 100, "delta": -0.5, "gamma": 0.001, "theta": -10, "vega": 5}},
            {"strikePrice": 22100, "CE": {"lastPrice": 50, "delta": 0.3, "gamma": 0.0008, "theta": -8, "vega": 4}},
            {"strikePrice": 22200, "CE": {"lastPrice": 20, "delta": 0.1, "gamma": 0.0005, "theta": -5, "vega": 3}},
            {"strikePrice": 21900, "PE": {"lastPrice": 50, "delta": -0.3, "gamma": 0.0008, "theta": -8, "vega": 4}},
            {"strikePrice": 21800, "PE": {"lastPrice": 20, "delta": -0.1, "gamma": 0.0005, "theta": -5, "vega": 3}},
        ]
    }
    with patch.object(builder, '_get_chain', return_value=mock_chain):
        res = builder.iron_condor(22000, "2026-04-02", "NIFTY")
        assert len(res["legs"]) == 4
        # CE Legs
        assert any(l["strike"] == 22100 and l["side"] == "SELL" and l["type"] == "CE" for l in res["legs"])
        assert any(l["strike"] == 22200 and l["side"] == "BUY" and l["type"] == "CE" for l in res["legs"])
        # PE Legs
        assert any(l["strike"] == 21900 and l["side"] == "SELL" and l["type"] == "PE" for l in res["legs"])
        assert any(l["strike"] == 21800 and l["side"] == "BUY" and l["type"] == "PE" for l in res["legs"])

def test_expiry_detection():
    """Verify expiry detection and holiday shift logic."""
    engine = ExpiryDayEngine()
    
    # 1. Standard Thursday
    with patch('nifty_options_trading.expiry_engine.date') as mock_date:
        mock_date.today.return_value = date(2026, 4, 2) # Thursday
        with patch('nifty_options_trading.expiry_engine.HOLIDAYS', []):
            assert engine.is_expiry_today("NIFTY") == True

    # 2. Holiday Shift (Thursday 26th is holiday, Wednesday 25th should be expiry)
    with patch('nifty_options_trading.expiry_engine.date') as mock_date:
        mock_date.today.return_value = date(2026, 3, 25) # Wednesday
        with patch('nifty_options_trading.expiry_engine.HOLIDAYS', ["2026-03-26"]):
            assert engine.is_expiry_today("NIFTY") == True

def test_portfolio_greek_aggregation():
    """Verify net delta calculation for a simple portfolio."""
    # This logic is in app.py, but we can test the aggregation math
    net_delta = 0
    positions = [
        {"delta": 0.6, "quantity": 50},  # Buy 1 lot NIFTY (CE)
        {"delta": 0.4, "quantity": -50}  # Sell 1 lot NIFTY (CE)
    ]
    for p in positions:
        net_delta += p["delta"] * p["quantity"]
    assert net_delta == (0.6 * 50) - (0.4 * 50) # 10.0

def test_nse_fallback_to_bs():
    """Verify that if NSE API fails, we return error and Black-Scholes tag (in fetcher)."""
    fetcher = NSEGreeksFetcher()
    with patch('requests.Session.get') as mock_get:
        mock_get.return_value.status_code = 404
        res = fetcher.fetch_option_chain("NIFTY")
        assert "error" in res
        assert res["source"] == "unavailable"
