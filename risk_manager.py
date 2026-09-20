"""Handle margin checks and risk management"""

from typing import Dict
from ib_insync import IB

class RiskManager:
    def __init__(self, ib: IB):
        self.ib = ib
    
    def check_margin_requirements(self, iron_condor: Dict, quantity: int = 1) -> bool:
        """Check if account has sufficient margin for the trade"""
        account_summary = self.ib.accountSummary()
        
        buying_power = 0
        for item in account_summary:
            if item.tag == 'BuyingPower':
                buying_power = float(item.value)
                break
        
        # Calculate margin requirement
        short_put_strike = iron_condor['short_put'][0].strike
        long_put_strike = iron_condor['long_put'][0].strike
        short_call_strike = iron_condor['short_call'][0].strike
        long_call_strike = iron_condor['long_call'][0].strike
        
        put_width = abs(short_put_strike - long_put_strike)
        call_width = abs(short_call_strike - long_call_strike)
        max_width = max(put_width, call_width)
        
        # Margin requirement with 20% buffer
        required_margin = max_width * 100 * quantity * 1.2
        
        return buying_power >= required_margin