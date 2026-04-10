"""
Live Market Background Scanner (Analytics Focus)
Continuously monitors market chains and tracks persistent real-time signals.

Author: Aditya Kota
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to sys.path to run from nifty_options_trading dir or parent dir
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from collections import defaultdict
from max_pain import calculate_max_pain
from theta_defense import calculate_dte, evaluate_theta_risk
from options_engine import get_option_chain
from alerts import send_alert
from nifty_options_trading.safe_breeze import SafeBreeze

load_dotenv(os.path.join(parent_dir, '.env'))

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
# Configure current expiry date (Format: YYYY-MM-DD or standard ISO without time)
EXPIRY_DATE = os.getenv("CURRENT_EXPIRY", "2026-04-09")

def initialize_breeze() -> SafeBreeze:
    print("Initializing Breeze API for Options Engine...")
    breeze = SafeBreeze(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
    return breeze

def run_analytics_monitor():
    if not API_KEY or not API_SECRET or not SESSION_TOKEN:
        print("[ERROR] Missing API_KEY, API_SECRET, or SESSION_TOKEN in .env.")
        return
        
    try:
        breeze = initialize_breeze()
    except Exception as e:
        print(f"[ERROR] Failed to initialize Breeze API. {e}")
        return
        
    STOCK_CODE = "NIFTY"
    print(f"Starting Multi-Stock Options Analytics Monitor for {STOCK_CODE}...")
    print(f"Monitoring Expiry: {EXPIRY_DATE}")
    
    last_max_pain = None
    last_defense_state = False
    
    while True:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time_str}] Fetching option chain & analyzing...")
        
        # 1. Fetch Option Chain
        chain_df = get_option_chain(breeze, STOCK_CODE, EXPIRY_DATE)
        
        if chain_df is not None and not chain_df.empty:
            # 2. Calculate Max Pain
            current_max_pain = calculate_max_pain(chain_df)
            
            # 3. Assess Theta Decay Defense Risk
            dte = calculate_dte(EXPIRY_DATE)
            risk_assessment = evaluate_theta_risk(dte, threshold=2)
            defense_active = risk_assessment["defense_active"]
            
            print(f"[{current_time_str}] Max Pain: {current_max_pain} | DTE: {dte}")
            
            alerts_to_send = []
            
            # Check for significant Max Pain shifts
            if current_max_pain > 0 and last_max_pain is not None and current_max_pain != last_max_pain:
                diff = current_max_pain - last_max_pain
                shift_msg = f"🟢 Shifted UP by {diff}" if diff > 0 else f"🔴 Shifted DOWN by {abs(diff)}"
                alerts_to_send.append(f"🎯 **Max Pain Shifted!**\nUnderlying: {STOCK_CODE}\nNew Max Pain: {current_max_pain}\nMovement: {shift_msg}")
            
            # Check for newly activated Defense
            if defense_active and not last_defense_state:
                alerts_to_send.append(f"🛡️ **Theta Defense Activated!**\n{risk_assessment['message']}")
            
            for alert in alerts_to_send:
                send_alert(alert)
                
            if current_max_pain > 0:
                last_max_pain = current_max_pain
            last_defense_state = defense_active
            
        else:
            print(f"[{current_time_str}] Failed to retrieve or parse option chain. Will retry...")
            
        # Poll every 5 minutes assuming chain data doesn't wildly vary second-by-second
        time.sleep(300)

if __name__ == "__main__":
    run_analytics_monitor()
