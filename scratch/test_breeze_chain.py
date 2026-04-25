import os
from dotenv import load_dotenv
from breeze_connect import BreezeConnect

load_dotenv()

def test_breeze_option_chain():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    session_token = os.getenv("SESSION_TOKEN")
    
    if not all([api_key, api_secret, session_token]):
        print("Error: Missing credentials")
        return

    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    
    print("Fetching Option Chain for NIFTY...")
    res = breeze.get_option_chain_quotes(
        stock_code="NIFTY",
        exchange_code="NFO",
        expiry_date="30-Apr-2026",
        product_type="options"
    )
    
    if res.get("Status") == 200 and res.get("Success"):
        first_row = res["Success"][0]
        print("\nRow Data Keys:", first_row.keys())
        print(f"  Symbol: {first_row.get('stock_code')}")
        print(f"  Strike: {first_row.get('strike_price')}")
        print(f"  Call IV: {first_row.get('implied_volatility')}")
        
        # Check if IV is actually a value
        iv = first_row.get('implied_volatility')
        if iv and float(iv) > 0:
            print(f"\nSUCCESS: Live IV is available in Option Chain: {iv}")
        else:
            print("\nIV field found but value is 0 or None.")
    else:
        print("Failed to fetch option chain.")
        print("Response:", res)

if __name__ == "__main__":
    test_breeze_option_chain()
