import yfinance as yf
import pandas as pd

ticker = "^BSESN"
data = yf.download(ticker, period="2d", interval="5m", progress=False)
print("Columns:", data.columns)
print("Index Name:", data.index.name)
df = data.reset_index()
print("Reset columns:", df.columns)
print("First row:\n", df.head(1))
