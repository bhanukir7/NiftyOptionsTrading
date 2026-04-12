"""
trade_analyzer.py — F&O Trade Book Analysis Engine
Parses ICICI Direct F&O trade book and generates summarized performance reports
with date filtering and symbol-to-contract drill-down.
"""

import pandas as pd
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

def parse_fno_trade_book(csv_path: str, from_date: Optional[str] = None, to_date: Optional[str] = None) -> Dict:
    """
    Parses the ICICI Direct F&O Trade Book CSV.
    Filters by date range if provided.
    Groups entries by Symbol -> Contract Descriptor.
    """
    if not os.path.exists(csv_path):
        return {"error": f"File not found: {csv_path}"}

    try:
        # 1. Read and Clean CSV
        df = pd.read_csv(csv_path)
        df = df.dropna(subset=['Contract Descriptor'])
        
        # Clean columns and strings
        df.columns = [c.strip() for c in df.columns]
        for col in df.select_dtypes(['object']):
            df[col] = df[col].astype(str).str.strip()

        # Convert numerics
        numeric_cols = ['Qty', 'Price', 'Value', 'Total Charges']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 2. Date Filtering
        # Convert 'Trade Date' (10-Apr-2026) to comparable objects
        df['dt_obj'] = pd.to_datetime(df['Trade Date'], format='%d-%b-%Y', errors='coerce')
        
        if from_date:
            min_dt = pd.to_datetime(from_date)
            df = df[df['dt_obj'] >= min_dt]
        
        if to_date:
            max_dt = pd.to_datetime(to_date)
            df = df[df['dt_obj'] <= max_dt]

        if df.empty:
            return {
                "summary": {"net_pnl": 0, "total_charges": 0, "win_rate": 0, "total_closed_trades": 0, "active_contracts": 0},
                "top_symbols": [], "worst_symbols": [], "recent_trades": [], "message": "No trades found in this date range."
            }

        # 3. Aggregation by Contract Descriptor
        contracts = {}
        for _, row in df.iterrows():
            desc = row['Contract Descriptor']
            if desc not in contracts:
                contracts[desc] = {
                    "symbol": _extract_symbol(desc),
                    "total_buy_val": 0.0,
                    "total_sell_val": 0.0,
                    "total_buy_qty": 0.0,
                    "total_sell_qty": 0.0,
                    "total_charges": 0.0,
                    "last_date": row['Trade Date']
                }
            
            action = str(row['Action']).upper()
            qty    = float(row['Qty'])
            val    = float(row['Value'])
            chgs   = float(row['Total Charges'] if 'Total Charges' in row else 0)
            
            if "BUY" in action:
                contracts[desc]["total_buy_val"] += val
                contracts[desc]["total_buy_qty"] += qty
            elif "SELL" in action:
                contracts[desc]["total_sell_val"] += val
                contracts[desc]["total_sell_qty"] += qty
            
            contracts[desc]["total_charges"] += chgs

        # 4. Symbol Hierarchy and Grouping
        symbol_map = {}
        total_realized_pnl = 0.0
        total_realized_charges = 0.0
        wins = 0
        losses = 0
        active_count = 0
        
        recent_trades = []

        for desc, data in contracts.items():
            is_closed = (data["total_buy_qty"] == data["total_sell_qty"]) and (data["total_buy_qty"] > 0)
            gross_pnl = data["total_sell_val"] - data["total_buy_val"]
            net_pnl   = gross_pnl - data["total_charges"]
            
            trade_item = {
                "contract": desc,
                "net_pnl": round(net_pnl, 2),
                "is_closed": is_closed,
                "date": data["last_date"]
            }
            recent_trades.append({**trade_item, "symbol": data["symbol"]})

            sym = data["symbol"]
            if sym not in symbol_map:
                symbol_map[sym] = {"net_pnl": 0.0, "trades": 0, "contracts": []}
            
            if is_closed:
                symbol_map[sym]["net_pnl"] += net_pnl
                symbol_map[sym]["trades"] += 1
                symbol_map[sym]["contracts"].append(trade_item)
                
                total_realized_pnl += net_pnl
                total_realized_charges += data["total_charges"]
                if net_pnl > 0: wins += 1
                elif net_pnl < 0: losses += 1
            else:
                active_count += 1

        # 5. Split into Profit and Loss symbols (No Overlap)
        profit_symbols = []
        loss_symbols = []
        
        for sym, d in symbol_map.items():
            entry = {"symbol": sym, "net_pnl": round(d["net_pnl"], 2), "trades": d["trades"], "contracts": d["contracts"]}
            if d["net_pnl"] > 0:
                profit_symbols.append(entry)
            elif d["net_pnl"] < 0:
                loss_symbols.append(entry)
        
        profit_symbols = sorted(profit_symbols, key=lambda x: x["net_pnl"], reverse=True)
        loss_symbols = sorted(loss_symbols, key=lambda x: x["net_pnl"]) # Most loss first

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "summary": {
                "net_pnl": round(total_realized_pnl, 2),
                "total_charges": round(total_realized_charges, 2),
                "win_rate": round(win_rate, 1),
                "total_closed_trades": total_trades,
                "active_contracts": active_count
            },
            "top_symbols": profit_symbols[:10],    # Showing more now that it's categorized
            "worst_symbols": loss_symbols[:10],
            "recent_trades": sorted(recent_trades, key=lambda x: _parse_date(x["date"]), reverse=True)[:10]
        }

    except Exception as e:
        return {"error": f"Error parsing CSV: {str(e)}"}

def _extract_symbol(descriptor: str) -> str:
    parts = descriptor.split('-')
    if len(parts) > 1: return parts[1]
    return descriptor

def _parse_date(date_str: str) -> datetime:
    try: return datetime.strptime(date_str, "%d-%b-%Y")
    except: return datetime.min

if __name__ == "__main__":
    test_path = "mytrades/8500524893_FNOTradeBook.csv"
    if os.path.exists(test_path):
        import json
        # Test filtering
        report = parse_fno_trade_book(test_path, from_date="2026-04-10", to_date="2026-04-10")
        print(json.dumps(report, indent=2))
