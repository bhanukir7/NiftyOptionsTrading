from nifty_options_trading.nse_greeks_fetcher import NSEGreeksFetcher

class StrategyBuilder:
    def __init__(self):
        self.fetcher = NSEGreeksFetcher()

    def _get_chain(self, symbol):
        chain = self.fetcher.fetch_option_chain(symbol)
        if "error" in chain:
            return None
        return chain

    def _find_strike(self, strikes, target_price):
        """Finds the closest strike price in the chain."""
        return min(strikes, key=lambda x: abs(x["strikePrice"] - target_price))

    def _create_leg(self, strike_data, opt_type, side):
        leg_info = strike_data[opt_type]
        mult = 1 if side == "BUY" else -1
        return {
            "strike": strike_data["strikePrice"],
            "type": opt_type,
            "side": side,
            "premium": leg_info["lastPrice"],
            "delta": leg_info["delta"],
            "gamma": leg_info["gamma"],
            "theta": leg_info["theta"],
            "vega": leg_info["vega"],
            "net_delta": round(leg_info["delta"] * mult, 4),
            "net_gamma": round(leg_info["gamma"] * mult, 6),
            "net_theta": round(leg_info["theta"] * mult, 4),
            "net_vega": round(leg_info["vega"] * mult, 4)
        }

    def _calculate_summary(self, legs, spot, ideal_regime):
        net_premium = sum(leg["premium"] * (1 if leg["side"] == "SELL" else -1) for leg in legs)
        net_greeks = {
            "delta": round(sum(leg["net_delta"] for leg in legs), 4),
            "gamma": round(sum(leg["net_gamma"] for leg in legs), 6),
            "theta": round(sum(leg["net_theta"] for leg in legs), 4),
            "vega": round(sum(leg["net_vega"] for leg in legs), 4)
        }
        
        # Max Profit/Loss and Breakevens logic varies by strategy
        # This is a generic placeholder that will be overridden by specific strategy methods
        return {
            "legs": legs,
            "net_premium": round(net_premium, 2),
            "net_greeks": net_greeks,
            "ideal_regime": ideal_regime
        }

    def bull_call_spread(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        atm = self._find_strike(chain["strikes"], spot)
        otm = self._find_strike(chain["strikes"], spot + 100)
        
        legs = [
            self._create_leg(atm, "CE", "BUY"),
            self._create_leg(otm, "CE", "SELL")
        ]
        
        summary = self._calculate_summary(legs, spot, "BULLISH")
        net_debit = -summary["net_premium"]
        width = otm["strikePrice"] - atm["strikePrice"]
        
        summary.update({
            "max_profit": round(width - net_debit, 2),
            "max_loss": round(net_debit, 2),
            "breakeven_upper": round(atm["strikePrice"] + net_debit, 2),
            "breakeven_lower": None
        })
        return summary

    def bear_put_spread(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        atm = self._find_strike(chain["strikes"], spot)
        otm = self._find_strike(chain["strikes"], spot - 100)
        
        legs = [
            self._create_leg(atm, "PE", "BUY"),
            self._create_leg(otm, "PE", "SELL")
        ]
        
        summary = self._calculate_summary(legs, spot, "BEARISH")
        net_debit = -summary["net_premium"]
        width = atm["strikePrice"] - otm["strikePrice"]
        
        summary.update({
            "max_profit": round(width - net_debit, 2),
            "max_loss": round(net_debit, 2),
            "breakeven_upper": None,
            "breakeven_lower": round(atm["strikePrice"] - net_debit, 2)
        })
        return summary

    def long_straddle(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        atm = self._find_strike(chain["strikes"], spot)
        
        legs = [
            self._create_leg(atm, "CE", "BUY"),
            self._create_leg(atm, "PE", "BUY")
        ]
        
        summary = self._calculate_summary(legs, spot, "HIGH VOLATILITY")
        net_debit = -summary["net_premium"]
        
        summary.update({
            "max_profit": "UNLIMITED",
            "max_loss": round(net_debit, 2),
            "breakeven_upper": round(atm["strikePrice"] + net_debit, 2),
            "breakeven_lower": round(atm["strikePrice"] - net_debit, 2)
        })
        return summary

    def short_straddle(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        atm = self._find_strike(chain["strikes"], spot)
        
        legs = [
            self._create_leg(atm, "CE", "SELL"),
            self._create_leg(atm, "PE", "SELL")
        ]
        
        summary = self._calculate_summary(legs, spot, "RANGE BOUND")
        net_credit = summary["net_premium"]
        
        summary.update({
            "max_profit": round(net_credit, 2),
            "max_loss": "UNLIMITED",
            "breakeven_upper": round(atm["strikePrice"] + net_credit, 2),
            "breakeven_lower": round(atm["strikePrice"] - net_credit, 2)
        })
        return summary

    def iron_condor(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        ce_sell = self._find_strike(chain["strikes"], spot + 100)
        ce_buy  = self._find_strike(chain["strikes"], spot + 200)
        pe_sell = self._find_strike(chain["strikes"], spot - 100)
        pe_buy  = self._find_strike(chain["strikes"], spot - 200)
        
        legs = [
            self._create_leg(ce_sell, "CE", "SELL"),
            self._create_leg(ce_buy,  "CE", "BUY"),
            self._create_leg(pe_sell, "PE", "SELL"),
            self._create_leg(pe_buy,  "PE", "BUY")
        ]
        
        summary = self._calculate_summary(legs, spot, "RANGE BOUND")
        net_credit = summary["net_premium"]
        width = ce_buy["strikePrice"] - ce_sell["strikePrice"]
        
        summary.update({
            "max_profit": round(net_credit, 2),
            "max_loss": round(width - net_credit, 2),
            "breakeven_upper": round(ce_sell["strikePrice"] + net_credit, 2),
            "breakeven_lower": round(pe_sell["strikePrice"] - net_credit, 2)
        })
        return summary

    def long_strangle(self, spot, expiry, symbol):
        chain = self._get_chain(symbol)
        if not chain: return {"error": "Chain unavailable"}
        
        ce_buy = self._find_strike(chain["strikes"], spot + 100)
        pe_buy = self._find_strike(chain["strikes"], spot - 100)
        
        legs = [
            self._create_leg(ce_buy, "CE", "BUY"),
            self._create_leg(pe_buy, "PE", "BUY")
        ]
        
        summary = self._calculate_summary(legs, spot, "HIGH VOLATILITY")
        net_debit = -summary["net_premium"]
        
        summary.update({
            "max_profit": "UNLIMITED",
            "max_loss": round(net_debit, 2),
            "breakeven_upper": round(ce_buy["strikePrice"] + net_debit, 2),
            "breakeven_lower": round(pe_buy["strikePrice"] - net_debit, 2)
        })
        return summary
