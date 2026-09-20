"""Analyze and find Iron Condor legs"""

from typing import Dict, Optional, Tuple
from ib_insync import Contract

class StrategyAnalyzer:
    def __init__(self, target_delta: float = 0.10, tolerance: float = 0.05):
        self.target_delta = target_delta
        self.tolerance = tolerance
    
    def find_iron_condor_legs(self, option_data: Dict[Contract, Dict], spy_price: float) -> Optional[Dict]:
        """Find Iron Condor legs"""
        puts = [(c, d) for c, d in option_data.items() if c.right == 'P']
        calls = [(c, d) for c, d in option_data.items() if c.right == 'C']
        
        puts.sort(key=lambda x: x[0].strike, reverse=True)
        calls.sort(key=lambda x: x[0].strike)
        
        # Find short put (delta around -0.10)
        short_put = self._find_target_delta_contract(puts, -self.target_delta)
        if not short_put:
            return None
        
        # Find short call (delta around +0.10)
        short_call = self._find_target_delta_contract(calls, self.target_delta)
        if not short_call:
            return None
        
        # Find protective legs (5 strikes OTM)
        long_put_strike = short_put[0].strike - 5
        long_call_strike = short_call[0].strike + 5
        
        long_put = self._find_strike_contract(puts, long_put_strike)
        long_call = self._find_strike_contract(calls, long_call_strike)
        
        if not long_put or not long_call:
            return None
        
        return {
            'long_put': long_put,
            'short_put': short_put,
            'short_call': short_call,
            'long_call': long_call
        }
    
    def _find_target_delta_contract(self, contracts: list, target_delta: float) -> Optional[Tuple]:
        """Find contract with target delta"""
        for contract, data in contracts:
            if abs(abs(data['delta']) - abs(target_delta)) <= self.tolerance:
                return (contract, data)
        return None
    
    def _find_strike_contract(self, contracts: list, target_strike: float) -> Optional[Tuple]:
        """Find contract with target strike"""
        return next(((c, d) for c, d in contracts if abs(c.strike - target_strike) < 0.01), None)
    
    def calculate_premium(self, iron_condor: Dict) -> float:
        """Calculate net premium"""
        lp_price = iron_condor['long_put'][1]['price']
        sp_price = iron_condor['short_put'][1]['price']
        sc_price = iron_condor['short_call'][1]['price']
        lc_price = iron_condor['long_call'][1]['price']
        
        return (sp_price + sc_price) - (lp_price + lc_price)