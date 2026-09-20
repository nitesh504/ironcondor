"""Handle market data and price fetching"""

import pandas as pd
from typing import Optional, List, Dict
from ib_insync import IB, Contract

class DataManager:
    def __init__(self, ib: IB):
        self.ib = ib
    
    def get_spy_price(self, spy_contract: Contract) -> Optional[float]:
        """Get SPY current price"""
        ticker = self.ib.reqMktData(spy_contract, '', False, False)
        
        for i in range(15):
            self.ib.sleep(1)
            
            # Try multiple price sources
            if ticker.last and ticker.last > 0 and not pd.isna(ticker.last):
                price = ticker.last
                break
            elif ticker.close and ticker.close > 0 and not pd.isna(ticker.close):
                price = ticker.close
                break
            elif ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                if not pd.isna(ticker.bid) and not pd.isna(ticker.ask):
                    price = (ticker.bid + ticker.ask) / 2
                    break
        else:
            price = None
        
        self.ib.cancelMktData(spy_contract)
        return float(price) if price else None
    
    def get_option_data(self, contracts: List[Contract]) -> Dict[Contract, Dict]:
        """Get option prices and deltas"""
        option_data = {}
        tickers = {}
        
        # Request data for all contracts
        for contract in contracts:
            ticker = self.ib.reqMktData(contract, '106', False, False)
            tickers[contract] = ticker
        
        # Wait for data
        for _ in range(8):
            self.ib.sleep(1)
        
        # Collect the data
        for contract, ticker in tickers.items():
            try:
                # Get price
                price = None
                if ticker.last and ticker.last > 0:
                    price = ticker.last
                elif ticker.close and ticker.close > 0:
                    price = ticker.close
                elif ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    price = (ticker.bid + ticker.ask) / 2
                
                # Get delta
                delta = None
                if ticker.modelGreeks and ticker.modelGreeks.delta is not None:
                    delta = ticker.modelGreeks.delta
                
                if price and delta is not None:
                    option_data[contract] = {'price': price, 'delta': delta}
            except:
                continue
            
            self.ib.cancelMktData(contract)
        
        return option_data