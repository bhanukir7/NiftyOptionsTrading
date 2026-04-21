**Release Version 1.0** — *April 12, 2026, 02:29 AM IST*
**Release Version 2.0** — *April 12, 2026, 06:49 AM IST*
**Release Version 3.0** — *April 12, 2026, 08:02 AM IST*
**Release Version 4.0** — *April 13, 2026, 01:05 AM IST*
**Release Version 5.0** — *April 13, 2026, 03:10 AM IST*
**Release Version 6.0** — *April 14, 2026, 01:45 AM IST* (The Audit & FIFO Overhaul)
**Release Version 7.0** — *April 21, 2026, 04:20 PM IST* (The Observability Hub)

---

## 📡 Version 7.0: The Observability Hub

This version transforms the trading engine into a transparent, observable state machine, providing deep insights into every algorithmic decision and trade lifecycle event.

### Key 7.0 Features:
*   **📡 Signal Hub Tab**: A new dedicated dashboard tab for real-time strategy observability.
*   **Symbol Monitor Grid**: Card-based view of every symbol in the `.env` watchlist, showing **Live State** (RANGE, BREAKOUT, TREND), **Real-time PnL estimates**, and **Volatility/Bias metrics**.
*   **Structured Signal Stream**: Chronological feed of internal engine events: `BREAKOUT_CONFIRMED`, `ENTRY_CE/PE`, `SCALE_OUT`, `TRAIL_ACTIVE`, and `EXIT`.
*   **Advanced Strategy Engine**: Formalized `advanced_strategy.py` which provides high-fidelity state tracking and alert-driven signals during the autonomous scan loop.
*   **Snapshot Telemetry API**: New FastAPI endpoints for polling engine-level snapshots without triggering high-overhead market data calls.
*   **IST-Synced Signal Logs**: All signals are timestamped with the current session's runtime for precise audit trails during live hours.

---

## 📈 Version 6.0: The Audit & FIFO Overhaul

This version focuses on professional-grade trade auditing and dashboard stability, ensuring accurate PnL calculations regardless of trading complexity.

### Key 6.0 Features:
*   **High-Precision FIFO Engine**: Replaced basic aggregation with a `collections.deque` FIFO matching engine in `trade_analyzer.py`. This ensures 100% accurate Realized PnL and "Cost Basis" tracking for scaling in/out of positions.
*   **Day-Wise Performance Journey**: A new chronological breakdown table in the dashboard showing **Daily Turnover (Buy/Sell Value)**, **Net Daily Realized PnL**, and **EOD Open Cost** (Cumulative Capital Deployed).
*   **Fault-Tolerant Dashboard**: Refactored `app.py` startup to be resilient. The dashboard UI (including the Trade Journal) now remains 100% accessible even if your API session is expired or `SecurityMaster.zip` is temporarily missing.
*   **Live Open Cost Tracking**: Integrated capital allocation metrics across the UI. See exactly how much cost basis is locked in your active "OPEN" symbols and contracts at a glance.
*   **Dashboard Cleanup & Stability**: Removed over 400 lines of duplicated JavaScript logic. Implemented a robust "UI Reset" mechanism that clears stale data upon API failures (404/Empty states), ensuring you never make decisions based on cached results after deleting trade files.
*   **Intelligent Launcher**: Updated `run.py` to support auto-downloading of the Security Master file via the core engine, removing it as a manual setup blocker for new users.
*   **Max Pain Stock Fixes**: Corrected the Max Pain Monitor for equity stocks (**COCSHI**, **VEDLIM**, etc.). It now fetches the actual **NSE Cash Spot Price** via historical API calls instead of guessing from the option chain.
*   **Adaptive Strategy Zone**: The AI Strategy logic now uses **percentage-based noise thresholds**, preventing "Insufficient Data" errors on low-priced stocks while maintaining accuracy for high-priced indices.
*   **OI Change Detection**: Enhanced the snapshot engine to capture real-time **OI Change**, allowing the strategy to detect when institutional walls are unwinding.

---

## 🎯 Version 5.0: The Conviction Engine

This version focuses on high-conviction intraday execution, filtering out market noise using a multi-factor strict validation logic.

### Key 5.0 Features:
*   **Strict Intraday Signal Validator**: (via `strict_validator.py`) A new confluence engine that only triggers signals when **all 5 conditions** (Trend, VWAP Bias, RSI Momentum, Volume Spike, and Pullback) are met.
*   **Confidence Scoring (0-100)**: Real-time weighted scoring for every setup. Trends (25%), VWAP (20%), RSI (20%), Pullback (20%), and Volume (15%).
*   **ToxicJ3ster Day Trading Signals**: Ported the famous Pine Script logic (EMA 9/21 crossovers + Volume confirmations) directly into a dedicated dashboard panel.
*   **Autonomous Engine Upgrade**: Refactored `main.py` and `trading_engine.py` to use the high-conviction strict validator for automated entries, significantly reducing false signals.
*   **Expanded Watchlist**: The engine now tracks an expanded list of high-volume tickers: **NIFTY, CNXBAN, VEDLIM, MAZDOC, RELIND, and COCSHI**.
*   **High-Precision UI**: Added confidence gauges and rule-breakdown badges to the dashboard. Fixed IST clock logic to ensure accurate timezone display regardless of local browser settings.

---

## 📊 Version 4.0: The Professional Audit Suite

This version transforms the dashboard from a real-time monitor into a professional trading audit station, integrating historical performance tracking with global macro precision.

### Key 4.0 Features:
*   **Comprehensive Trade Journal**: (via `trade_analyzer.py`) Automatically ingest ICICI Direct F&O Trade Book CSVs to generate a localized performance audit.
*   **Symbol-Level Drill-down**: Interactive "Folder-style" UI. Click on any symbol (e.g., NIFTY) to see the exact P&L breakdown of every specific strike and expiry traded within that symbol.
*   **Dynamic Date Filtering**: Custom date pickers allow for session-specific or weekly performance reviews, isolating realized P&L across custom timeframes.
*   **Strict Realized P&L Filtering**: Intelligently separates active (open) positions from completed trades to ensure your dashboard totals reflect actual cash-in-hand profit.
*   **GIFT Nifty (NSE IX) Integration**: Real-time tracking of offshore Nifty sentiment added to the Global Macro confluence engine.
*   **Pro Sidebar Navigation**: A complete UI overhaul moving from top-tabs to a modern vertical "side-car" navigation for better ergonomics and more screen real-estate.
*   **NaN-Robust JSON Layer**: New sanitization logic in `global_cues.py` ensures the dashboard remains 100% stable even when specific world indices return incomplete data.

---

## 🤖 Version 3.0: The Autonomous Command Center

The suite has evolved into a fully autonomous trading ecosystem. The background daemon has been unified into the dashboard, providing a "Zero-Click" monitoring and execution experience.

### Key 3.0 Features:
*   **Unified Autonomous Engine**: (via `trading_engine.py`) The background scanner from `main.py` is now a hosted service within the dashboard. Start or stop the engine directly from the UI.
*   **Max Pain OI Strategy**: A buyer-side mean-reversion engine that identifies institutional OI walls (Support/Resistance) and targets Max Pain for high-precision exits.
*   **Live Log Telemetry**: Stream the engine's internal "decision logs" in real-time to the browser without refreshing or checking terminal output.
*   **Paper Trade Toggle**: Integrated safety mode allowing you to run the full autonomous engine for signal verification without risking capital.
*   **High-Frequency OI Scanning**: Aggressive 15-second caching window for option chains, enabling sub-minute reaction to fresh OI concentration changes.
*   **Performance Monitoring**: Real-time tracking of "Trades Today" and "Daily P&L" directly on the central engine dashboard.

---

## ⚡ Version 2.0: The Premium Dashboard

The suite has graduated from CLI-only execution to a unified, interactive **FastAPI Dashboard**. This version focuses on stability, modularity, and a modern web interface.

### Key 2.0 Features:
*   **Unified UI Dashboard**: (via `app.py`) Access every evaluator (V3, BTST, Global) through a single, stunning HSL-themed web interface.
*   **Universal Launcher**: (via `run.py`) One command to start the entire environment with automatic PYTHONPATH management and optimized file watching for Windows.
*   **Interactive Risk Simulator**: A live rule-engine visualizer that allows you to simulate entry conditions, potential slippage, and capital exposure.
*   **Robust Session Isolation**: Relocated API persistence to the `logs/` root directory, preventing recursive reloads and stabilizing developer sessions.
*   **Modular Architecture**: Clean separation between the core "Evaluation Engines" and the "Web Service Layer".
*   **4-Region Global Cues**: Automated sentiment tracking for **Gift Nifty**, **US (S&P/Nasdaq)**, **Europe (DAX/FTSE)**, and **Asia (Nikkei/HangSeng)** via `yfinance`.
*   **Auto-Maintenance**: Automatically creates `/logs` directory and performs daily cleanup of legacy 25MB+ ScripMaster files for disk hygiene.

### Running the V2 Suite:
Always use `run.py` to handle the environment correctly:
- **Dashboard**: `python run.py dash` (Open http://127.0.0.1:8001)
- **BTST CLI**: `python run.py btst "NIFTY 16 Apr 23900 CE"`
- **Global Monitor**: `python run.py global`

---

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

### 4. `evaluate_btst.py` (Probabilistic BTST Decision Engine)
Upgraded from deterministic binary signals to a **0–100 probability-based scoring system** to hunt massive overnight gap-ups using a 1-Day Macro Timeframe.
* **Scoring Logic:** Computes dynamic edge scores scaling across: Price Action (MACD, Bollinger Bands, Closing Strength) [35%], Options Data (PCR, Support Strikes) [25%], Volatility Percentile (ATR-based IV Proxy) [10%], and interactive Global Cues [30%].
* **Output:** Replaces static true/false inputs with quantified edge verdicts (`HIGH PROBABILITY`, `MODERATE EDGE`, etc.) based on overall mathematically calculated confidence.

### 5. `evaluate_global.py` (Global Macro Confluence)
The definitive, flagship analyzer. 
* Executes silent external background calls via `yfinance` to global indices (S&P 500, NASDAQ, Nikkei 225, FTSE 100) before triggering local Indian API scripts.
* **Confluence Logic:** Synchronizes the local Daily BTST gap-up probability with global overnight health.
* Triggers `🔥 EXTREME CONVICTION` when US/Asian markets align with local setups, and throws `⚠️ DIVERGENCE WARNINGS` when global markets crash against your local trades.

### 6. `evaluate_contract_V3.py` (Multi-Strike Evaluator)
The latest UI/UX and analytical upgrade for fast terminal tracking.
* **Input Simplicity:** You no longer type exact strike prices; just feed the underlying symbol, expiry, and Call/Put direction.
* **Multi-Strike Logic:** Automatically locates the ATM strike and evaluates up to 4 closest strikes above and 4 closest strikes below the live spot price simultaneously.

---

## 🆕 v1.0 Universal API Tracking
As part of Release 1.0, the `api_rate_limiter.py` engine now persistently tracks API endpoint usage across *all independent script runs*. State is preserved in a local JSON cache, meaning whether you run `V2`, `V3`, or a background monitor, ICICIdirect quotas are universally protected and synced. All evaluators now explicitly print live API usage logs seamlessly at the end of their reports.

---

## 🛠️ Infrastructure & Network Defenses

In addition to single-contract evaluation, the suite contains active daemons and strict network defenses to track broad portfolios safely.

* `api_rate_limiter.py` & `cache_manager.py`: Protects against ICICIdirect API limits (5000/day, 100/min) using advanced deque tracking and Time-To-Live (TTL) memory caching.
* `safe_breeze.py`: A unified, central wrapper that overrides raw API calls mapping them securely through the caching matrices.
* `market_stream.py`: An asynchronous WebSocket engine hooking actively onto ICICI ticks to update active position tracking locally, eliminating REST API overhead.
* `options_engine.py`: The core wrapper bridging historical dataframe fetching.
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
- `advanced_strategy.py` : **Observable Strategy Provider**. Manages symbol-level state machines (RANGE/TREND) and emits structured signals for the dashboard and alerts.
- `trade_analyzer.py` : **Performance Audit Engine**. Parses ICICI Direct F&O Trade Books with date filtering and symbol-to-contract drill-down hierarchy.
- `evaluate_global.py` : **Global Macro Confluence Evaluator**. Integrates local Indian setups with global US/Asian market sentiment.
- `evaluate_btst.py` : **Probabilistic BTST Engine**. Aggregates Daily Closing Strength, Put-Call Ratio, IV proxy, and Global Cues to compute a 0-100 confidence score for gap-ups.
- `evaluate_contract_V3.py` : **Multi-Strike Evaluator**. Dynamically locates ATM strike and evaluates up to 9 closest active strikes (4 above, 4 below) without requiring explicit strike inputs.
- `evaluate_contract_V2.py` : **Intraday Engine V2**. Employs fixed percentage targets (+5%, +10%) alongside strict -3% momentum traps.
- `evaluate_contract_V1.py` : **Intraday Engine V1**. Utilizes dynamically shifting stop-loss logic generated natively by the Average True Range (ATR).
- `evaluate_contract.py` : **Base Pricing Engine**. Establishes terminal grid-matrices mapping available capital to physical option lots.

### The Background Monitors
- `unified_monitor.py` : **Live Pipeline Monitor**. Orchestrates multiple ticker tracking loops silently in the background.
- `analytics_monitor.py` : **Background Signal Scanner**. Used specifically for scraping continuous data from multi-timeframe analytical models.

### Core Calculation Logic Scripts
- `strict_validator.py` : **Strict Execution Gatekeeper**. Enforces rigid 5-factor discipline (Trend, VWAP, RSI, Volume, Pullback) with weighted confidence scoring.
- `rule_engine.py` : **Risk Management Layer**. Enforces daily loss limits, trade count caps, and trails active stops.
- `options_engine.py` : **Dynamic Sizer & Fetcher**. Downloads dataframes directly from ICICI. Automatically unzips and parses the official SecurityMaster text files daily to calculate exact operational lot sizes.
- `theta_defense.py` : **DTE Protection Script**. Identifies Options contract validity to protect the trader from bleeding Time/Theta decay.
- `max_pain.py` : **Max Pain Calculator**. Extrapolates aggregate Open Interest data to estimate the expiration "pain" threshold for option sellers.
- `expiry_calc.py` : **Time Series Mapper**. Ensures scripts exclusively pull exactly standard valid NSE expiration boundaries.

### Network & API Infrastructure
- `run.py` : **Universal Startup Launcher**. Handles environment bootstrapping, PYTHONPATH resolution, and optimized Uvicorn reload parameters for Windows.
- `safe_breeze.py` : **API Core Wrapper**. Redirects logic to local cache blocks or gracefully queues requests under active ICICIdirect limits.
- `api_rate_limiter.py` : **Persistent Quota Queue**. Algorithmic rate restrictor mapping usage dynamically across runs (via `logs/api_usage.json`).
- `cache_manager.py` : **TTL Memory Cache**. Eliminates redundant polling by statically saving data in local system RAM.
- `market_stream.py` : **WebSocket Integrator**. Circumvents REST API bottlenecks entirely by subscribing to a standard native price stream.

### Web & UI Layer
- `app.py` : **FastAPI Master Server**. The central brain of the Version 2.0 suite. Exposes all analytical modules via a RESTful API.
- `nifty_trading_dashboard.html` : **The Command Center**. A high-performance, responsive UI featuring live world markets, risk simulation, and multi-strike analysis.

### Execution & Alert Framework
- `main.py` : **Controlled Multi-Task Daemon**. The primary scheduled state machine daemon. Batch processes historical indicator refreshes exclusively every 60s.
- `strategy.py` : **Primitive Signal Generator**. Generates the base conditional evaluations for the telegram daemon.
- `alerts.py` : **Telegram Webhooks**. Outbound messaging pipeline to post results live to external Chat IDs.
- `tmp_methods.py` : **Development Sandbox**. Scratchpad files used during primary architecture debugging.

