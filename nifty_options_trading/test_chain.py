import os
import sys
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from breeze_connect import BreezeConnect

load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")

try:
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)

    print("--- NIFTY Option Chain Quotes ---")
    resp = breeze.get_option_chain_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date="2026-04-21T06:00:00.000Z",
                right="Call"
            )
    if 'Success' in resp and resp['Success']:
        print("Success keys:")
        print(resp['Success'][0])
    else:
        print("Empty or invalid:", resp)
except Exception as e:
    print("Error:", e)
