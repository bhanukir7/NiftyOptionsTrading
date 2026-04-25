# 🛠️ Scratch Utilities (Debug & Diagnostics)

This folder contains standalone Python scripts used for verifying broker API capabilities, testing connectivity, and debugging data formats outside of the main web application.

### 📋 Usage Instructions
To run any of these scripts, ensure your `.env` file is populated with valid credentials and run:
```powershell
python scratch/<script_name>.py
```

### 🔍 Script Directory

| Script | Purpose |
| :--- | :--- |
| **`test_breeze_iv.py`** | Verifies if ICICI Breeze returns the `implied_volatility` field for a single Nifty option contract. |
| **`test_breeze_chain.py`** | Tests the bulk Option Chain API for Nifty to inspect the full data structure and field keys. |
| **`test_full_iv.py`** | A deep diagnostic tool that prints **all** available data fields for a quote to find hidden Greek or Volatility keys. |
| **`test_sensex_iv.py`** | Validates the correct Symbol/Exchange mapping for BSE Sensex options (BSESEN vs SENSEX). |
| **`check_master.py`** | Utility to verify if scrip master mapping (tokens to symbols) is working correctly for Angle One or Zerodha. |

---
**Note**: These scripts are intended for developer use and can be safely deleted once the main application features are verified.
