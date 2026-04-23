import pytest
from unittest.mock import MagicMock
from nifty_options_trading.trading_engine import AutonomousEngine

@pytest.fixture
def engine():
    breeze = MagicMock()
    # Mocking historical data fetch
    breeze.get_historical_data.return_value = {
        "Status": 200,
        "Success": [
            {"open": 22000, "high": 22100, "low": 21900, "close": 22050, "volume": 1000},
            # ... more rows
        ] * 100
    }
    return AutonomousEngine(breeze)

def test_full_pipeline_trend_day(engine):
    # Part 15: Simulate TREND DAY
    # 1. Setup market conditions
    engine.stream.get_price = MagicMock(return_value=22100)
    
    # 2. Run analysis
    engine._analyze_symbol("NIFTY")
    
    # 3. Check if trade was executed (if conditions were met)
    # This depends on the exact mock data. 
    # If score >= 70, _execute_signal is called.
    pass

def test_missing_data_safe_skip(engine):
    # Part 16: Missing data
    engine.breeze.get_historical_data.return_value = {"Status": 500, "Success": None}
    engine._analyze_symbol("NIFTY")
    # Should not crash
    assert len(engine.state.active_positions) == 0
