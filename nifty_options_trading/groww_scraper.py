"""
groww_scraper.py — Real-time Index Scraper for Groww.in
Fetches high-fidelity market data including GIFT NIFTY and India VIX.

Author: Aditya Kota
"""
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# URLs
GLOBAL_URL = "https://groww.in/indices/global-indices"
INDIAN_URL = "https://groww.in/indices/indian-indices"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}

def clean_value(text: str) -> float:
    """Removes commas and currency symbols, returns float."""
    try:
        # Extract digits, dots and minus sign
        cleaned = re.sub(r'[^\d\.\-]', '', text)
        return float(cleaned)
    except:
        return 0.0

def parse_groww_page(url: str) -> list:
    """Scrapes a Groww indices page and returns a list of dictionaries."""
    results = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3:
                continue
            
            # Name in first column
            name_tag = cols[0].find('span', class_='bodyBaseHeavy')
            if not name_tag:
                continue
            name = name_tag.text.strip()
            
            # Price in second column
            price_text = cols[1].text.strip()
            price = clean_value(price_text)
            
            # Change in third column (format: "diff (pct%)")
            change_div = cols[2].find('div')
            change_pct = 0.0
            if change_div:
                change_text = change_div.text.strip()
                # Use regex to find the percentage inside parentheses
                match = re.search(r'\(([\d\.\-]+)%\)', change_text)
                if match:
                    change_pct = float(match.group(1))
                    # Check if the overall change text implies a negative move
                    if '-' in change_text and change_pct > 0:
                        change_pct = -change_pct
            
            results.append({
                "name": name,
                "last": price,
                "change_pct": change_pct,
                "timestamp": datetime.now().isoformat()
            })
    except Exception as e:
        print(f"[groww_scraper] Error scraping {url}: {e}")
        
    return results

def fetch_groww_indices() -> dict:
    """Fetches and combines data from Global and Indian pages."""
    all_data = {}
    
    # Fetch both
    global_indices = parse_groww_page(GLOBAL_URL)
    indian_indices = parse_groww_page(INDIAN_URL)
    
    combined = global_indices + indian_indices
    
    # Map to standard names used in our app (WORLD_INDICES keys in global_cues.py)
    name_mapping = {
        "GIFT NIFTY": "GIFT NIFTY (NSE IX Proxy)",
        "NIFTY 50": "NIFTY 50",
        "NIFTY BANK": "BANK NIFTY",
        "BANK NIFTY": "BANK NIFTY",
        "NIFTY FINANCIAL SERVICES": "FIN NIFTY",
        "FINNIFTY": "FIN NIFTY",
        "SENSEX": "SENSEX",
        "BSE SENSEX": "SENSEX",
        "BSE BANKEX": "SENSEX BANK",
        "SENSEX BANK": "SENSEX BANK",
        "INDIA VIX": "INDIA VIX",
        "S&P 500": "S&P 500",
        "S&P": "S&P 500",
        "NASDAQ": "NASDAQ",
        "US TECH 100": "NASDAQ",
        "DOW": "Dow Jones",
        "DOW JONES": "Dow Jones",
        "FTSE 100": "FTSE 100",
        "FTSE": "FTSE 100",
        "NIKKEI 225": "Nikkei 225",
        "NIKKEI": "Nikkei 225",
        "HANG SENG": "Hang Seng",
        "DAX": "DAX",
        "CAC 40": "CAC 40",
        "CAC": "CAC 40",
        "EURO STOXX 50": "Euro Stoxx 50",
        "STOXX 50": "Euro Stoxx 50",
        "SMI": "SMI (Switzerland)",
        "KOSPI": "Kospi",
        "STI": "STI (Singapore)",
        "SHANGHAI": "Shanghai",
        "TAIWAN (TWII)": "Taiwan (TWII)",
        "ASX 200": "ASX 200",
    }
    
    final_list = []
    for item in combined:
        std_name = name_mapping.get(item["name"].upper(), item["name"])
        # Avoid duplicates if any
        if std_name not in all_data:
            item["std_name"] = std_name
            all_data[std_name] = item
            final_list.append(item)
            
    return {
        "markets": final_list,
        "timestamp": datetime.now().isoformat(),
        "source": "Groww"
    }

if __name__ == "__main__":
    # Standalone test
    print("Testing Groww Scraper...")
    data = fetch_groww_indices()
    for m in data["markets"]:
        print(f"{m['std_name']:<20} | {m['last']:>10.2f} | {m['change_pct']:>6.2f}%")
