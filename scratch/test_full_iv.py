import os
from dotenv import load_dotenv
from breeze_connect import BreezeConnect

load_dotenv()

def test_full_iv():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    session_token = os.getenv("SESSION_TOKEN")
    
    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    
    print("Fetching NIFTY Option Quote...")
    res = breeze.get_option_chain_quotes(
        stock_code="NIFTY",
        exchange_code="NFO",
        expiry_date="30-Apr-2026",
        product_type="options",
        right="call",
        strike_price="24500"
    )
    
    if res.get("Success"):
        row = res["Success"][0]
        print("KEYS:", sorted(row.keys()))
        for k, v in row.items():
            if 'vol' in k.lower() or 'iv' in k.lower() or 'implied' in k.lower():
                print(f"FOUND FIELD: {k} = {v}")
    else:
        print("Failed Nifty fetch:", res)

if __name__ == "__main__":
    test_full_iv()
