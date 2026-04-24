import os
import webbrowser
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urlencode
from pathlib import Path
from dotenv import load_dotenv, set_key

if os.name == 'nt':
    import msvcrt

# ── Path Setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH  = REPO_ROOT / ".env"

# ── Local Redirect Listener ───────────────────────────────────────────────────
class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if "apisession" in params:
            self.server.token = params["apisession"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body style='font-family:sans-serif; text-align:center; padding-top:100px;'>")
            self.wfile.write(b"<h1 style='color:#28a745;'>Success!</h1>")
            self.wfile.write(b"<p>Session Token captured successfully. You can close this tab now.</p>")
            self.wfile.write(b"</body></html>")
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"No apisession parameter found in redirect.")

    def log_message(self, format, *args):
        return # Silence logs

def capture_session_token(api_key, port=8080):
    """Starts a local server and opens the login URL."""
    # Robust URL parameter encoding
    params = {"api_key": api_key}
    query_string = urlencode(params)
    # Using the official Breeze API Login URL
    login_url = f"https://api.icicidirect.com/apiuser/login?{query_string}"
    
    print(f"\n[SessionManager] Opening browser for login...")
    print(f"[SessionManager] URL: {login_url}")
    webbrowser.open(login_url)
    
    server = HTTPServer(("127.0.0.1", port), RedirectHandler)
    server.token = None
    
    print(f"[SessionManager] Waiting for redirect on http://127.0.0.1:{port} ...")
    
    # Timeout after 5 minutes
    start_time = time.time()
    print(f"[SessionManager] (If the browser shows an error or doesn't redirect, you can manually paste the full redirect URL here).")
    
    server.timeout = 0.5 # Allow checking for manual input or timeout
    while not server.token:
        server.handle_request()
        
        # Non-blocking manual input check (Windows)
        if os.name == 'nt' and msvcrt.kbhit():
            print("\n[SessionManager] Manual entry triggered. Please paste the full redirect URL:")
            manual_url = input("> ").strip()
            if "apisession=" in manual_url:
                query = urlparse(manual_url).query
                params = parse_qs(query)
                if "apisession" in params:
                    server.token = params["apisession"][0]
                    break
            else:
                print("[!] Invalid URL. Still waiting for automatic redirect or another manual attempt...")

        if time.time() - start_time > 300:
            print(" [!] Timeout: No login detected within 5 minutes.")
            return None
            
    return server.token

# ── .env Management ───────────────────────────────────────────────────────────
def update_env_token(token):
    """Updates the SESSION_TOKEN in .env using python-dotenv."""
    if not ENV_PATH.exists():
        # Fallback to creating a new one if somehow missing
        with open(ENV_PATH, "w") as f:
            f.write(f"SESSION_TOKEN={token}\n")
        return True
    
    # set_key handles replacing an existing key or adding it, preserving comments.
    success = set_key(str(ENV_PATH), "SESSION_TOKEN", token)
    return success

# ── Session Health Check ──────────────────────────────────────────────────────
def check_session_health(api_key, api_secret, session_token, broker_type="ICICI_BREEZE", **kwargs):
    """
    Returns (bool, str) -> (is_valid, error_message)
    Tries a lightweight API call to verify the session.
    """
    if broker_type == "ICICI_BREEZE":
        from breeze_connect import BreezeConnect
        try:
            breeze = BreezeConnect(api_key=api_key)
            breeze.generate_session(api_secret=api_secret, session_token=session_token)
            res = breeze.get_customer_details(api_session=session_token)
            if res.get("Status") == 200:
                return True, "Valid"
            else:
                return False, res.get("Error", "Unknown Error")
        except Exception as e:
            return False, str(e)
    elif broker_type == "ANGLE_ONE":
        from SmartApi import SmartConnect
        try:
            smart = SmartConnect(api_key=api_key)
            # SmartAPI uses jwtToken for subsequent requests.
            # We check profile to verify session.
            smart.setAccessToken(session_token)
            res = smart.getProfile(kwargs.get("refresh_token", ""))
            if res.get("status"):
                return True, "Valid"
            else:
                return False, res.get("message", "Unknown Error")
        except Exception as e:
            return False, str(e)
    return False, "Unsupported Broker"

def login_smartapi(api_key, client_code, password, totp_secret):
    """Performs silent TOTP login for Angle One."""
    from nifty_options_trading.safe_smartapi import SafeSmartAPI
    try:
        broker = SafeSmartAPI(api_key=api_key)
        res = broker.generate_session(client_code, password, totp_secret)
        if res.get('status'):
            return res['data']['jwtToken'], res['data']['refreshToken']
    except Exception as e:
        print(f"[SessionManager] Angle One Login Failed: {e}")
    return None, None

if __name__ == "__main__":
    # Internal CLI for manual refresh
    load_dotenv(ENV_PATH)
    AK = os.getenv("API_KEY")
    if not AK:
        print("[!] API_KEY not found in .env")
        exit(1)
        
    new_token = capture_session_token(AK)
    if new_token:
        if update_env_token(new_token):
            print(f"[+] Successfully updated .env with new token: {new_token[:4]}...{new_token[-4:]}")
        else:
            print("[!] Failed to update .env")
    else:
        print("[!] Failed to capture token.")
