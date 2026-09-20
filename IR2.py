import asyncio
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz
import threading
from ib_insync import IB, Stock, Option, Order, Contract, PortfolioItem, ComboLeg

class IronCondorBot:
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.ib = IB()
        self.host, self.port, self.client_id = host, port, client_id
        self.spy_contract = Stock('SPY', 'SMART', 'USD')
        self.est_tz = pytz.timezone('US/Eastern')
        self.positions_to_close = []
        self.auto_close_timer = None
        
    def is_market_open(self) -> bool:
        try:
            now = datetime.now(self.est_tz)
            if now.weekday() >= 5:
                print(f"Market closed - Weekend")
                return False
            
            current_time = now.time()
            market_open = datetime.strptime('09:30', '%H:%M').time()
            market_close = datetime.strptime('16:15', '%H:%M').time()
            
            is_open = market_open <= current_time <= market_close
            status = "Market is open" if is_open else "Market closed"
            print(f"{status} - Current time: {current_time}")
            return is_open
        except Exception as e:
            print(f"Error checking market hours: {e}")
            return False

    def get_time_to_close(self) -> Optional[int]:
        try:
            now = datetime.now(self.est_tz)
            market_close = now.replace(hour=16, minute=15, second=0, microsecond=0)
            
            if now.date() != market_close.date():
                return None
                
            minutes_to_close = int((market_close - now).total_seconds() / 60)
            return max(0, minutes_to_close)
        except Exception as e:
            print(f"Error calculating time to close: {e}")
            return None

    def connect(self) -> bool:
        try:
            print("Connecting to Interactive Brokers...")
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.spy_contract = self.ib.qualifyContracts(self.spy_contract)[0]
            print(f"Connected - SPY ConId: {self.spy_contract.conId}")
            self.start_auto_close_monitoring()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def get_user_lot_size(self) -> int:
        while True:
            try:
                print("\nLOT SIZE SELECTION")
                print("Please enter the number of Iron Condor contracts to trade:")
                print("(Each contract represents 1 Iron Condor = 4 option legs)")
                
                lot_input = input("Enter lot size (e.g., 1, 2, 5): ").strip()
                if not lot_input:
                    print("Please enter a valid number")
                    continue
                
                lot_size = int(lot_input)
                if lot_size <= 0:
                    print("Lot size must be greater than 0")
                    continue
                if lot_size > 100:
                    print("Lot size seems too large (max 100). Please enter a smaller number.")
                    continue
                
                print(f"Lot size selected: {lot_size} contracts")
                return lot_size
            except ValueError:
                print("Please enter a valid integer number")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user")
                return 0
            except Exception as e:
                print(f"Error getting lot size: {e}")

    def get_current_positions(self) -> List[PortfolioItem]:
        try:
            positions = self.ib.positions()
            return [p for p in positions if (p.contract.symbol == 'SPY' and 
                                          p.contract.secType == 'OPT' and 
                                          p.position != 0)]
        except Exception as e:
            print(f"Error getting positions: {e}")
            return []

    def close_all_positions(self) -> bool:
        try:
            print("\nCLOSING ALL SPY OPTION POSITIONS...")
            positions = self.get_current_positions()
            
            if not positions:
                print("No positions to close")
                return True
            
            print(f"Found {len(positions)} positions to close:")
            
            for position in positions:
                contract = position.contract
                current_pos = int(position.position)
                
                print(f"  {contract.right} ${contract.strike} Exp:{contract.lastTradeDateOrContractMonth} Pos:{current_pos}")
                
                # Fix: Set proper exchange for closing orders
                if not hasattr(contract, 'exchange') or not contract.exchange:
                    contract.exchange = 'SMART'
                
                # Qualify contract to ensure proper exchange
                try:
                    qualified_contracts = self.ib.qualifyContracts(contract)
                    if qualified_contracts:
                        contract = qualified_contracts[0]
                        print(f"    Contract qualified with exchange: {contract.exchange}")
                except Exception as e:
                    print(f"    Could not qualify contract: {e}")
                    contract.exchange = 'SMART'  # Fallback
                
                action = 'SELL' if current_pos > 0 else 'BUY'
                order = Order(action=action, totalQuantity=abs(current_pos), orderType='MKT', tif='DAY')
                
                trade = self.ib.placeOrder(contract, order)
                print(f"    {action} {abs(current_pos)} contracts...")
                
                # Wait for fill
                for _ in range(30):
                    self.ib.sleep(1)
                    if trade.orderStatus.status == 'Filled':
                        print(f"    CLOSED at ${trade.orderStatus.avgFillPrice:.2f}")
                        break
                    elif trade.orderStatus.status in ['Cancelled', 'Rejected']:
                        print(f"    Order {trade.orderStatus.status}: {trade.log[-1].message if trade.log else 'Unknown error'}")
                        break
                else:
                    print(f"    Order timeout - may still be working")
                
                time.sleep(1)
            
            print("Position closing process completed")
            return True
        except Exception as e:
            print(f"Error closing positions: {e}")
            return False

    def start_auto_close_monitoring(self):
        def monitor_close_time():
            while self.ib.isConnected():
                try:
                    minutes_to_close = self.get_time_to_close()
                    if minutes_to_close is not None and minutes_to_close <= 5:
                        print(f"\n{minutes_to_close} minutes until market close - AUTO-CLOSING POSITIONS")
                        self.close_all_positions()
                        break
                    time.sleep(60)
                except Exception as e:
                    print(f"Error in auto-close monitoring: {e}")
                    break
        
        self.auto_close_timer = threading.Thread(target=monitor_close_time, daemon=True)
        self.auto_close_timer.start()
        print("Auto-close monitoring started (will close positions 5 min before market close)")
    
    def get_spy_price(self) -> Optional[float]:
        try:
            print("Getting SPY price...")
            ticker = self.ib.reqMktData(self.spy_contract, '', False, False)
            
            for i in range(15):
                self.ib.sleep(1)
                price = None
                
                # Fixed: Safe attribute access with proper validation
                try:
                    if hasattr(ticker, 'last') and ticker.last is not None:
                        if isinstance(ticker.last, (int, float)) and ticker.last > 0 and not pd.isna(ticker.last):
                            price = ticker.last
                            break
                except:
                    pass
                
                try:
                    if hasattr(ticker, 'close') and ticker.close is not None:
                        if isinstance(ticker.close, (int, float)) and ticker.close > 0 and not pd.isna(ticker.close):
                            price = ticker.close
                            break
                except:
                    pass
                
                try:
                    if (hasattr(ticker, 'bid') and hasattr(ticker, 'ask') and 
                        ticker.bid is not None and ticker.ask is not None):
                        if (isinstance(ticker.bid, (int, float)) and isinstance(ticker.ask, (int, float)) and
                            ticker.bid > 0 and ticker.ask > 0 and 
                            not pd.isna(ticker.bid) and not pd.isna(ticker.ask)):
                            price = (ticker.bid + ticker.ask) / 2
                            break
                except:
                    pass
                
                try:
                    if hasattr(ticker, 'marketPrice') and ticker.marketPrice is not None:
                        if isinstance(ticker.marketPrice, (int, float)) and ticker.marketPrice > 0 and not pd.isna(ticker.marketPrice):
                            price = ticker.marketPrice
                            break
                except:
                    pass
                
                print(f"  Waiting for price data... ({i+1}/15)")
            
            self.ib.cancelMktData(self.spy_contract)
            
            if price is None or pd.isna(price):
                print("Unable to get valid SPY price")
                print("Trying historical data...")
                bars = self.ib.reqHistoricalData(self.spy_contract, '', '1 D', '1 min', 'MIDPOINT', True)
                if bars:
                    price = bars[-1].close
                    print(f"Got price from historical data: ${price:.2f}")
                else:
                    return None
            
            print(f"SPY Price: ${price:.2f}")
            return float(price)
        except Exception as e:
            print(f"Error getting SPY price: {e}")
            return None
    
    def get_expiration_date(self) -> str:
        return datetime.now(self.est_tz).strftime('%Y%m%d')
    
    def create_option_contracts(self, expiration: str, spy_price: float) -> List[Contract]:
        try:
            print(f"Creating option contracts...")
            
            if pd.isna(spy_price) or spy_price <= 0:
                print(f"Invalid SPY price: {spy_price}")
                return []
            
            base_strike = round(float(spy_price))
            print(f"Base strike: ${base_strike} (from SPY price: ${spy_price:.2f})")
            
            strikes = [base_strike + i for i in range(-20, 21) if base_strike + i > 0]
            print(f"Strike range: ${min(strikes):.0f} to ${max(strikes):.0f}")
            
            contracts = []
            for strike in strikes:
                contracts.extend([
                    Option('SPY', expiration, float(strike), 'C', 'CBOE'),
                    Option('SPY', expiration, float(strike), 'P', 'CBOE')
                ])
            
            print("Qualifying contracts...")
            qualified = self.ib.qualifyContracts(*contracts)
            valid_contracts = [c for c in qualified if c.conId and c.symbol == 'SPY']
            
            print(f"{len(valid_contracts)} valid contracts created")
            return valid_contracts
        except Exception as e:
            print(f"Error creating contracts: {e}")
            return []
    
    def get_option_data(self, contracts: List[Contract]) -> Dict[Contract, Dict]:
        try:
            print(f"Getting market data for {len(contracts)} contracts...")
            
            option_data = {}
            tickers = {contract: self.ib.reqMktData(contract, '106', False, False) 
                      for contract in contracts}
            
            # Wait for data
            for _ in range(8):
                self.ib.sleep(1)
            
            for contract, ticker in tickers.items():
                try:
                    price = None
                    # Fixed: Safe attribute access for ticker prices
                    try:
                        if hasattr(ticker, 'last') and ticker.last is not None:
                            if isinstance(ticker.last, (int, float)) and ticker.last > 0:
                                price = ticker.last
                    except:
                        pass
                    
                    if price is None:
                        try:
                            if hasattr(ticker, 'close') and ticker.close is not None:
                                if isinstance(ticker.close, (int, float)) and ticker.close > 0:
                                    price = ticker.close
                        except:
                            pass
                    
                    if price is None:
                        try:
                            if (hasattr(ticker, 'bid') and hasattr(ticker, 'ask') and 
                                ticker.bid is not None and ticker.ask is not None):
                                if (isinstance(ticker.bid, (int, float)) and isinstance(ticker.ask, (int, float)) and
                                    ticker.bid > 0 and ticker.ask > 0):
                                    price = (ticker.bid + ticker.ask) / 2
                        except:
                            pass
                    
                    delta = None
                    try:
                        if (hasattr(ticker, 'modelGreeks') and ticker.modelGreeks is not None and
                            hasattr(ticker.modelGreeks, 'delta') and ticker.modelGreeks.delta is not None):
                            delta = ticker.modelGreeks.delta
                    except:
                        pass
                    
                    if price and delta is not None:
                        option_data[contract] = {'price': price, 'delta': delta}
                except:
                    continue
                
                self.ib.cancelMktData(contract)
            
            print(f"Retrieved data for {len(option_data)} contracts")
            return option_data
        except Exception as e:
            print(f"Error getting option data: {e}")
            return {}
    
    def find_iron_condor_legs(self, option_data: Dict[Contract, Dict], spy_price: float) -> Optional[Dict]:
        try:
            print(f"Finding Iron Condor legs around SPY ${spy_price:.2f}...")
            
            puts = [(c, d) for c, d in option_data.items() if c.right == 'P']
            calls = [(c, d) for c, d in option_data.items() if c.right == 'C']
            
            puts.sort(key=lambda x: x[0].strike, reverse=True)
            calls.sort(key=lambda x: x[0].strike)
            
            target_delta, tolerance = 0.10, 0.05
            
            # Find short legs
            short_put = next((item for item in puts if abs(abs(item[1]['delta']) - target_delta) <= tolerance), None)
            short_call = next((item for item in calls if abs(item[1]['delta'] - target_delta) <= tolerance), None)
            
            if not short_put or not short_call:
                print("Cannot find suitable short strikes")
                return None
            
            # Find protective legs
            long_put_strike = short_put[0].strike - 5
            long_call_strike = short_call[0].strike + 5
            
            long_put = next((item for item in puts if abs(item[0].strike - long_put_strike) < 0.01), None)
            long_call = next((item for item in calls if abs(item[0].strike - long_call_strike) < 0.01), None)
            
            if not long_put or not long_call:
                print("Cannot find protective strikes")
                return None
            
            iron_condor = {
                'long_put': long_put, 'short_put': short_put,
                'short_call': short_call, 'long_call': long_call
            }
            
            print("\nIRON CONDOR FOUND:")
            for name, (contract, data) in iron_condor.items():
                print(f"{name.upper():11}: ${contract.strike:>6.0f} | Δ={data['delta']:>6.3f} | ${data['price']:>5.2f}")
            
            return iron_condor
        except Exception as e:
            print(f"Error finding Iron Condor: {e}")
            return None
    
    def calculate_premium(self, iron_condor: Dict, quantity: int = 1) -> float:
        try:
            prices = {k: v[1]['price'] for k, v in iron_condor.items()}
            net_premium_per_contract = (prices['short_put'] + prices['short_call']) - (prices['long_put'] + prices['long_call'])
            total_net_premium = net_premium_per_contract * quantity
            
            print(f"\nNET PREMIUM PER CONTRACT: ${net_premium_per_contract:.2f}")
            print(f"TOTAL NET PREMIUM ({quantity} contracts): ${total_net_premium:.2f}")
            return total_net_premium
        except Exception as e:
            print(f"Error calculating premium: {e}")
            return 0.0

    def validate_combo_order(self, iron_condor: Dict, quantity: int) -> bool:
        """
        Validate the Iron Condor combination order before placing it
        """
        try:
            print("\nVALIDATING IRON CONDOR COMBINATION ORDER...")
            
            # Create test combination contract
            combo_contract = Contract()
            combo_contract.symbol = "SPY" 
            combo_contract.secType = "BAG"
            combo_contract.currency = "USD"
            combo_contract.exchange = "SMART"
            
            combo_legs = []
            
            # Add all legs in proper order
            contracts_and_actions = [
                (iron_condor['long_put'][0], "BUY"),
                (iron_condor['short_put'][0], "SELL"), 
                (iron_condor['short_call'][0], "SELL"),
                (iron_condor['long_call'][0], "BUY")
            ]
            
            for contract, action in contracts_and_actions:
                leg = ComboLeg()
                leg.conId = contract.conId
                leg.ratio = 1
                leg.action = action
                leg.exchange = "SMART"
                combo_legs.append(leg)
            
            combo_contract.comboLegs = combo_legs
            
            # Test with minimal limit order
            test_order = Order()
            test_order.action = "BUY"  # BUY combination = receive credit
            test_order.totalQuantity = 1  # Test with 1 contract
            test_order.orderType = "LMT" 
            test_order.lmtPrice = 0.05  # Very low price for testing
            test_order.tif = "DAY"
            
            print("Testing combination order margin requirements...")
            
            # Use whatIfOrder to validate
            whatif = self.ib.whatIfOrder(combo_contract, test_order)
            
            if not whatif:
                print("Validation failed - cannot check combination order")
                return False
                
            # Check margin requirements
            margin_req = abs(float(whatif.initMarginChange or 0))
            print(f"Estimated margin per contract: ${margin_req:.2f}")
            print(f"Total margin for {quantity} contracts: ${margin_req * quantity:.2f}")
            
            # Get available buying power
            account_info = self.ib.accountSummary()
            buying_power = float(next((item.value for item in account_info if item.tag == 'BuyingPower'), '0'))
            
            print(f"Available buying power: ${buying_power:.2f}")
            
            total_margin_needed = margin_req * quantity
            if total_margin_needed > buying_power * 0.8:  # Don't use more than 80%
                print(f"INSUFFICIENT BUYING POWER:")
                print(f"  Required: ${total_margin_needed:.2f}")
                print(f"  Available: ${buying_power:.2f}")
                return False
                
            print("✓ Combination order validation PASSED")
            print(f"✓ Margin requirement: ${total_margin_needed:.2f} (vs ${buying_power:.2f} available)")
            return True
            
        except Exception as e:
            print(f"Validation error: {e}")
            return False

    def place_iron_condor_combo_order(self, iron_condor: Dict, quantity: int = 1) -> bool:
        """
        Place Iron Condor as a single combination order to avoid margin issues
        """
        try:
            print(f"\n🔄 PLACING IRON CONDOR COMBINATION ORDER FOR {quantity} CONTRACTS")
            
            # Create the combination contract
            combo_contract = Contract()
            combo_contract.symbol = "SPY"
            combo_contract.secType = "BAG"
            combo_contract.currency = "USD"
            combo_contract.exchange = "SMART"
            
            # Create combo legs for Iron Condor
            combo_legs = []
            
            # Long Put (BUY) - protective leg
            long_put_leg = ComboLeg()
            long_put_leg.conId = iron_condor['long_put'][0].conId
            long_put_leg.ratio = 1
            long_put_leg.action = "BUY"
            long_put_leg.exchange = "SMART"
            combo_legs.append(long_put_leg)
            
            # Short Put (SELL) - income leg
            short_put_leg = ComboLeg()
            short_put_leg.conId = iron_condor['short_put'][0].conId
            short_put_leg.ratio = 1
            short_put_leg.action = "SELL"
            short_put_leg.exchange = "SMART"
            combo_legs.append(short_put_leg)
            
            # Short Call (SELL) - income leg
            short_call_leg = ComboLeg()
            short_call_leg.conId = iron_condor['short_call'][0].conId  
            short_call_leg.ratio = 1
            short_call_leg.action = "SELL"
            short_call_leg.exchange = "SMART"
            combo_legs.append(short_call_leg)
            
            # Long Call (BUY) - protective leg
            long_call_leg = ComboLeg()
            long_call_leg.conId = iron_condor['long_call'][0].conId
            long_call_leg.ratio = 1
            long_call_leg.action = "BUY" 
            long_call_leg.exchange = "SMART"
            combo_legs.append(long_call_leg)
            
            combo_contract.comboLegs = combo_legs
            
            # Calculate net credit limit price
            net_credit = (iron_condor['short_put'][1]['price'] + iron_condor['short_call'][1]['price']) - \
                        (iron_condor['long_put'][1]['price'] + iron_condor['long_call'][1]['price'])
            
            # Use limit order with buffer below expected credit (more conservative)
            limit_price = max(0.10, net_credit - 0.15)  # At least $0.10, or $0.15 below expected
            
            # Create the combination order
            combo_order = Order()
            combo_order.action = "BUY"  # BUY the combination (net credit to us)
            combo_order.totalQuantity = quantity
            combo_order.orderType = "LMT"
            combo_order.lmtPrice = limit_price
            combo_order.tif = "DAY"
            combo_order.transmit = True
            
            print(f"📊 Combination order details:")
            print(f"   Expected Credit: ${net_credit:.2f}")
            print(f"   Limit Price: ${limit_price:.2f}")
            print(f"   Quantity: {quantity}")
            print(f"   Legs: Long Put ${iron_condor['long_put'][0].strike} | Short Put ${iron_condor['short_put'][0].strike} | Short Call ${iron_condor['short_call'][0].strike} | Long Call ${iron_condor['long_call'][0].strike}")
            
            # Place the combination order
            trade = self.ib.placeOrder(combo_contract, combo_order)
            print("⏳ Iron Condor combination order placed... waiting for fill")
            
            # Wait for fill with detailed status updates
            max_wait = 90  # seconds - longer wait for combo orders
            for i in range(max_wait):
                self.ib.sleep(1)
                status = trade.orderStatus.status
                
                if status == 'Filled':
                    avg_price = trade.orderStatus.avgFillPrice or 0
                    total_credit = avg_price * quantity * 100  # Convert to total dollars
                    print(f"\n🎉 IRON CONDOR FILLED SUCCESSFULLY!")
                    print(f"   Fill Price: ${avg_price:.2f} per contract")
                    print(f"   Total Credit Received: ${total_credit:.2f}")
                    print(f"   Max Risk: ${(5.0 * quantity * 100) - total_credit:.2f}")  # 5-point spread
                    print(f"   Max Profit: ${total_credit:.2f}")
                    return True
                elif status in ['Cancelled', 'Rejected']:
                    error_msg = trade.log[-1].message if trade.log else "Unknown error"
                    print(f"\n❌ Order {status}: {error_msg}")
                    
                    # Try to diagnose the issue
                    if "margin" in error_msg.lower():
                        print("💡 MARGIN ISSUE DETECTED - This suggests:")
                        print("   • Account may not have sufficient buying power")
                        print("   • Try reducing quantity or check account requirements")
                    elif "reject" in error_msg.lower():
                        print("💡 ORDER REJECTED - This could be due to:")
                        print("   • Price too aggressive (limit too high)")
                        print("   • Market conditions")
                        print("   • Contract qualification issues")
                    
                    return False
                elif i % 15 == 0 and i > 0:
                    print(f"   ⏱️  Still waiting for fill... ({i}s elapsed, status: {status})")
                elif i % 5 == 0 and i > 0 and status == 'Submitted':
                    # Show current market info
                    print(f"   📈 Order status: {status} (limit: ${limit_price:.2f})")
            
            print(f"\n⚠️  Order timeout after {max_wait}s - order may still be working")
            print(f"   Final status: {trade.orderStatus.status}")
            
            # Cancel if still pending
            if trade.orderStatus.status not in ['Filled', 'Cancelled']:
                try:
                    self.ib.cancelOrder(trade.order)
                    print("   Order cancelled due to timeout")
                except:
                    print("   Could not cancel order - please check manually")
            
            return False
            
        except Exception as e:
            print(f"❌ Critical error placing combination order: {e}")
            return False

    def execute_iron_condor_strategy(self, iron_condor: Dict, quantity: int = 1) -> bool:
        """
        Execute Iron Condor using combination orders (MAIN METHOD)
        """
        try:
            print(f"\n🚀 EXECUTING IRON CONDOR STRATEGY")
            
            # First validate the combination order
            if not self.validate_combo_order(iron_condor, quantity):
                print("❌ Iron Condor validation failed")
                return False
            
            # Then place the actual combination order
            success = self.place_iron_condor_combo_order(iron_condor, quantity)
            
            if success:
                print("\n✅ IRON CONDOR SUCCESSFULLY EXECUTED AS COMBINATION ORDER!")
                print("🔄 Position will be monitored and auto-closed before market close")
            else:
                print("\n❌ Iron Condor execution failed")
                
            return success
            
        except Exception as e:
            print(f"❌ Error executing Iron Condor strategy: {e}")
            return False
    
    def execute_strategy(self):
        print("\n🤖 STARTING SPY IRON CONDOR STRATEGY (COMBINATION ORDER VERSION)")
        print("📋 Features: Single combo order execution + Margin-efficient + Auto cleanup")
        
        try:
            if not self.is_market_open():
                print("❌ Cannot execute - market is closed")
                return
            
            minutes_to_close = self.get_time_to_close()
            if minutes_to_close is not None and minutes_to_close <= 30:
                print(f"⚠️  Only {minutes_to_close} minutes until market close - skipping new trades")
                return
            
            if not self.ib.isConnected() and not self.connect():
                return
            
            lot_size = self.get_user_lot_size()
            if lot_size <= 0:
                print("❌ Trade cancelled - invalid lot size")
                return
            
            spy_price = self.get_spy_price()
            if not spy_price:
                print("❌ Cannot get SPY price")
                return
            
            expiration = self.get_expiration_date()
            option_contracts = self.create_option_contracts(expiration, spy_price)
            if len(option_contracts) < 10:
                print("❌ Insufficient contracts")
                return
            
            option_data = self.get_option_data(option_contracts)
            if len(option_data) < 8:
                print("❌ Insufficient market data")
                return
            
            iron_condor = self.find_iron_condor_legs(option_data, spy_price)
            if not iron_condor:
                return
            
            total_net_premium = self.calculate_premium(iron_condor, lot_size)
            if total_net_premium <= 0:
                print(f"❌ Negative premium: ${total_net_premium:.2f}")
                return
            
            # Calculate max risk for Iron Condor (5-point spread)
            max_risk = (5.0 * lot_size * 100) - total_net_premium
            
            print(f"\n📊 TRADE SUMMARY:")
            print(f"   Strategy: Iron Condor (COMBINATION ORDER)")
            print(f"   Contracts: {lot_size}")
            print(f"   Expected Credit: ${total_net_premium:.2f}")
            print(f"   Credit per Contract: ${total_net_premium/lot_size:.2f}")
            print(f"   Maximum Risk: ${max_risk:.2f}")
            print(f"   Risk/Reward Ratio: {max_risk/total_net_premium:.1f}:1")
            
            proceed = input(f"\n❓ Execute this Iron Condor trade? (y/n): ").strip().lower()
            if proceed not in ['y', 'yes']:
                print("❌ Trade cancelled by user")
                return
            
            # Use the NEW combination order method instead of individual orders
            success = self.execute_iron_condor_strategy(iron_condor, quantity=lot_size)
            
            if success:
                print("\n🎉 IRON CONDOR TRADE EXECUTED SUCCESSFULLY!")
                print("⏰ Positions will be automatically closed 5 minutes before market close")
            else:
                print("\n❌ TRADE EXECUTION FAILED")
                print("💡 This could be due to:")
                print("   • Insufficient margin/buying power")
                print("   • Market conditions (spread too wide)")
                print("   • Order pricing (try with different strikes)")
                
        except Exception as e:
            print(f"❌ Strategy error: {e}")

    def disconnect(self):
        if self.ib.isConnected():
            print("\n📋 Listing open positions before disconnect (not closing them)...")
            open_positions = self.ib.positions()
            if open_positions:
                print("📍 Current positions:")
                for pos in open_positions:
                    contract = pos.contract
                    print(f"   {contract.symbol} | "
                        f"Exp: {getattr(contract, 'lastTradeDateOrContractMonth', 'N/A')} | "
                        f"Strike: {getattr(contract, 'strike', 'N/A')} | "
                        f"Type: {getattr(contract, 'right', 'N/A')} | "
                        f"Pos: {pos.position}")
            else:
                print("✅ No open positions.")
        
        self.ib.disconnect()
        print("🔌 Disconnected from Interactive Brokers")


def main():
    print("🤖 SPY IRON CONDOR TRADING BOT - COMBINATION ORDER VERSION")
    print("✨ Features: Margin-efficient combo orders + Complete execution or nothing + Auto cleanup")
    print("🎯 Strategy: Same-day SPY Iron Condors with automatic position management")
    
    bot = IronCondorBot(host='127.0.0.1', port=7497, client_id=1)
    
    try:
        if bot.connect():
            bot.execute_strategy()
            print("\n🔄 Bot is running... Press Ctrl+C to stop")
            while bot.ib.isConnected():
                time.sleep(60)
        else:
            print("❌ Failed to start bot")
    except KeyboardInterrupt:
        print("\n⏹️  Bot interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        bot.disconnect()

if __name__ == "__main__":
    main()