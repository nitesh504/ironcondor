"""Handle order placement and position management"""

import time
from typing import Dict, List
from ib_insync import IB, MarketOrder, PortfolioItem

class OrderManager:
    def __init__(self, ib: IB):
        self.ib = ib
        self.positions_to_close = []
    
    def place_iron_condor_orders(self, iron_condor: Dict, quantity: int = 1) -> bool:
        """Place individual orders for each leg"""
        legs = [
            ("BUY", iron_condor['long_put'], "LONG PUT"),
            ("SELL", iron_condor['short_put'], "SHORT PUT"),
            ("SELL", iron_condor['short_call'], "SHORT CALL"),
            ("BUY", iron_condor['long_call'], "LONG CALL")
        ]
        
        executed_contracts = []
        
        for action, leg_data, leg_name in legs:
            contract, data = leg_data
            
            order = MarketOrder(action, quantity)
            order.tif = 'DAY'
            
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for fill
            if not self._wait_for_fill(trade, timeout=30):
                return False
            
            executed_contracts.append(contract)
            time.sleep(1)
        
        self.positions_to_close.extend(executed_contracts)
        return True
    
    def _wait_for_fill(self, trade, timeout: int = 30) -> bool:
        """Wait for order to fill"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            self.ib.sleep(1)
            if trade.orderStatus.status == 'Filled':
                return True
            elif trade.orderStatus.status in ['Cancelled', 'Rejected']:
                return False
        
        return False
    
    def get_current_positions(self) -> List[PortfolioItem]:
        """Get current SPY option positions"""
        positions = self.ib.positions()
        return [p for p in positions if (p.contract.symbol == 'SPY' and 
                                       p.contract.secType == 'OPT' and 
                                       p.position != 0)]
    
    def close_all_positions(self) -> bool:
        """Close all open SPY option positions"""
        positions = self.get_current_positions()
        
        if not positions:
            return True
        
        for position in positions:
            contract = position.contract
            current_pos = int(position.position)
            
            action = 'SELL' if current_pos > 0 else 'BUY'
            quantity = abs(current_pos)
            
            order = MarketOrder(action, quantity)
            order.tif = 'DAY'
            
            trade = self.ib.placeOrder(contract, order)
            self._wait_for_fill(trade, timeout=30)
            time.sleep(1)
        
        return True