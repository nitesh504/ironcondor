"""Configuration settings for the Iron Condor Bot"""

# IB Connection Settings
IB_HOST = '127.0.0.1'
IB_PORT = 7497  # Paper trading
CLIENT_ID = 1

# Trading Parameters
TARGET_DELTA = 0.10
DELTA_TOLERANCE = 0.05
PROTECTIVE_STRIKE_DISTANCE = 5
AUTO_CLOSE_MINUTES = 5

# Market Hours (EST)
MARKET_OPEN_TIME = '09:30'
MARKET_CLOSE_TIME = '16:15'