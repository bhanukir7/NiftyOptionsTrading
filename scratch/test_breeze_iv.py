import os
from dotenv import load_dotenv
from breeze_connect import BreezeConnect

load_dotenv()

def test_breeze_iv():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    session_token = os.getenv("SESSION_TOKEN")
    
    if not all([api_key, api_secret, session_token]):
        print("Error: Missing credentials")
        return

    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    
    # Test with a Nifty Option
    # Note: Using current month/expiry logic or hardcoded for test
    print("Fetching quote for NIFTY Option...")
    res = breeze.get_quotes(
        stock_code="NIFTY",
        exchange_code="NFO",
        expiry_date="30-Apr-2026",
        product_type="options",
        right="call",
        strike_price="24500"
    )
    
    if res.get("Status") == 200 and res.get("Success"):
        quote = res["Success"][0]
        print("\nQuote Data Keys:", quote.keys())
        iv = quote.get("implied_volatility")
        print(f"  Symbol: {quote.get('stock_code')}")
        print(f"  Strike: {quote.get('strike_price')}")
        print(f"  LTP: {quote.get('ltp')}")
        print(f"  Implied Volatility (IV): {iv}")
        
        if iv is None:
            print("\nIV is NOT present in get_quotes response.")
        else:
            print(f"\nSUCCESS: IV is available: {iv}")
    else:
        print("Failed to fetch quote or no data found.")
        print("Response:", res)

if __name__ == "__main__":
    test_breeze_iv()
