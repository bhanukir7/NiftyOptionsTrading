"""
Legacy Intraday Scalp Generator
Utilizes simple EMA crosses and MACD logic to determine primitive BUY_CALL/BUY_PUT logic for alerting.

Author: Aditya Kota
"""
import pandas as pd
from ta.trend import EMAIndicator, MACD

def analyze_and_generate_signal(df: pd.DataFrame) -> str:
    """
    Analyzes historical data and returns a signal ('BUY_CALL', 'BUY_PUT', or 'HOLD').
    Parameters:
        df: A pandas DataFrame containing Nifty historical OHLC data with a 'close' column.
        
    Strategy Logic (Example):
        - Buy Call if EMA 9 crosses above EMA 21 and MACD histogram is positive.
        - Buy Put if EMA 9 crosses below EMA 21 and MACD histogram is negative.
    """
    if df is None or len(df) < 50:
        return "HOLD"
        
    # Calculate Indicators
    ema9 = EMAIndicator(close=df["close"], window=9)
    df["EMA_9"] = ema9.ema_indicator()
    
    ema21 = EMAIndicator(close=df["close"], window=21)
    df["EMA_21"] = ema21.ema_indicator()
    
    macd = MACD(close=df["close"])
    df["MACD_Hist"] = macd.macd_diff()
    
    # Get last two rows to check for a crossover
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    # Check EMA crossover above
    call_condition = (prev_row["EMA_9"] <= prev_row["EMA_21"]) and \
                     (last_row["EMA_9"] > last_row["EMA_21"]) and \
                     (last_row["MACD_Hist"] > 0)
                     
    # Check EMA crossover below
    put_condition = (prev_row["EMA_9"] >= prev_row["EMA_21"]) and \
                    (last_row["EMA_9"] < last_row["EMA_21"]) and \
                    (last_row["MACD_Hist"] < 0)
                    
    if call_condition:
        return "BUY_CALL"
    elif put_condition:
        return "BUY_PUT"
    
    return "HOLD"
