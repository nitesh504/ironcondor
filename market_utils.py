import pytz
from datetime import datetime, time as dt_time

class MarketUtils:
    def __init__(self):
        self.est_tz = pytz.timezone('US/Eastern')
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now(self.est_tz)
        current_time = now.time()
        
        # Check if weekday
        if now.weekday() >= 5:
            return False
        
        market_open = datetime.strptime('09:30', '%H:%M').time()
        market_close = datetime.strptime('16:15', '%H:%M').time()
        
        return market_open <= current_time <= market_close
    
    def get_time_to_close(self) -> int:
        """Get minutes until market close"""
        now = datetime.now(self.est_tz)
        market_close = now.replace(hour=16, minute=15, second=0, microsecond=0)
        
        if now.date() != market_close.date():
            return None
        
        time_diff = market_close - now
        minutes_to_close = int(time_diff.total_seconds() / 60)
        
        return minutes_to_close if minutes_to_close > 0 else 0
    
    def get_expiration_date(self) -> str:
        """Get 0DTE expiration date"""
        return datetime.now(self.est_tz).strftime('%Y%m%d')