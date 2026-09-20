"""Main Iron Condor Bot class"""

from ib_insync import IB, Stock
from market_utils import MarketUtils
from data_manager import DataManager
from contract_builder import ContractBuilder
from strategy_analyzer import StrategyAnalyzer
from risk_manager import RiskManager
from order_manager import OrderManager
from auto_close_monitor import AutoCloseMonitor
import config

class IronCondorBot:
    def __init__(self, host=config.IB_HOST, port=config.IB_PORT, client_id=config.CLIENT_ID):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        
        # Initialize modules
        self.market_utils = MarketUtils()
        self.data_manager = DataManager(self.ib)
        self.contract_builder = ContractBuilder(self.ib)
        self.strategy_analyzer = StrategyAnalyzer()
        self.risk_manager = RiskManager(self.ib)
        self.order_manager = OrderManager(self.ib)
        self.auto_close_monitor = AutoCloseMonitor(self.ib, self.order_manager)
        
        self.spy_contract = None
    
    def connect(self) -> bool:
        """Connect to Interactive Brokers"""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            
            spy_stock = Stock('SPY', 'SMART', 'USD')
            self.spy_contract = self.ib.qualifyContracts(spy_stock)[0]
            
            self.auto_close_monitor.start_monitoring()
            return True
        except Exception:
            return False
    
    def execute_strategy(self):
        """Main strategy execution"""
        # Pre-flight checks
        if not self.market_utils.is_market_open():
            print("Market is closed")
            return
        
        minutes_to_close = self.market_utils.get_time_to_close()
        if minutes_to_close is not None and minutes_to_close <= 30:
            print("Too close to market close")
            return
        
        if not self.ib.isConnected() and not self.connect():
            print("Connection failed")
            return
        
        # Get market data
        spy_price = self.data_manager.get_spy_price(self.spy_contract)
        if not spy_price:
            print("Cannot get SPY price")
            return
        
        expiration = self.market_utils.get_expiration_date()
        
        # Build contracts and get data
        option_contracts = self.contract_builder.create_option_contracts(expiration, spy_price)
        if len(option_contracts) < 10:
            print("Insufficient contracts")
            return
        
        option_data = self.data_manager.get_option_data(option_contracts)
        if len(option_data) < 8:
            print("Insufficient market data")
            return
        
        # Find and analyze strategy
        iron_condor = self.strategy_analyzer.find_iron_condor_legs(option_data, spy_price)
        if not iron_condor:
            print("Cannot find Iron Condor")
            return
        
        net_premium = self.strategy_analyzer.calculate_premium(iron_condor)
        if net_premium <= 0:
            print(f"Negative premium: ${net_premium:.2f}")
            return
        
        # Risk check
        if not self.risk_manager.check_margin_requirements(iron_condor):
            print("Insufficient margin")
            return
        
        # Confirm and execute
        proceed = input(f"Execute Iron Condor for ${net_premium:.2f} credit? (y/n): ").strip().lower()
        if proceed not in ['y', 'yes']:
            print("Trade cancelled")
            return
        
        success = self.order_manager.place_iron_condor_orders(iron_condor)
        
        if success:
            print("Iron Condor executed successfully!")
        else:
            print("Trade execution failed")
    
    def disconnect(self):
        """Disconnect from IB"""
        if self.ib.isConnected():
            self.order_manager.close_all_positions()
            self.ib.disconnect()
