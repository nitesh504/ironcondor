import time
from iron_condor_bot import IronCondorBot

def main():
    print("🤖 SPY IRON CONDOR TRADING BOT - MODULAR VERSION")
    
    bot = IronCondorBot()
    
    try:
        if bot.connect():
            bot.execute_strategy()
            
            print("Bot is running... Press Ctrl+C to stop")
            while bot.ib.isConnected():
                time.sleep(60)
        else:
            print("Failed to start bot")
    
    except KeyboardInterrupt:
        print("Bot interrupted")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        bot.disconnect()

if __name__ == "__main__":
    main()