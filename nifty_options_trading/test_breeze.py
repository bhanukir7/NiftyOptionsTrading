import os
import sys
from dotenv import load_dotenv

# Ensure the parent directory is in the python path to prevent ModuleNotFoundError
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from breeze_connect import BreezeConnect

load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

breeze = BreezeConnect(api_key=API_KEY)
breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)

# Let's see what get_quotes returns for NIFTY spot
print("--- NIFTY Spot Quotes ---")
resp = breeze.get_quotes(stock_code="NIFTY", exchange_code="NSE", product_type="cash")
print(resp)

# Let's see what get_quotes returns for an Option
# We will use NIFTY to be safe
print("\n--- NIFTY Option Quotes ---")
resp2 = breeze.get_quotes(stock_code="NIFTY", exchange_code="NFO", product_type="options", expiry_date="2024-04-25T06:00:00.000Z", right="Call", strike_price="22500")
print(resp2)

# Maybe there is a get_contract_detail ? Let's see if dir helps
print("\n--- BreezeConnect dir ---")
print([m for m in dir(breeze) if not m.startswith('_')])
