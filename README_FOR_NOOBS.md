# 📗 Beginner's Guide: Running NiftyOptionsTrading on Windows

Welcome! This guide is for traders who want to run this powerful dashboard on their Windows laptop but are not "tech-heavy" users. Just follow these steps in order.

---

## 🏗️ Step 1: Install Python (The Engine)
Your laptop needs Python to run the code.
1. Download **Python 3.11, 3.12, or 3.13** from [python.org](https://www.python.org/downloads/windows/).
2. **IMPORTANT**: During installation, check the box that says **"Add Python to PATH"**. If you skip this, the tool won't work!
3. Click "Install Now" and wait for it to finish.

## 📂 Step 2: Download the Code
1. Click the green **Code** button on GitHub and select **Download ZIP**.
2. Extract the ZIP file into a folder on your Desktop (e.g., `C:\Users\YourName\Desktop\NiftyTrading`).

## 🛠️ Step 3: Install Requirements
1. Open the folder where you extracted the code.
2. Click on the address bar at the top of the folder, type `cmd`, and press **Enter**. A black window will open.
3. Type the following command and press Enter:
   ```bash
   pip install -r requirements.txt
   ```
   *Wait for all the colorful bars to finish loading.*

## 🔑 Step 4: Add your API Keys (Choose your Broker)
The tool now supports both **ICICI Breeze** and **Angle One (SmartAPI)**.

1. In the folder, find the file named `.env.example`.
2. Right-click it and choose **Open with Notepad**.
3. Fill in your details:
   - **`BROKER_TYPE`**: Set this to `ICICI_BREEZE` or `ANGLE_ONE`.
   
   **For ICICI Users:**
   - Fill in `API_KEY` and `API_SECRET`.
   - `SESSION_TOKEN`: You still need to update this daily from your Breeze terminal.
   
   **For Angle One Users (Highly Recommended):**
   - Fill in `ANGLE_API_KEY`, `CLIENT_CODE`, and `PASSWORD`.
   - `ANGLE_TOTP_SECRET`: This is the secret key you get when setting up 2FA on the SmartAPI portal.
   - **Benefit**: Angle One logins are **100% automatic**. You don't need to copy-paste tokens every morning!

4. Go to **File > Save As** and save it as exactly `.env` (remove the `.example` part).

## 🚀 Step 5: Start the Dashboard
Now the fun part!
1. Go back to that black window (cmd) or open a new one in the folder.
2. Type:
   ```bash
   python run.py
   ```
3. Open your web browser (Chrome or Edge) and go to:
   **http://127.0.0.1:8001**

---

## 🎯 How to use the Dashboard
- **Sidebar**: Navigate through different tools (V3 Evaluator, BTST, Day Trading).
- **Day Trading Tab**: Select NIFTY, choose an expiry, and click "Analyze".
- **Signal Hub**: Monitor real-time technical signals from your active broker.
- **Trading Mode**: You can toggle between **Paper Trade** (safe testing) and **Live Trading** in the Autonomous Engine tab.

## 🛑 Common Issues for Beginners
- **"Python is not recognized"**: You forgot to check "Add Python to PATH" in Step 1. Uninstall and reinstall Python.
- **ModuleNotFoundError**: Run `pip install -r requirements.txt` again to ensure everything is installed.
- **Session Expired**: 
  - For ICICI: Update your `SESSION_TOKEN` in `.env`.
  - For Angle One: Ensure your `TOTP_SECRET` is correct.

---

*Disclaimer: Algorithmic trading is risky. Start with Paper Trading in the dashboard to understand the signals before using real money.*
