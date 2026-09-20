"""Build option contracts"""

from typing import List
from ib_insync import IB, Option, Contract

class ContractBuilder:
    def __init__(self, ib: IB):
        self.ib = ib
    
    def create_option_contracts(self, expiration: str, spy_price: float) -> List[Contract]:
        """Create option contracts around current price"""
        contracts = []
        base_strike = round(float(spy_price))
        
        # Create strikes from -20 to +20 around current price
        strikes = [base_strike + i for i in range(-20, 21) if base_strike + i > 0]
        
        # Create contracts
        for strike in strikes:
            call = Option('SPY', expiration, float(strike), 'C', 'SMART')
            put = Option('SPY', expiration, float(strike), 'P', 'SMART')
            contracts.extend([call, put])
        
        # Qualify contracts
        qualified = self.ib.qualifyContracts(*contracts)
        return [c for c in qualified if c.conId and c.symbol == 'SPY']