from datetime import datetime, date, timedelta
from nifty_options_trading.rule_engine import Config

# NSE Holidays for 2025-2026
HOLIDAYS = [
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14",
    "2025-04-18", "2025-05-01", "2025-08-15", "2025-10-02", "2025-10-21", "2025-11-05",
    "2026-01-26", "2026-03-03", "2026-03-24", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-08-15", "2026-10-02", "2026-11-09", "2026-12-25"
]

class ExpiryDayEngine:
    def is_expiry_today(self, symbol: str) -> bool:
        """Determines if today is the expiry day for the given symbol."""
        symbol = symbol.upper()
        today = date.today()
        weekday = today.weekday()
        
        # NIFTY: Thursday (3), BANKNIFTY: Wednesday (2), SENSEX: Friday (4)
        target_weekday = 3 if symbol == "NIFTY" else (2 if symbol in ["BANKNIFTY", "CNXBAN"] else (4 if symbol in ["SENSEX", "BSESN", "BSESEN"] else -1))
        
        if target_weekday == -1: return False
        
        # If today is a holiday, it can't be the expiry day (it should have shifted earlier)
        if today.strftime("%Y-%m-%d") in HOLIDAYS:
            return False

        if weekday == target_weekday:
            return True
            
        # Shift logic: If the standard expiry day is a holiday, the previous trading day is expiry.
        # We check if target_weekday is in the future this week and if all days between today and target are holidays.
        for d in range(1, 4):
            check_date = today + timedelta(days=d)
            if check_date.weekday() == target_weekday:
                # If target day is holiday, today might be expiry if no other days between are open
                if check_date.strftime("%Y-%m-%d") in HOLIDAYS:
                    return True
                else:
                    return False
            if check_date.strftime("%Y-%m-%d") not in HOLIDAYS:
                # Found an open day before target, so today is not expiry
                break

        return False

    def get_expiry_parameters(self, symbol: str, spot: float, hours_to_expiry: float) -> dict:
        """Adjusts trading parameters based on time remaining to expiry."""
        config = Config()
        if hours_to_expiry < 2:
            return {
                "sl_pct": 0.30,
                "target_pct": 0.20,
                "max_lots": 1,
                "otm_limit": 50,
                "note": "Gamma risk high: Tight SL and targets"
            }
        elif 2 <= hours_to_expiry <= 4:
            return {
                "sl_pct": 0.25,
                "target_pct": 0.30,
                "max_lots": 2,
                "otm_limit": 100,
                "note": "Balanced expiry risk"
            }
        else:
            return {
                "sl_pct": config.sl_pct,
                "target_pct": config.sl_pct * 2,
                "max_lots": config.max_lots,
                "otm_limit": 150,
                "note": "Standard trading parameters"
            }

    def get_gamma_risk_strikes(self, symbol: str, spot: float, option_chain: dict) -> dict:
        """Identifies strikes with high gamma and pin risk."""
        strikes = option_chain.get("strikes", [])
        if not strikes: return {"high_gamma_strike": 0, "pin_risk_zone": [], "avoid_selling": False}
        
        try:
            high_gamma_strike_data = max(strikes, key=lambda x: max(x["CE"].get("gamma", 0), x["PE"].get("gamma", 0)))
            high_gamma_strike = high_gamma_strike_data["strikePrice"]
            pin_risk_zone = [s["strikePrice"] for s in strikes if abs(s["strikePrice"] - spot) <= 50]
            
            return {
                "high_gamma_strike": high_gamma_strike,
                "pin_risk_zone": pin_risk_zone,
                "avoid_selling": abs(high_gamma_strike - spot) < 50
            }
        except Exception as e:
            print(f"Error in gamma risk calculation: {e}")
            return {"high_gamma_strike": 0, "pin_risk_zone": [], "avoid_selling": False}

    def get_expiry_recommendation(self, symbol: str, spot: float, vix: float, hours_to_expiry: float, trending: bool = False) -> dict:
        """Provides trading recommendations based on VIX, time, and trend."""
        if vix > 18 and hours_to_expiry < 2:
            return {
                "recommendation": "AVOID — High IV + Gamma risk",
                "rationale": f"VIX is high ({vix}) and time is short. Gamma explosions likely."
            }
        
        if vix < 14 and hours_to_expiry > 3:
            return {
                "recommendation": "Short Straddle / Iron Condor — IV crush expected",
                "rationale": "Low VIX and plenty of time for theta decay. Safe for premium eating."
            }
        
        if trending:
            return {
                "recommendation": "ATM directional — tight SL",
                "rationale": "Trending market detected. Follow momentum with strict discipline."
            }
            
        return {
            "recommendation": "Scalp only / Wait for breakout",
            "rationale": "Range bound market. Wait for clear ORB breakout or volume spike."
        }
