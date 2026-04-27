import math
import time
import requests
from datetime import datetime, date, timedelta
from nifty_options_trading.cache_manager import CacheManager

class NSEGreeksFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/"
        })
        self.cache = CacheManager()
        self._init_session()

    def _init_session(self):
        """Initializes NSE session to get cookies."""
        try:
            self.session.get("https://www.nseindia.com", timeout=10)
        except Exception as e:
            print(f"[NSEGreeksFetcher] Session init failed: {e}")

    def n_cdf(self, x):
        """Normal Cumulative Distribution Function."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def n_pdf(self, x):
        """Normal Probability Density Function."""
        return math.exp(-0.5 * x**2) / math.sqrt(2 * math.pi)

    def calculate_greeks(self, S, K, T, r, sigma, option_type="CE"):
        """
        Black-Scholes Greek calculation.
        S: Spot Price
        K: Strike Price
        T: Time to expiry in years
        r: Risk-free rate (e.g., 0.07)
        sigma: Implied Volatility (e.g., 0.15 for 15%)
        """
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        
        try:
            d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            
            if option_type == "CE":
                delta = self.n_cdf(d1)
                theta = (- (S * self.n_pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * self.n_cdf(d2))
            else:
                delta = self.n_cdf(d1) - 1
                theta = (- (S * self.n_pdf(d1) * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * self.n_cdf(-d2))
                
            gamma = self.n_pdf(d1) / (S * sigma * math.sqrt(T))
            vega = S * self.n_pdf(d1) * math.sqrt(T) / 100 # Per 1% IV change
            
            return {
                "delta": round(delta, 4),
                "gamma": round(gamma, 6),
                "theta": round(theta / 365, 4), # Theta per day
                "vega": round(vega, 4)
            }
        except Exception as e:
            print(f"[NSEGreeksFetcher] Greek calc error: {e}")
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}

    def fetch_option_chain(self, symbol: str) -> dict:
        """Fetches NSE option chain and calculates Greeks."""
        cache_key = f"nse_chain_{symbol}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        data = None
        source = "NSE"

        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    break
                elif response.status_code in [401, 403]:
                    self._init_session()
                    time.sleep(2)
                else:
                    time.sleep(2)
            except Exception as e:
                print(f"[NSEGreeksFetcher] Attempt {attempt+1} failed for {symbol}: {e}")
                time.sleep(2)

        if not data:
            return {"error": "NSE API Unavailable", "source": "unavailable", "strikes": []}

        try:
            records = data.get("records", {})
            filtered = data.get("filtered", {})
            spot = float(records.get("underlyingValue", 0))
            if spot == 0:
                # Try fallback from filtered
                spot = float(filtered.get("data", [{}])[0].get("CE", {}).get("underlyingValue", 0) or 
                             filtered.get("data", [{}])[0].get("PE", {}).get("underlyingValue", 0) or 0)

            expiry_list = records.get("expiryDates", [])
            if not expiry_list:
                return {"error": "No expiry dates found", "source": source, "strikes": []}
            
            target_expiry = filtered.get("data", [{}])[0].get("expiryDate", expiry_list[0])
            
            # Calculate T (Time to expiry in years)
            expiry_dt = datetime.strptime(target_expiry, "%d-%b-%Y").replace(hour=15, minute=30)
            now = datetime.now()
            time_diff = (expiry_dt - now).total_seconds()
            T = max(0, time_diff) / (365 * 24 * 3600)
            
            strikes_processed = []
            for item in filtered.get("data", []):
                strike_price = float(item.get("strikePrice"))
                ce = item.get("CE", {})
                pe = item.get("PE", {})
                
                strike_data = {
                    "strikePrice": strike_price,
                    "CE": self._enrich_leg(ce, spot, strike_price, T, "CE"),
                    "PE": self._enrich_leg(pe, spot, strike_price, T, "PE"),
                }
                strikes_processed.append(strike_data)
            
            result = {
                "symbol": symbol,
                "spot": spot,
                "expiry": target_expiry,
                "strikes": strikes_processed,
                "source": source,
                "timestamp": datetime.now().isoformat()
            }
            self.cache.set(cache_key, result, ttl=60)
            return result

        except Exception as e:
            print(f"[NSEGreeksFetcher] Data processing error: {e}")
            return {"error": f"Processing Error: {str(e)}", "source": "BlackScholes", "strikes": []}

    def _enrich_leg(self, leg, spot, strike, T, option_type):
        """Enriches a leg with Greeks if missing."""
        iv = float(leg.get("impliedVolatility", 0)) / 100.0
        ltp = float(leg.get("lastPrice", 0))
        oi = float(leg.get("openInterest", 0))
        oi_change = float(leg.get("changeinOpenInterest", 0))
        
        greeks = self.calculate_greeks(spot, strike, T, 0.07, iv, option_type)
        
        return {
            "lastPrice": ltp,
            "impliedVolatility": round(iv * 100, 2),
            "openInterest": oi,
            "changeinOpenInterest": oi_change,
            **greeks
        }

    def get_atm_greeks(self, symbol: str, spot: float) -> dict:
        """Return only the ATM strike CE and PE Greeks."""
        chain = self.fetch_option_chain(symbol)
        if "error" in chain or not chain.get("strikes"):
            return {}
        
        # Find ATM strike
        strikes = chain["strikes"]
        atm_strike = min(strikes, key=lambda x: abs(x["strikePrice"] - spot))
        return {
            "symbol": symbol,
            "spot": spot,
            "strike": atm_strike["strikePrice"],
            "CE": atm_strike["CE"],
            "PE": atm_strike["PE"],
            "expiry": chain["expiry"],
            "source": chain["source"]
        }
