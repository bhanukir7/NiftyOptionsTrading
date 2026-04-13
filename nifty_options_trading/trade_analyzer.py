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

        # 3. FIFO Aggregation by Contract Descriptor
        from collections import deque
        from collections import defaultdict
        
        # We track state per contract
        queues = {} 
        realized_pnl = {}
        total_charges = {}
        contract_info = {} # symbol, last_date
        
        # Daily Performance Tracking
        daily_map = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "pnl": 0.0, "charges": 0.0, "open_cost_eod": 0.0})
        running_open_cost = 0.0
        
        for _, row in df.iterrows():
            desc = row['Contract Descriptor']
            dt_str = row['Trade Date']
            
            if desc not in queues:
                queues[desc] = deque()
                realized_pnl[desc] = 0.0
                total_charges[desc] = 0.0
                contract_info[desc] = {
                    "symbol": _extract_symbol(desc),
                    "last_date": dt_str
                }
            
            action = str(row['Action']).upper()
            qty    = float(row['Qty'])
            price  = float(row['Price'])
            val    = float(row['Value'])
            chgs   = float(row['Total Charges'] if 'Total Charges' in row else 0)
            
            total_charges[desc] += chgs
            daily_map[dt_str]["charges"] += chgs
            
            if "BUY" in action:
                daily_map[dt_str]["buy"] += val
                running_open_cost += val
                
                # If we have short positions (negative qty in queue), cover them first
                remaining_buy = qty
                while remaining_buy > 0 and queues[desc] and queues[desc][0][0] < 0:
                    oldest_short = queues[desc][0]
                    short_qty = abs(oldest_short[0])
                    match_qty = min(remaining_buy, short_qty)
                    
                    # PnL for short: (Sell Price [oldest_short[1]] - Buy Price [price]) * match_qty
                    trade_pnl = match_qty * (oldest_short[1] - price)
                    realized_pnl[desc] += trade_pnl
                    daily_map[dt_str]["pnl"] += trade_pnl
                    
                    remaining_buy -= match_qty
                    oldest_short[0] += match_qty
                    if oldest_short[0] >= 0:
                        queues[desc].popleft()
                
                if remaining_buy > 0:
                    queues[desc].append([remaining_buy, price])
                
                # Update running open cost specifically for Long positions
                temp_cost = 0
                for d_desc in queues:
                    temp_cost += sum(item[0] * item[1] for item in queues[d_desc] if item[0] > 0)
                running_open_cost = temp_cost

            elif "SELL" in action:
                daily_map[dt_str]["sell"] += val
                
                # If we have long positions (positive qty in queue), close them first
                remaining_sell = qty
                while remaining_sell > 0 and queues[desc] and queues[desc][0][0] > 0:
                    oldest_long = queues[desc][0]
                    match_qty = min(remaining_sell, oldest_long[0])
                    
                    # PnL for long: (Sell Price [price] - Buy Price [oldest_long[1]]) * match_qty
                    trade_pnl = match_qty * (price - oldest_long[1])
                    realized_pnl[desc] += trade_pnl
                    daily_map[dt_str]["pnl"] += trade_pnl
                    
                    remaining_sell -= match_qty
                    oldest_long[0] -= match_qty
                    if oldest_long[0] <= 0:
                        queues[desc].popleft()
                
                if remaining_sell > 0:
                    queues[desc].append([-remaining_sell, price])
                
                # Recalculate deployed capital
                temp_cost = 0
                for d_desc in queues:
                    temp_cost += sum(item[0] * item[1] for item in queues[d_desc] if item[0] > 0)
                running_open_cost = temp_cost

            daily_map[dt_str]["open_cost_eod"] = running_open_cost

        # 4. Symbol Hierarchy and Grouping
        symbol_map = {}
        total_pnl_accumulator = 0.0
        total_charges_accumulator = 0.0
        wins = 0
        losses = 0
        active_count = 0
        
        recent_trades = []

        for desc, queue in queues.items():
            info = contract_info[desc]
            
            open_qty = sum(item[0] for item in queue)
            open_cost = sum(item[0] * item[1] for item in queue if item[0] > 0) # Only positive qty has "cost"
            
            is_closed = (abs(open_qty) < 1e-5) # Account for float precision
            net_pnl = realized_pnl[desc] - total_charges[desc]
            
            trade_item = {
                "contract": desc,
                "net_pnl": round(net_pnl, 2),
                "is_closed": is_closed,
                "date": info["last_date"],
                "open_qty": round(open_qty, 2),
                "open_cost": round(open_cost, 2)
            }
            recent_trades.append({**trade_item, "symbol": info["symbol"]})

            sym = info["symbol"]
            if sym not in symbol_map:
                symbol_map[sym] = {"net_pnl": 0.0, "trades": 0, "contracts": [], "open_cost": 0.0}
            
            symbol_map[sym]["open_cost"] += open_cost
            
            if is_closed:
                symbol_map[sym]["net_pnl"] += net_pnl
                symbol_map[sym]["trades"] += 1
                symbol_map[sym]["contracts"].append(trade_item)
                
                total_pnl_accumulator += net_pnl
                total_charges_accumulator += total_charges[desc]
                if net_pnl > 0: wins += 1
                elif net_pnl < 0: losses += 1
            else:
                active_count += 1
                # Even for open positions, we show them in the symbol drill-down
                symbol_map[sym]["contracts"].append(trade_item)

        # 5. Split into Profit and Loss symbols
        profit_symbols = []
        loss_symbols = []
        
        for sym, d in symbol_map.items():
            entry = {
                "symbol": sym, 
                "net_pnl": round(d["net_pnl"], 2), 
                "trades": d["trades"], 
                "contracts": d["contracts"],
                "open_cost": round(d["open_cost"], 2)
            }
            if d["net_pnl"] >= 0:
                profit_symbols.append(entry)
            else:
                loss_symbols.append(entry)
        
        profit_symbols = sorted(profit_symbols, key=lambda x: x["net_pnl"], reverse=True)
        loss_symbols = sorted(loss_symbols, key=lambda x: x["net_pnl"]) 

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        # 6. Prepare Daily Performance List
        daily_perf = []
        for dt, stats in daily_map.items():
            daily_perf.append({
                "date": dt,
                "buy": round(stats["buy"], 2),
                "sell": round(stats["sell"], 2),
                "trade_value": round(stats["buy"] + stats["sell"], 2),
                "net_pnl": round(stats["pnl"] - stats["charges"], 2),
                "open_cost": round(stats["open_cost_eod"], 2)
            })
        daily_perf = sorted(daily_perf, key=lambda x: _parse_date(x["date"]), reverse=True)

        return {
            "summary": {
                "net_pnl": round(total_pnl_accumulator, 2),
                "total_charges": round(total_charges_accumulator, 2),
                "win_rate": round(win_rate, 1),
                "total_closed_trades": total_trades,
                "active_contracts": active_count,
                "total_open_cost": round(sum(d["open_cost"] for d in symbol_map.values()), 2)
            },
            "top_symbols": profit_symbols[:20],
            "worst_symbols": loss_symbols[:20],
            "recent_trades": sorted(recent_trades, key=lambda x: _parse_date(x["date"]), reverse=True)[:20],
            "daily_performance": daily_perf
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
