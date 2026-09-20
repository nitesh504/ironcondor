import time
import threading
from market_utils import MarketUtils
from order_manager import OrderManager

class AutoCloseMonitor:
    def __init__(self, ib, order_manager: OrderManager, close_minutes: int = 5):
        self.ib = ib
        self.order_manager = order_manager
        self.market_utils = MarketUtils()
        self.close_minutes = close_minutes
        self.monitor_thread = None
    
    def start_monitoring(self):
        """Start monitoring for auto-close time"""
        def monitor_close_time():
            while self.ib.isConnected():
                try:
                    minutes_to_close = self.market_utils.get_time_to_close()
                    
                    if minutes_to_close is not None and minutes_to_close <= self.close_minutes:
                        self.order_manager.close_all_positions()
                        break
                    
                    time.sleep(60)  # Check every minute
                except Exception:
                    break
        
        self.monitor_thread = threading.Thread(target=monitor_close_time, daemon=True)
        self.monitor_thread.start()