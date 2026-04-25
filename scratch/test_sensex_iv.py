import os
from dotenv import load_dotenv
from breeze_connect import BreezeConnect

load_dotenv()

def test_sensex_iv():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    session_token = os.getenv("SESSION_TOKEN")
    
    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    
    # Try SENSEX instead of BSESEN
    print("Fetching Sensex Option Chain...")
    res = breeze.get_option_chain_quotes(
        stock_code="SENSEX",
        exchange_code="BFO",
        expiry_date="30-Apr-2026",
        product_type="options",
        right="call",
        strike_price="78500"
    )
    
    print("Status:", res.get("Status"))
    if res.get("Success"):
        row = res["Success"][0]
        print("Success! Keys:", row.keys())
        print("IV:", row.get("implied_volatility"))
    else:
        print("Failed. Error:", res.get("Error"))
        
    # Try BSESEN to confirm failure
    print("\nTrying with BSESEN symbol...")
    res2 = breeze.get_option_chain_quotes(
        stock_code="BSESEN",
        exchange_code="BFO",
        expiry_date="30-Apr-2026",
        product_type="options",
        right="call",
        strike_price="78500"
    )
    print("Status:", res2.get("Status"))
    print("Error:", res2.get("Error"))

if __name__ == "__main__":
    test_sensex_iv()
