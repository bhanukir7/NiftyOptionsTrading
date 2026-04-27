import pandas as pd
import numpy as np
from ta.trend import MACD, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator

# Create dummy data with 12 rows
df = pd.DataFrame({
    "open": np.random.rand(12),
    "high": np.random.rand(12),
    "low": np.random.rand(12),
    "close": np.random.rand(12),
    "volume": np.random.rand(12)
})

print(f"Testing with df size: {len(df)}")

try:
    # 1. EMA Bias
    ema21_ind = EMAIndicator(df["close"], window=21).ema_indicator()
    print("EMA21 Success")
    ema50_ind = EMAIndicator(df["close"], window=50).ema_indicator()
    print("EMA50 Success")
    
    # 2. MACD
    macd_ind = MACD(df["close"])
    print("MACD Success")
    
    # 3. ATR
    atr_ind = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
    atr = atr_ind.average_true_range().iloc[-1]
    print("ATR Success")
    
    # 4. RSI
    rsi_val = RSIIndicator(df["close"], window=14).rsi().iloc[-1]
    print("RSI Success")
    
    # 5. Bollinger Bands
    bb_ind = BollingerBands(df["close"], window=20, window_dev=2)
    bb_upper = bb_ind.bollinger_hband().iloc[-1]
    print("BB Success")

except Exception as e:
    print(f"CAUGHT ERROR: {e}")
