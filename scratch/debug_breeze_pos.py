import os
import asyncio
from dotenv import load_dotenv
from breeze_connect import BreezeConnect

load_dotenv()

def debug_breeze_positions():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    session_token = os.getenv("SESSION_TOKEN")
    
    if not all([api_key, api_secret, session_token]):
        print("Error: Missing credentials in .env")
        return

    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    
    print("Fetching positions...")
    res = breeze.get_portfolio_positions()
    print("Response Status:", res.get("Status"))
    print("Response Keys:", res.keys())
    
    if res.get("Success"):
        print(f"Found {len(res['Success'])} positions in 'Success' list.")
        for i, pos in enumerate(res["Success"]):
            print(f"\nPosition {i+1}:")
            print(f"  Stock: {pos.get('stock_code')}")
            print(f"  Qty: {pos.get('net_quantity')}")
            print(f"  Full Data: {pos}")
    else:
        print("No 'Success' data found or list is empty.")
        print("Full Response:", res)

if __name__ == "__main__":
    debug_breeze_positions()
