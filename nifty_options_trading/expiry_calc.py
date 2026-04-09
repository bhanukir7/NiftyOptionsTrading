"""
Expiry Tracking Module
Calculates valid immediate and weekly expiries for corresponding index option types.

Author: Aditya Kota
"""
from datetime import datetime, date, timedelta
import calendar

# Add any known NSE market holidays here (format: YYYY-MM-DD)
HOLIDAYS = [
    "2026-01-26", # Republic Day
    "2026-03-03", # Mahashivratri
    "2026-03-24", # Holi
    "2026-04-03", # Good Friday
    "2026-04-14", # Ambedkar Jayanti
    "2026-05-01", # Maharashtra Day
    "2026-08-15", # Independence Day
    "2026-10-02", # Gandhi Jayanti
    "2026-11-09", # Diwali
    "2026-12-25"  # Christmas
]

def _is_holiday(check_date: date) -> bool:
    return check_date.strftime("%Y-%m-%d") in HOLIDAYS

def _apply_holiday_fallback(target_date: date) -> date:
    """If the target expiry day is a holiday, it shifts to the previous working day."""
    while _is_holiday(target_date):
        target_date -= timedelta(days=1)
    return target_date

def get_next_weekly_expiry(from_date: date = None) -> str:
    """
    Returns the next upcoming Tuesday. If Tuesday is a holiday, returns Monday.
    Used for indices like NIFTY.
    """
    if from_date is None:
        from_date = date.today()
        
    days_ahead = 1 - from_date.weekday() # Tuesday is 1
    if days_ahead < 0: # Target day already happened this week
        days_ahead += 7
        
    target_date = from_date + timedelta(days=days_ahead)
    final_date = _apply_holiday_fallback(target_date)
    return final_date.strftime("%Y-%m-%d")

def get_month_end_expiry(from_date: date = None) -> str:
    """
    Returns the Last Tuesday of the month.
    If the last Tuesday has already passed for the current month, returns the last Tuesday of the next month.
    Used for CNXBAN and stock options.
    """
    if from_date is None:
        from_date = date.today()
        
    year = from_date.year
    month = from_date.month
    
    def _last_tuesday_of_month(y: int, m: int) -> date:
        last_day = calendar.monthrange(y, m)[1]
        last_date = date(y, m, last_day)
        # Tuesday is 1
        offset = (last_date.weekday() - 1) % 7
        target = last_date - timedelta(days=offset)
        return _apply_holiday_fallback(target)
        
    candidate = _last_tuesday_of_month(year, month)
    
    # If the month-end expiry for this month has already passed, roll to next month
    if candidate < from_date:
        if month == 12:
            candidate = _last_tuesday_of_month(year + 1, 1)
        else:
            candidate = _last_tuesday_of_month(year, month + 1)
            
    return candidate.strftime("%Y-%m-%d")

def get_dynamic_expiry(symbol: str) -> str:
    """
    Master function determining the proper expiry based on the instrument symbol.
    """
    MONTHLY_SYMBOLS = ["CNXBAN"]
    
    # If it's a specific known index running weekly, return weekly.
    # Otherwise, assume it's a stock or CNXBAN which runs on monthly cycles.
    if symbol == "NIFTY":
        return get_next_weekly_expiry()
    elif symbol in MONTHLY_SYMBOLS or len(symbol) >= 5: 
        # Most stocks have long tickers, or explicitly CNXBAN
        return get_month_end_expiry()
    else:
        # Fallback to monthly as it's safer for random stocks
        return get_month_end_expiry()

