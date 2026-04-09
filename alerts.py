import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(message: str):
    """
    Dispatch an alert to the user.
    Currently defaults to Console printing and Telegram if configured.
    """
    print(f"\n[ALERT GENERATED] {message}")
    
    # Send to telegram if configured
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"[ERROR] Failed to send Telegram alert: {response.text}")
        except Exception as e:
            print(f"[ERROR] Exception sending Telegram alert: {e}")
