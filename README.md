**Release Version 5.1** — *April 28, 2026, 01:25 AM IST* (Data Sovereignty & Quantitative Edge)
**Release Version 5.0** — *April 28, 2026, 12:00 AM IST* (Institutional Strategy & Scalp Lab)
**Release Version 4.1** — *April 27, 2026, 12:00 PM IST* (Scanning Engine Stabilization)
**Release Version 4.0** — *April 26, 2026, 04:45 AM IST* (Morning Trade & Resilience Overhaul)
**Release Version 3.2** — *April 25, 2026, 11:20 PM IST* (The High-Fidelity Greek Refinement)
**Release Version 3.1** — *April 25, 2026, 02:40 PM IST* (The Portfolio Intelligence Overhaul)
**Release Version 2.0** — *April 24, 2026, 05:45 PM IST* (The Multi-Broker & Automation Overhaul)
**Release Version 1.10** — *April 24, 2026, 12:30 PM IST* (The Observability & Efficiency Overhaul)
**Release Version 1.9** — *April 24, 2026, 01:40 AM IST* (The Hedge-Fund Decision Pipeline)
**Release Version 1.8.1** — *April 24, 2026, 01:25 AM IST* (Advanced Signal & Risk Upgrades)
**Release Version 1.8** — *April 24, 2026, 01:15 AM IST* (The Risk & Regime Overhaul)
**Release Version 1.7.2** — *April 23, 2026, 09:55 AM IST* (Session Resilience & Intraday Fixes)
**Release Version 1.7.1** — *April 23, 2026, 02:45 AM IST* (High-Fidelity Signal Refinement)
**Release Version 1.7** — *April 21, 2026, 04:20 PM IST* (The Observability Hub)
**Release Version 1.6** — *April 14, 2026, 01:45 AM IST* (The Audit & FIFO Overhaul)
**Release Version 1.5** — *April 13, 2026, 03:10 AM IST*
**Release Version 1.4** — *April 13, 2026, 01:05 AM IST*
**Release Version 1.3** — *April 12, 2026, 08:02 AM IST*
**Release Version 1.2** — *April 12, 2026, 06:49 AM IST*
**Release Version 1.1** — *April 12, 2026, 02:29 AM IST*
**Release Version 1.0** — *April 10, 2026, 12:00 AM IST* (The Foundation)

## 🚀 Version 5.1: The Data Sovereignty & Quantitative Edge

This release transitions the dashboard into a truly independent quantitative workstation by removing reliance on external websites and implementing professional-grade mathematical solvers.

### Key 5.1 Improvements:
- **🚀 100% Broker-Powered Greeks**: Decommissioned the unreliable NSE website scraper. The **Greeks Strategy Lab** now runs exclusively on official data from your ICICI Breeze / Broker feed, ensuring 100% uptime and no more 403 Forbidden errors.
- **🧠 Iterative IV Solver (Newton-Raphson)**: Implemented a professional-grade quantitative engine that reverse-calculates Implied Volatility (IV) from live market prices. This ensures accurate Delta, Theta, Gamma, and Vega even when exchange-provided IV is missing or stale.
- **⚡ Manual Fetch Control**: Optimized the UI to prevent unnecessary API calls. Data in the **Greeks Lab** and **Scalp Lab** now only fetches when you explicitly click the "Fetch" or "Analyze" buttons, preserving your API rate limits.
- **🎯 Precision Strike Trimming**: Re-engineered the option chain display to focus on what matters. The table now intelligently centers on the **ATM (At-The-Money)** strike and shows exactly 21 strikes (+/- 10 OTM/ITM), eliminating the need for endless scrolling.
- **🛡️ Robust Spot Price Fallback**: Implemented a smart fallback mechanism for after-hours analysis. If the live spot price is unavailable, the system automatically uses the **median strike price** of the option chain as a proxy for Greek calculations.
- **🔧 UI Alignment & Stability**: Fixed critical alignment bugs in the Greeks table and hardened the frontend against null responses, ensuring a seamless experience across all symbols including NIFTY, BANKNIFTY, and SENSEX.
- **💼 Focused Strategy Analysis**: Removed portfolio-level noise from the Strategy Lab. It is now a dedicated environment for "What-If" strategy building and contract-specific risk analysis.

---

## 🚀 Version 5.0: The Institutional Strategy & Scalp Lab

This major release introduces institutional-grade decision tools and professional Greek analysis to the dashboard.

### Key 5.0 Improvements:
- **⚡ Scalp Trade Lab**: A real-time impulsive trade validator for high-speed (5m/10m) scalping. Converts market noise into binary **GO / BLOCK / WAIT** outcomes.
- **🛡️ Hard Block Engine**: Implemented institutional entry filters. Automatically blocks trades near **OI Walls**, exhausted moves (>1.5 ATR), and low-expansion candles.
- **📊 Mandatory Level Engine**: Integrated automated tracking of **Previous Day High/Low** and the **15-minute Opening Range (09:15-09:30)**.
- **🟢 Institutional Green Conditions**: 100% signal alignment required: Breakout + Volume Spike + Momentum Score ≥ 70 + Candle Strength.
- **⚡ Greeks & Strategy Lab**: A professional options terminal featuring live **Delta, Gamma, Theta, and Vega** tracking with NSE-direct fetching and Black-Scholes fallbacks.
- **📈 Portfolio Greeks Aggregator**: Monitor your overall **Net Delta, Gamma, and Theta** across all active positions to manage directional bias and decay risk.
- **🏗️ Strategy Builder Pro**: Analyze and execute complex templates (**Iron Condors, Spreads, Straddles**) with automated P&L projections and regime alignment.
- **⚠️ Expiry Day Risk Panel**: Specialized monitoring for expiry days, providing **Gamma Risk alerts**, **Pin Zone detection**, and adjusted SL/Target recommendations.

---


## 🚀 Version 4.1: The Scanning Engine Stabilization

This minor release focuses on stabilizing the autonomous scanning engine and improving data reliability across the dashboard and Signal Hub.

### Key 4.1 Improvements:
- **⚡ Extended Scanner History**: Upgraded the `AutonomousEngine` to fetch 7 days of 5-minute historical data (instead of just today's), ensuring technical indicators like ATR and EMA are fully calculated even at market open.
- **🛡️ Data Safety Guards**: Implemented a mandatory length check (`len(df) < 50`) in the scanning loop to gracefully skip illiquid or newly listed symbols, preventing "Index Out of Bounds" crashes.
- **📡 Silent yfinance Recovery**: Silenced all `[FALLBACK]` and `[SUCCESS]` logs for `yfinance` calls. These now run as silent background recovery tasks, preventing console spam from affecting the Signal Hub UI performance.
- **📍 Intelligent BSE Fetching**: Optimized the hybrid pipeline to try the primary broker (Breeze) first for all exchanges (including BSE), with a silent failover to `yfinance` only when necessary.
- **📍 Real-Time LTP API**: Added a dedicated `/api/ ltp` endpoint with automated historical fallback to guarantee live spot price visibility in the dashboard simulator, even during broker maintenance or data gaps.
- **🛠️ Service Resilience**: Added missing `timedelta` imports and hardened the `_analyze_symbol` loop against null responses from the broker API.

---

## 🌅 Version 4.0: The Morning Trade & Resilience Overhaul

This major release focuses on high-conviction market-opening execution and system-wide resilience against broker API instability.

### Key 4.0 Improvements:
- **🌅 Morning Trade Panel**: A premium intraday command center implementing **Opening Range Breakout (ORB)** with automated multi-factor confluence (VWAP, EMA, RSI).
- **🔄 Multi-Index Confirmation**: Integrated real-time verification across **NIFTY, BANK NIFTY, and SENSEX**. Directional signals are strictly filtered based on index alignment.
- **📍 Nifty Spot (LTP) Integration**: Guaranteed visibility of the underlying spot price in the Morning Trade Panel by implementing an LTP fallback when VWAP is unavailable (common on weekends).
- **📡 Data Source Transparency**: Added a live source indicator (`Breeze` vs `yfinance`) to the dashboard UI, providing full visibility into the origin of the technical data.
- **🛡️ Hybrid Data Pipeline (yfinance Fallback)**: Implemented an intelligent failover mechanism. The engine now automatically switches to **yfinance** if the broker's historical API is unresponsive, ensuring 100% uptime for index analysis.
- **💼 Advanced Position Tracking**: Refactored the portfolio engine in `SafeBreeze` to support multiple quantity schemas and accurately tag **F&O segments**, fixing visibility issues in the dashboard.
- **📐 Fake Breakout Protection**: Added a second-layer price action filter that rejects "trap" signals if the price fails to sustain beyond the opening range boundaries.
- **🧼 Defensive UI Rendering**: Hardened the entire dashboard with optional chaining and recursive null-sanitization, preventing crashes during weekend maintenance or data gaps.
- **📍 BSE Index Support**: Expanded support for BSE indices with accurate exchange lookups and symbol mapping for SENSEX and BANKEX contracts.

---

## 🎯 Version 3.2: The High-Fidelity Greek Refinement

This release focuses on data precision and high-fidelity synchronization between the broker's real-time quotes and the simulator engine.

### Key 3.2 Improvements:
- **⚡ On-Demand Live IV Sync**: Implemented a dedicated "Fetch Live IV" capability that pulls exact volatility from NSE, replacing simulation baselines with real market data.
- **🎯 Precision Strike Matching**: Hardened the matching logic to handle numeric precision (float vs string) in broker responses, ensuring 100% position synchronization for all OTM/ITM strikes.
- **🔄 Real-Time UI Re-rendering**: Optimized the dashboard to instantly reflect Greek updates and multi-factor PnL changes without requiring manual page refreshes.
- **📍 Smart Spot Calibration**: Automated the simulator's starting spot to the nearest 50-point strike and corrected weekend fallbacks for more accurate "What-If" baseline modeling.
- **🚀 NSE/NFO Optimization**: Prioritized high-speed data fetching for NSE indices, reducing latency during live Greek enrichment calls.

---

## 💼 Version 3.1: The Portfolio Intelligence & PnL Simulation Overhaul

This minor release introduces advanced portfolio observability and a mathematical simulation engine for real-time PnL projections across all brokers.

### Key 3.1 Improvements:
- **💼 Live Positions Dashboard**: Added a unified tab to monitor outstanding positions across all three brokers (**ICICI**, **Angle**, **Zerodha**) with standardized normalization for stocks and options.
- **📈 Advanced PnL Simulator**: Integrated a full **Black-Scholes Greek Engine** that projects "True PnL" by simulating Delta (Price), Vega (IV), and Theta (Time).
- **💥 IV Crush & Theta Modeling**: Dedicated controls to simulate volatility drops and weekend time decay, helping traders visualize the impact of time and volatility on their premiums.
- **📐 Dual-Input Simulator**: Features both a high-precision manual spot entry and a quick-action percentage slider for "What-If" market scenarios.
- **🔄 Smart Position Aggregation**: Automatically consolidates multiple fills and partial trades into clean, net outstanding positions.
- **🌍 Automated Index Scaling**: Intelligent scaling for Sensex (BSESEN) positions, ensuring accurate delta projections relative to Nifty spot movements.
- **⚡ Real-Time LTP Integration**: Added a dedicated backend endpoint for high-frequency index spot fetching to ensure simulator midpoints are always live.

---

## 🚀 Version 3.0: The Zero-Cost & Full Broker Evolution

This milestone version marks the completion of the multi-broker ecosystem, adding native support for Zerodha and perfecting the zero-cost API logic with Angle One.

### Key 3.0 Improvements:
- **🔌 Full Broker Trifecta**: Support for **ICICI Breeze**, **Angle One (SmartAPI)**, and **Zerodha (Kite Connect)**. Switch brokers instantly via `.env` without changing a single line of code.
- **💸 Zerodha (Kite Connect) Native Support**: Integrated the industry-standard Kite API. Features high-precision OHLC data, seamless WebSocket streaming, and robust order execution.
- **📐 Automated Zerodha Session Capture**: Implemented a local redirect listener for Zerodha. The system now automatically opens your browser for login, captures the `request_token`, and exchanges it for a 24-hour `access_token`.
- **🤖 Perfected Zero-Cost Trading**: Native integration for **Angle One** now includes full option chain simulation and metadata lookups (expiries/strikes), enabling a completely free API environment for both indices and stocks.
- **📊 Standardized Metadata Engine**: Unified the way metadata is fetched. Expiries and Strikes for all three brokers are now served through a consistent internal interface, ensuring the dashboard is always synchronized.
- **📦 Full Dependency Overhaul**: Updated core requirements to include `kiteconnect`, `smartapi-python`, and `pyotp` with restored support for `logzero` high-fidelity logging.

---

## 🔌 Version 2.0: The Multi-Broker & Automation Overhaul

This major version transitions the suite from a single-broker tool to a modular, broker-agnostic trading platform, featuring fully automated authentication and support for Angle One (SmartAPI).

### Key 2.0 Improvements:
- **🔌 Broker-Agnostic Architecture**: Introduced a unified `BaseBroker` interface. The entire engine (Signal Hub, Strategies, Risk Engine) is now decoupled from the ICICI Breeze API, allowing for plug-and-play support for any broker.
- **📐 Angle One (SmartAPI) Integration**: Full native support for Angle One. Access live market data, historical candles, and order placement with zero monthly API fees.
- **🤖 100% Silent Authentication**: Implemented TOTP-based automated login for Angle One. The system now generates its own 2FA codes using `pyotp`, enabling truly autonomous "lights-out" operation without manual browser redirects.
- **📊 Unified Data Normalization**: Created a translation layer that standardizes data formats across different brokers. Whether you use ICICI or Angle One, your technical indicators and dashboards receive identical, high-fidelity data.
- **📜 Smart Scrip Mapping**: Integrated an automated Instrument Master downloader for Angle One that maps millions of tokens to human-readable symbols in real-time.
- **🛠️ Windows Environment Stability**: Fixed a critical `uvicorn` argument conflict on Windows and optimized the auto-reload process for better performance during development.
- **📦 Automated Dependency Management**: Added `smartapi-python`, `pyotp`, and `logzero` to the core requirements with automated installation checks during startup.

---

## 🚀 Version 1.10: The Observability & Efficiency Overhaul

This version focuses on operational efficiency, reducing API overhead, and providing full transparency into the autonomous engine's decision-making process.

### Key 1.10 Improvements:
- **⚡ 5-Minute Scan Optimization**: Slowed down the `AutonomousEngine` scanning loop from 1 minute to **5 minutes**. This aligns with 5-minute technical indicators and reduces API call frequency by **80%**, significantly protecting your ICICI Breeze rate limits.
- **📡 Signal Hub Transparency**: Integrated the `AdvancedBreakoutStrategy` into the main engine loop. The **Signal Hub** now provides real-time analysis for all tracked symbols.
- **📝 Descriptive Decision Logs**: Every signal in the hub now includes a detailed **Reason** (e.g., *"Idle - Within Range"* or *"Bullish Setup - Price > Resistance"*), eliminating the "black box" feel of the autonomous engine.
- **📈 ATR-Based IV Proxy**: Implemented a volatility estimation engine in `trading_engine.py` that calculates an **IV Proxy** using 5-minute ATR. This ensures the Signal Hub reflects realistic volatility metrics for all symbols without requiring extra API calls.
- **🛠️ Service Resilience (Windows)**: Added `watchfiles` support for reliable file monitoring on Windows and implemented a **Graceful Shutdown** in `app.py` to prevent WebSocket disconnect errors from crashing the auto-reload process.
- **🚨 Stabilized Telegram Alerts**: Updated the alert system with Markdown escaping to prevent parsing errors (400 Bad Request) caused by underscores in signal types like `NO_TRADE`.

---

## 🧬 Version 1.9: The Hedge-Fund Decision Pipeline

This version transforms the autonomous engine into a structured, hedge-fund style decision pipeline, adding a mandatory validation layer through market regime detection and historical backtesting.

### Key 1.9 Improvements:
- **🏦 Master Orchestrator Pipeline**: Integrated `evaluate_trade_decision` in `trading_engine.py`, enforcing a strict flow: **DATA → REGIME → BIAS → STRATEGY → SCORING → RISK → EXECUTION**.
- **📊 Market Regime Detection**: Implemented a logic gate that classifies the market into **TREND**, **RANGE**, or **NO_TRADE** (Chop > 55 or < 35). Directional trades are strictly blocked in Range regimes.
- **🛡️ Higher Timeframe (HTF) Bias**: Added a mandatory bias alignment check. New trades only trigger if the price and EMAs (21/50) align on the higher timeframe.
- **📈 Adaptive Scoring Engine**: Replaced static validation with regime-aware weighting. Trend-following indicators (MACD) are weighted higher in Trending markets, while Mean-reversion (RSI/BB) is prioritized in Ranges.
- **📐 ATR-Based Expected Move**: Stop-Loss and Target levels are now dynamically calculated based on the **Expected Move** (`ATR / Spot`), ensuring exits are mathematically linked to volatility.
- **💰 Premium-Based Risk Sizing**: Overhauled position sizing to calculate quantity based on the actual option premium and a fixed risk-per-trade percentage.
- **🧪 Backtesting Validation Layer**: A new dedicated `backtester.py` module allows for historical simulation of the decision flow, tracking metrics like **Profit Factor**, **Win Rate**, and **Max Drawdown**.
- **✅ Automated Test Suite (Pytest)**: Integrated a comprehensive suite of **28 automated tests** in the `tests/` directory. This suite validates:
    - **Logic**: Regime detection, scoring weights, and HTF bias alignment.
    - **Risk**: Premium-based sizing, daily profit/loss limits, and partial booking.
    - **Performance**: Profit factor, expectancy, and drawdown stability.
    - **Scenarios**: Full pipeline integration and edge-case resilience.
- **🚦 Final Gate Filters**: Added VIX-based entry blocks, strict time windows (09:30-14:45), and a daily profit circuit breaker to protect capital.

---

## ⚖️ Version 1.8.1: Advanced Signal & Risk Upgrades

This version polishes signal generation with a weighted scoring model and introduces strict ATR-based risk management to prevent over-allocation and improve consistency.

### Key 8.1 Improvements:
*   **⚖️ Weighted Signal Scoring**: Replaced binary entry logic with a 0-100 weighted scoring model. Trades are now classified as **HIGH_CONVICTION** (score ≥ 70) or **MEDIUM** (score ≥ 50), significantly reducing false positives.
*   **🛡️ ATR-Based Dynamic Risk**: Implemented ATR-based Stop Loss (0.5 * ATR) and Target (1.5 * ATR) for premium pricing, ensuring risk levels adapt to current market volatility.
*   **🚧 No Trade Zone Override**: Integrated an automatic override that blocks all signals if the Choppiness Index is between **35 and 45**, avoiding low-probability "chop" entries.
*   **⏰ Late Entry Filter**: New positions are strictly blocked after **14:45 IST** (via `late_entry_cutoff`) to avoid the high-volatility risks of the session close.
*   **📏 Hard Lot Caps**: Enforced a hard limit of **3 lots** (via `max_lots`) per trade, preventing dangerous over-allocation in cheaper OTM options.
*   **🚫 OTM Distance Filter**: Automatically rejects trades where the strike price distance from spot is more than **150 points**, focusing only on high-probability contracts.
*   **📝 Enhanced Audit Logging**: Every trade rejection now logs a specific reason (e.g., "Rejected: No trade zone" or "Rejected: HTF mismatch") to the live activity feed for better transparency.

## 📉 Version 1.8: The Risk & Regime Overhaul

This version introduces strict risk discipline, market regime-aware strategy selection, and corrects critical position sizing logic to stabilize P&L and prevent drawdowns during choppy markets.

### Key 8.0 Improvements:
*   **📉 Market Regime Detection**: Implemented a new detection engine in `trading_engine.py` to identify **RANGE** vs **TREND** regimes. The system now intelligently filters strategies: in RANGE mode, it strictly executes Max Pain mean-reversion and blocks directional breakout signals.
*   **🎯 Partial Profit Booking**: Updated `rule_engine.py` to automatically book **50% quantity at +50% gain** and instantly move the Stop Loss to **Entry Price** (cost-to-cost), ensuring capital protection.
*   **🛡️ Confluence Bias Engine**: Upgraded the bias detection to require dual alignment: **Price > VWAP** AND **EMA 21 > EMA 50** for BULLISH, and vice-versa for BEARISH.
*   **🛑 Forced Intraday Exit**: Integrated a hard safety gate in the core loop that closes all active positions at **15:20 IST** with a "Forced EOD exit" log, eliminating unintended overnight exposure.
*   **💰 Corrected Position Sizing**: Overhauled `calculate_position_size` to use the **actual option premium (LTP)** instead of spot price, ensuring quantity and risk-per-trade are mathematically accurate for options.
*   **🌉 BTST Guardrails**: Refined the BTST evaluator in `app.py`. Overnight carry is now strictly blocked unless the score is **≥ 70** AND global market cues (Gift Nifty, US, Europe) are aligned with the trade direction.
*   **📢 Detailed Rejection Logs**: Every blocked trade now logs its exact reason (e.g., "Blocked due to regime mismatch" or "Blocked due to bias mismatch") for improved audit transparency.

## 🛡️ Version 1.7.2: Session Resilience & Intraday Fixes

This version focuses on operational resilience, fixing a critical bottleneck in the session management flow and restoring full functionality to the Day Trading analysis tab for Indian indices.

### Key 7.2 Improvements:
*   **⌨️ Non-Blocking Session Capture**: Integrated `msvcrt` into `session_manager.py` to enable immediate manual URL entry. You can now press any key in the terminal to paste a redirect URL, bypassing the 5-minute blocking wait for automatic capture.
*   **📈 Index Volume Resolution**: Fixed the "Insufficient clean data" error in `strict_validator.py` and `evaluate_daytrading.py`. The engine now correctly handles indices (NIFTY/BANKNIFTY) by treating missing cash volume as `0.0` instead of dropping the dataset.
*   **🧼 NaN-Proof API Layer**: Implemented a recursive `clean_json_data` utility in `app.py`. This sanitizes all outgoing API responses by replacing `NaN` and `Infinity` with `0.0`, preventing dashboard crashes during high-volatility gaps or early-session warmups.
*   **⚙️ Indicator Buffer Optimization**: Increased the minimum data guard to 30 rows in the strict validator to ensure high-conviction technical indicators like RSI and EMA have sufficient history to generate valid signals.

---

## 🚀 Version 1.7.1: High-Fidelity Signal Refinement

This version polishes the Signal Hub and Global Macro engines, transitioning from placeholder logic to real-time, high-fidelity technical analysis and resilient API fetching.

### Key 7.1 Improvements:
*   **📡 Real-Time Indicator Integration**: Replaced all hardcoded strategy placeholders in `trading_engine.py` with real-time calculations for **ATR**, **MACD**, **Bollinger Bands**, and **Chop Index**.
*   **🌙 24/7 Observability**: Decoupled the scanning loop from market hours. The Signal Hub now provides continuous observability using closing prices and LTP, ensuring the dashboard is never static even after hours.
*   **⚡ Smart Hybrid Fetcher**: Optimized `global_cues.py` to prioritize **Groww** data for Indian indices and only fallback to yfinance for international tickers, eliminating redundant "Quote Not Found" console errors.
*   **🚨 Signal Hub Telegram Alerts**: Fully integrated the `AdvancedBreakoutStrategy` with Telegram. High-conviction signals (`BREAKOUT_CONFIRMED`, `ENTRY`, `EXIT`) now trigger immediate mobile notifications.
*   **🛡️ Fail-Safe Data Pipeline**: Implemented robust field detection for **Implied Volatility (IV)** and dynamic percentage-based Range detection (0.1% threshold) to ensure stability across both indices and small-cap stocks.

---

## 📡 Version 1.7: The Observability Hub

This version transforms the trading engine into a transparent, observable state machine, providing deep insights into every algorithmic decision and trade lifecycle event.

### Key 7.0 Features:
*   **📡 Signal Hub Tab**: A new dedicated dashboard tab for real-time strategy observability.
*   **Symbol Monitor Grid**: Card-based view of every symbol in the `.env` watchlist, showing **Live State** (RANGE, BREAKOUT, TREND), **Real-time PnL estimates**, and **Volatility/Bias metrics**.
*   **Structured Signal Stream**: Chronological feed of internal engine events: `BREAKOUT_CONFIRMED`, `ENTRY_CE/PE`, `SCALE_OUT`, `TRAIL_ACTIVE`, and `EXIT`.
*   **Advanced Strategy Engine**: Formalized `advanced_strategy.py` which provides high-fidelity state tracking and alert-driven signals during the autonomous scan loop.
*   **Snapshot Telemetry API**: New FastAPI endpoints for polling engine-level snapshots without triggering high-overhead market data calls.
*   **IST-Synced Signal Logs**: All signals are timestamped with the current session's runtime for precise audit trails during live hours.

---

## 📈 Version 1.6: The Audit & FIFO Overhaul

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

## 🎯 Version 1.5: The Conviction Engine

This version focuses on high-conviction intraday execution, filtering out market noise using a multi-factor strict validation logic.

### Key 5.0 Features:
*   **Strict Intraday Signal Validator**: (via `strict_validator.py`) A new confluence engine that only triggers signals when **all 5 conditions** (Trend, VWAP Bias, RSI Momentum, Volume Spike, and Pullback) are met.
*   **Confidence Scoring (0-100)**: Real-time weighted scoring for every setup. Trends (25%), VWAP (20%), RSI (20%), Pullback (20%), and Volume (15%).
*   **ToxicJ3ster Day Trading Signals**: Ported the famous Pine Script logic (EMA 9/21 crossovers + Volume confirmations) directly into a dedicated dashboard panel.
*   **Autonomous Engine Upgrade**: Refactored `main.py` and `trading_engine.py` to use the high-conviction strict validator for automated entries, significantly reducing false signals.
*   **Expanded Watchlist**: The engine now tracks an expanded list of high-volume tickers: **NIFTY, CNXBAN, VEDLIM, MAZDOC, RELIND, and COCSHI**.
*   **High-Precision UI**: Added confidence gauges and rule-breakdown badges to the dashboard. Fixed IST clock logic to ensure accurate timezone display regardless of local browser settings.

---

## 📊 Version 1.4: The Professional Audit Suite

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

## 🤖 Version 1.3: The Autonomous Command Center

The suite has evolved into a fully autonomous trading ecosystem. The background daemon has been unified into the dashboard, providing a "Zero-Click" monitoring and execution experience.

### Key 1.3 Improvements:
*   **Unified Autonomous Engine**: (via `trading_engine.py`) The background scanner from `main.py` is now a hosted service within the dashboard. Start or stop the engine directly from the UI.
*   **Max Pain OI Strategy**: A buyer-side mean-reversion engine that identifies institutional OI walls (Support/Resistance) and targets Max Pain for high-precision exits.
*   **Live Log Telemetry**: Stream the engine's internal "decision logs" in real-time to the browser without refreshing or checking terminal output.
*   **Paper Trade Toggle**: Integrated safety mode allowing you to run the full autonomous engine for signal verification without risking capital.
*   **High-Frequency OI Scanning**: Aggressive 15-second caching window for option chains, enabling sub-minute reaction to fresh OI concentration changes.
*   **Performance Monitoring**: Real-time tracking of "Trades Today" and "Daily P&L" directly on the central engine dashboard.

---

## ⚡ Version 1.2: The Premium Dashboard

The suite has graduated from CLI-only execution to a unified, interactive **FastAPI Dashboard**. This version focuses on stability, modularity, and a modern web interface.

### Key 1.2 Improvements:
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

## 🆕 v1.1 Universal API Tracking
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
   Create a `.env` file in the base `NiftyOptionsTrading` directory.
   ```env
   # Options: ICICI_BREEZE, ANGLE_ONE, ZERODHA
   BROKER_TYPE="ICICI_BREEZE"
   
   # ICICI Credentials
   API_KEY="your_key"
   API_SECRET="your_secret"
   SESSION_TOKEN="daily_token"
   
   # Angle One Credentials (Zero Cost API)
   ANGLE_API_KEY="your_key"
   ANGLE_CLIENT_CODE="your_id"
   ANGLE_PASSWORD="your_pin"
   ANGLE_TOTP_SECRET="your_totp_seed"
   
   # Zerodha Credentials
   ZERODHA_API_KEY="your_key"
   ZERODHA_API_SECRET="your_secret"
   
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
- `scalp_engine.py` : **Scalp Trade Lab Engine**. High-speed decision engine with hard blocks, opening range breakouts, and institutional green conditions.
- `nse_greeks_fetcher.py` : **NSE Live Greeks Engine**. Fetches live option chains and calculates Greeks (Delta, Gamma, Theta, Vega) with BS fallback.
- `strategy_builder.py` : **Advanced Strategy Builder**. Analyzes multi-leg templates and projects Max Profit/Loss and regime compatibility.
- `expiry_engine.py` : **Expiry Day Risk Manager**. Monitors Gamma risk, pin zones, and provides adjusted recommendations for expiry day volatility.
- `morning_strategy.py` : **Morning Trade Decision Engine**. Implements ORB logic with Multi-Index confirmation and fake-breakout filters.
- `advanced_strategy.py` : **Observable Strategy Provider**. Manages symbol-level state machines (RANGE/TREND) and emits structured signals for the dashboard and alerts.
- `trade_analyzer.py` : **Performance Audit Engine**. Parses broker-specific F&O Trade Books with date filtering and symbol-to-contract drill-down hierarchy.
- `evaluate_global.py` : **Global Macro Confluence Evaluator**. Integrates local Indian setups with global US/Asian market sentiment.
- `evaluate_btst.py` : **Probabilistic BTST Engine**. Aggregates Daily Closing Strength, Put-Call Ratio, IV proxy, and Global Cues to compute a 0-100 confidence score for gap-ups.
- `evaluate_contract_V3.py` : **Multi-Strike Evaluator**. Dynamically locates ATM strike and evaluates up to 9 closest active strikes (4 above, 4 below) without requiring explicit strike inputs.
- `evaluate_contract_V2.py` : **Intraday Engine V2**. Employs fixed percentage targets (+5%, +10%) alongside strict -3% momentum traps.
- `evaluate_contract_V1.py` : **Intraday Engine V1**. Utilizes dynamically shifting stop-loss logic generated natively by the Average True Range (ATR).
- `evaluate_contract.py` : **Base Pricing Engine**. Establishes terminal grid-matrices mapping available capital to physical option lots.
- `backtester.py` : **Strategy Validation Layer**. Full hedge-fund style backtesting engine with regime segmentation and performance metrics.

### The Background Monitors
- `unified_monitor.py` : **Live Pipeline Monitor**. Orchestrates multiple ticker tracking loops silently in the background.
- `analytics_monitor.py` : **Background Signal Scanner**. Used specifically for scraping continuous data from multi-timeframe analytical models.

### Core Calculation Logic Scripts
- `strict_validator.py` : **Strict Execution Gatekeeper**. Enforces rigid 5-factor discipline (Trend, VWAP, RSI, Volume, Pullback) with weighted confidence scoring.
- `rule_engine.py` : **Risk Management Layer**. Enforces daily loss limits, trade count caps, and trails active stops.
- `options_engine.py` : **Dynamic Sizer & Fetcher**. Fetches market data and historical candles from the active broker. Automatically unzips and parses security master files to calculate exact operational lot sizes.
- `theta_defense.py` : **DTE Protection Script**. Identifies Options contract validity to protect the trader from bleeding Time/Theta decay.
- `max_pain.py` : **Max Pain Calculator**. Extrapolates aggregate Open Interest data to estimate the expiration "pain" threshold for option sellers.
- `expiry_calc.py` : **Time Series Mapper**. Ensures scripts exclusively pull exactly standard valid NSE expiration boundaries.

### Network & API Infrastructure
- `run.py` : **Universal Startup Launcher**. Handles environment bootstrapping, PYTHONPATH resolution, and optimized Uvicorn reload parameters for Windows.
- `broker_interface.py` : **Unified Broker ABC**. Defines the standard interface for all supported brokerage platforms.
- `safe_smartapi.py` : **Angle One Wrapper**. Implements the SmartAPI with automated scrip master mapping and TOTP authentication.
- `safe_kite.py` : **Zerodha Wrapper**. Implements the Kite Connect API with automated session capture and normalized OHLC data.
- `safe_breeze.py` : **ICICI Breeze Wrapper**. Refactored to implement the `BaseBroker` interface while maintaining legacy rate limiting.
- `api_rate_limiter.py` : **Persistent Quota Queue**. Algorithmic rate restrictor mapping usage dynamically across runs (via `logs/api_usage.json`).
- `cache_manager.py` : **TTL Memory Cache**. Eliminates redundant polling by statically saving data in local system RAM.
- `market_stream.py` : **Unified WebSocket Integrator**. Broker-agnostic price stream handling for real-time dashboard updates.

### Web & UI Layer
- `app.py` : **FastAPI Master Server**. The central brain of the Version 2.0 ecosystem. Exposes all analytical modules and multi-broker services via a RESTful API.
- `nifty_trading_dashboard.html` : **The Command Center**. A high-performance, responsive UI featuring live world markets, risk simulation, and multi-strike analysis.

### Execution & Alert Framework
- `main.py` : **Controlled Multi-Task Daemon**. The primary scheduled state machine daemon. Batch processes historical indicator refreshes exclusively every 60s.
- `strategy.py` : **Primitive Signal Generator**. Generates the base conditional evaluations for the telegram daemon.
- `alerts.py` : **Telegram Webhooks**. Outbound messaging pipeline to post results live to external Chat IDs.
- `tmp_methods.py` : **Development Sandbox**. Scratchpad files used during primary architecture debugging.

