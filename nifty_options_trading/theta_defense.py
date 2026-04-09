"""
DTE Theta Decay Engine
Analyses options decay curves based on Days to Expiry to warn against bleeding contracts.

Author: Aditya Kota
"""
from datetime import datetime, date

def calculate_dte(expiry_date_str: str) -> int:
    """
    Calculates the Days to Expiry (DTE) from today.
    
    Parameters:
        expiry_date_str: Expiration date in 'YYYY-MM-DD' format.
        
    Returns:
        Integer representing the number of days until expiration.
    """
    try:
        expiry_date = datetime.strptime(expiry_date_str[:10], "%Y-%m-%d").date()
        today = date.today()
        # Assume expiry happens at end of day, so if today is expiry, DTE is 0 (or slight positive intra-day, but 0 is safe).
        dte = (expiry_date - today).days
        return max(0, dte)
    except Exception as e:
        print(f"Error calculating DTE: {e}")
        return 999  # Return large number to avoid triggering defense on error

def evaluate_theta_risk(dte: int, threshold: int = 2) -> dict:
    """
    Evaluates the theta decay risk based on the Days to Expiry.
    
    Parameters:
        dte: Days to Expiry.
        threshold: The DTE threshold below which risk is considered elevated.
        
    Returns:
        Dictionary with 'defense_active' boolean and a 'message'.
    """
    if dte <= threshold:
        return {
            "defense_active": True,
            "message": f"DTE is {dte} day(s) (<= {threshold}). Warning: Rapid Theta decay expected. Avoid buying OTM options or tighten stop-losses on long options."
        }
    else:
        return {
            "defense_active": False,
            "message": f"DTE is {dte} day(s). Theta decay risk is moderate."
        }
