# nifty_options_trading 🚀

An advanced, automated algorithmic options trading, evaluation, and monitoring suite built natively for Indian Equities and Indices using the **ICICIdirect Breeze API**.

This repository documents the chronological evolution of a professional-grade options evaluation engine—growing from a basic intraday strike pricer to a highly sophisticated multi-timeframe Global Macro Confluence Algorithm.

> **Disclaimer:** This software is for **educational and analytical purposes only**. Algorithmic options trading involves substantial risk of capital loss. Do not trade using production capital without thoroughly verifying the signals. The authors are not responsible for any financial losses incurred.

---

## 🧬 The Chronological Evolution

nifty_options_trading was developed iteratively. Each version solves a distinct trading challenge, moving from purely intraday momentum to gap-up End-Of-Day predictions and Global Macro integrations.

### 1. `evaluate_contract.py` (The Foundation)
The base engine. It connects to the Live ICICI Breeze Option Chains and fetches active premiums, evaluating basic contract affordability based on dynamic `AVAILABLE_FUNDS` limitations mapped cleanly to current lot sizes.

### 2. `evaluate_contract_V1.py` (Dynamic Intraday Volatility)
The first algorithmic upgrade. Transitioned to a 5-minute Intraday Timeframe logic.
* **Core Indicators:** MACD Crosses, Bollinger Bands, Average True Range (ATR), and the Choppiness Index (CHOP).
* **Risk Model:** Dynamic Volatility Targeting. Uses Option ATR to dynamically shift stop-losses and targets based on real-time premium chaos.

### 3. `evaluate_contract_V2.py` (The Fixed Sniper)
A strict risk-adjusted pivot from V1.
* Calculates identical 5-minute underlying technicals but completely overhauls the profit taking mechanism.
* **Risk Model:** Fixed Percentage System. Strictly enforces predefined percentage levels: Target 1 (+5%), Target 2 (+10%), and a hard Stop-Loss (-3%).

### 4. `evaluate_btst.py` (End-of-Day EOD Gap-Ups)
Transitioned the engine from 5-minute lagging indicators to a **1-Day Macro Timeframe** specifically to hunt massive overnight gap-ups.
* **Core Logic:** Focuses intensely on Daily Closing Strength. If a stock closes near its absolute daily peak (e.g. >85% of its daily range) above its 20-Day SMA with Bullish MACD, it triggers a `🟩 HIGH CONVICTION BTST`.
* Designed to prevent "lagging indicator traps" where 5-min intraday profit-booking overrides strong daily multi-day recovery momentum.

### 5. `evaluate_global.py` (Global Macro Confluence)
The definitive, flagship analyzer. 
* Executes silent external background calls via `yfinance` to global indices (S&P 500, NASDAQ, Nikkei 225, FTSE 100) before triggering local Indian API scripts.
* **Confluence Logic:** Synchronizes the local Daily BTST gap-up probability with global overnight health.
* Triggers `🔥 EXTREME CONVICTION` when US/Asian markets align with local setups, and throws `⚠️ DIVERGENCE WARNINGS` when global markets crash against your local trades.

---

## 🛠️ Infrastructure & Monitors

In addition to single-contract evaluation, the suite contains active daemons to track broad portfolios.

* `options_engine.py`: The core wrapper bridging authentication and dataframe fetching to ICICI Breeze.
* `max_pain.py`: Calculates Max Pain theory limits across active option chains.
* `theta_defense.py`: Analyzes DTE (Days to Expiry) decay curves to prevent buying heavily decaying premium.
* `analytics_monitor.py` & `unified_monitor.py`: Persistent, unified dashboard monitors tracking multiple underlying contracts simultaneously via asynchronous API streaming.

---

## ⚙️ Installation & Setup

1. **Clone the Directory:** Ensure `nifty_options_trading` is the active working directory.
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Environment Setup (`.env`):**
   Create a `.env` file in the base `NiftyOptionsTrading` directory and provide your live ICICI API credentials.
   ```env
   API_KEY="your_icici_api_key_here"
   API_SECRET="your_icici_secret_here"
   SESSION_TOKEN="daily_regenerated_breeze_token_here"
   AVAILABLE_FUNDS="50000"
   ```
4. **Telegram Alert Setup (Optional, for Live Notifications):**
   To utilize `main.py` and receive live automated alert broadcasts on your phone, you must map your Telegram bot configurations in `.env`.
   
   **How to create a Telegram Bot (For Novices):**
   - **Step A:** Open the Telegram App and search for the verified contact `@BotFather`.
   - **Step B:** Send the message `/newbot` and follow the prompts to name your bot. 
   - **Step C:** Once created, BotFather will give you a long **API Token**. Copy this string and paste it into your `.env` file as `TELEGRAM_BOT_TOKEN`.
   - **Step D:** Now, search for `@userinfobot` on Telegram and send it a message. It will reply with your personal **Id number** (e.g., `123456789`). Paste this into your `.env` file as `TELEGRAM_CHAT_ID`.
   
   Your `.env` should now look like this:
   ```env
   TELEGRAM_BOT_TOKEN="1234567890:AAH...your_long_token_here"
   TELEGRAM_CHAT_ID="123456789"
   ```
   **Validation:** You can verify that your bot is properly communicating with your phone by executing the alerts module directly:
   ```powershell
   python nifty_options_trading/alerts.py
   ```
   *(If successful, your new bot will instantly ping your phone with a test notification).*

## 🚀 Usage

All evaluators accept string-based contract descriptors directly from the command line.

**Example: Evaluating a Global Confluence setup for NIFTY call options:**
```powershell
python nifty_options_trading/evaluate_global.py "NIFTY 16 Apr 23900 CE"
```

**Example: Tracking an Intraday Scalp on HAL:**
```powershell
python nifty_options_trading/evaluate_contract_V2.py "HINAER 28 Apr 4600 CE"
```


---

## 📁 Complete File Manifest

A detailed index of exactly what every Python file does within the `nifty_options_trading/` package:

### The Evaluator Engines
- `evaluate_global.py` : **Global Macro Confluence Evaluator**. Integrates local Indian setups with global US/Asian market sentiment to generate macro-overnight convictions.
- `evaluate_btst.py` : **End-Of-Day BTST Engine**. Focuses strictly on the physical footprint of the 1-Day closing strength to project opening gap-ups.
- `evaluate_contract_V2.py` : **Intraday Engine V2**. Employs fixed percentage targets (+5%, +10%) alongside strict -3% momentum traps.
- `evaluate_contract_V1.py` : **Intraday Engine V1**. Utilizes dynamically shifting stop-loss logic generated natively by the Average True Range (ATR).
- `evaluate_contract.py` : **Base Pricing Engine**. Establishes terminal grid-matrices mapping available capital to physical option lots.

### The Background Monitors
- `unified_monitor.py` : **Live Pipeline Monitor**. Orchestrates multiple ticker tracking loops silently in the background.
- `analytics_monitor.py` : **Background Signal Scanner**. Used specifically for scraping continuous data from multi-timeframe analytical models.

### Core Calculation Logic Scripts
- `rule_engine.py` : **Strict Execution Gatekeeper**. Enforces rigid discipline, time limits, position sizing, risk capital mapping, and trails active stops.
- `options_engine.py` : **Breeze API Communicator & Dynamic Sizer**. Downloads dataframes directly from ICICI. Automatically unzips and parses the official SecurityMaster text files daily to calculate exact operational lot sizes.
- `theta_defense.py` : **DTE Protection Script**. Identifies Options contract validity to protect the trader from bleeding Time/Theta decay.
- `max_pain.py` : **Max Pain Calculator**. Extrapolates aggregate Open Interest data to estimate the expiration "pain" threshold for option sellers.
- `expiry_calc.py` : **Time Series Mapper**. Ensures scripts exclusively pull exactly standard valid NSE expiration boundaries.

### Execution & Alert Framework
- `main.py` : **Controlled Trading Engine**. The primary State Machine daemon. Scans technical indicators, calculates VWAP biases, filters logic via the `rule_engine`, executes managed trade entries, and harvests partial profits automatically.
- `strategy.py` : **Primitive Signal Generator**. Generates the base conditional evaluations for the telegram daemon.
- `alerts.py` : **Telegram Webhooks**. Outbound messaging pipeline to post results live to external Chat IDs.
- `tmp_methods.py` : **Development Sandbox**. Scratchpad files used during primary architecture debugging.

