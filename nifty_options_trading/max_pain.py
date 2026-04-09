"""
Max Pain Theory Calculator
Determines the optimal strike price where option sellers experience minimum financial loss.

Author: Aditya Kota
"""
import pandas as pd

def calculate_max_pain(chain_df: pd.DataFrame) -> float:
    """
    Calculates the Max Pain strike price from an Option Chain DataFrame.
    
    Parameters:
        chain_df: DataFrame containing at least 'strike_price', 'right', and 'open_interest'
        
    Returns:
        The strike price representing the Max Pain point.
    """
    if chain_df is None or chain_df.empty:
        return 0.0
        
    try:
        # Filter vital columns and drop NAs
        df = chain_df[['strike_price', 'right', 'open_interest']].dropna()
        
        # Make right lowercase to handle Call/Put or CE/PE variations
        df['right'] = df['right'].str.lower()
        
        strikes = sorted(df['strike_price'].unique())
        
        pain_values = {}
        
        for presumed_expiry in strikes:
            total_pain = 0.0
            
            for _, row in df.iterrows():
                strike = row['strike_price']
                oi = row['open_interest']
                opt_type = row['right']
                
                # Expiry pain = Intrinsic value at expiration * Open Interest
                if opt_type in ['call', 'ce']:
                    # Call buyer makes money if expiry > strike
                    loss_for_seller = max(0, presumed_expiry - strike) * oi
                    total_pain += loss_for_seller
                elif opt_type in ['put', 'pe']:
                    # Put buyer makes money if expiry < strike
                    loss_for_seller = max(0, strike - presumed_expiry) * oi
                    total_pain += loss_for_seller
                    
            pain_values[presumed_expiry] = total_pain
            
        # The Max Pain point is the strike price where option sellers lose the least amount of money
        max_pain_strike = min(pain_values, key=pain_values.get)
        
        return max_pain_strike
        
    except Exception as e:
        print(f"Error calculating Max Pain: {e}")
        return 0.0
