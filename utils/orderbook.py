import numpy as np
import pandas as pd
from collections import defaultdict
import logging
import bisect

logger = logging.getLogger(__name__)

class OrderBook:
    """
    OrderBook class for maintaining and analyzing market orderbook data
    """
    
    def __init__(self, symbol, max_depth=100):
        """
        Initialize an empty orderbook
        
        Args:
            symbol (str): Trading pair symbol
            max_depth (int): Maximum depth to maintain for analysis
        """
        self.symbol = symbol
        self.max_depth = max_depth
        
        # Initialize empty orderbook
        self.asks = []  # [[price, quantity], ...]
        self.bids = []  # [[price, quantity], ...]
        self.ask_dict = {}  # {price: quantity}
        self.bid_dict = {}  # {price: quantity}
        
        self.timestamp = 0
        self.last_update_id = 0
        
        # Statistics
        self.mid_price_history = []
        self.spread_history = []
        self.depth_history = []
        self.update_count = 0
        
    def update(self, asks, bids, timestamp):
        """
        Update the orderbook with new data
        
        Args:
            asks (list): List of [price, quantity] pairs for ask orders
            bids (list): List of [price, quantity] pairs for bid orders
            timestamp (int): Timestamp of the update in milliseconds
        """
        self.timestamp = timestamp
        self.update_count += 1
        
        # Update ask side
        for price, quantity in asks:
            if quantity > 0:
                self.ask_dict[price] = quantity
            else:
                # Remove price level if quantity is 0
                self.ask_dict.pop(price, None)
        
        # Update bid side
        for price, quantity in bids:
            if quantity > 0:
                self.bid_dict[price] = quantity
            else:
                # Remove price level if quantity is 0
                self.bid_dict.pop(price, None)
        
        # Reconstruct sorted arrays
        self._rebuild_arrays()
        
        # Update statistics
        self._update_statistics()
        
        logger.debug(f"Updated orderbook for {self.symbol} at {timestamp}")
        
    def _rebuild_arrays(self):
        """
        Rebuild sorted arrays for asks and bids
        """
        # Convert dictionaries to sorted arrays
        self.asks = [[price, qty] for price, qty in sorted(self.ask_dict.items())]
        self.bids = [[price, qty] for price, qty in sorted(self.bid_dict.items(), reverse=True)]
        
        # Limit depth if needed
        if len(self.asks) > self.max_depth:
            self.asks = self.asks[:self.max_depth]
        if len(self.bids) > self.max_depth:
            self.bids = self.bids[:self.max_depth]
            
    def _update_statistics(self):
        """
        Update orderbook statistics
        """
        if not self.asks or not self.bids:
            return
            
        # Calculate mid price
        best_ask = self.asks[0][0]
        best_bid = self.bids[0][0]
        mid_price = (best_ask + best_bid) / 2
        
        # Calculate spread
        spread = best_ask - best_bid
        spread_bps = (spread / mid_price) * 10000  # in basis points
        
        # Calculate depth (sum of quantity within 1% of mid price)
        depth_range = mid_price * 0.01
        ask_depth = sum(qty for price, qty in self.asks if price <= mid_price + depth_range)
        bid_depth = sum(qty for price, qty in self.bids if price >= mid_price - depth_range)
        
        # Store statistics
        self.mid_price_history.append(mid_price)
        self.spread_history.append(spread_bps)
        self.depth_history.append((ask_depth, bid_depth))
        
        # Keep history limited to avoid memory issues
        max_history = 1000
        if len(self.mid_price_history) > max_history:
            self.mid_price_history = self.mid_price_history[-max_history:]
            self.spread_history = self.spread_history[-max_history:]
            self.depth_history = self.depth_history[-max_history:]
    
    def get_best_ask(self):
        """
        Get the best ask price and quantity
        
        Returns:
            tuple: (price, quantity) or (None, None) if no asks
        """
        if self.asks:
            return self.asks[0]
        return (None, None)
    
    def get_best_bid(self):
        """
        Get the best bid price and quantity
        
        Returns:
            tuple: (price, quantity) or (None, None) if no bids
        """
        if self.bids:
            return self.bids[0]
        return (None, None)
    
    def get_mid_price(self):
        """
        Get the current mid price
        
        Returns:
            float: Mid price or None if orderbook is empty
        """
        best_ask_price, _ = self.get_best_ask()
        best_bid_price, _ = self.get_best_bid()
        
        if best_ask_price and best_bid_price:
            return (best_ask_price + best_bid_price) / 2
        return None
    
    def get_spread(self):
        """
        Get the current spread in basis points
        
        Returns:
            float: Spread in basis points or None if orderbook is empty
        """
        best_ask_price, _ = self.get_best_ask()
        best_bid_price, _ = self.get_best_bid()
        
        if best_ask_price and best_bid_price:
            mid_price = (best_ask_price + best_bid_price) / 2
            spread = best_ask_price - best_bid_price
            return (spread / mid_price) * 10000  # in basis points
        return None
    
    def get_volume_at_price(self, side, price):
        """
        Get the volume at a specific price level
        
        Args:
            side (str): 'ask' or 'bid'
            price (float): Price level
            
        Returns:
            float: Volume at the specified price or 0 if not found
        """
        if side.lower() == 'ask':
            return self.ask_dict.get(price, 0)
        elif side.lower() == 'bid':
            return self.bid_dict.get(price, 0)
        return 0
    
    def calculate_market_impact(self, side, quantity):
        """
        Calculate the market impact of a market order
        
        Args:
            side (str): 'buy' or 'sell'
            quantity (float): Order quantity
            
        Returns:
            tuple: (average_price, price_impact_bps, executed_quantity)
        """
        if side.lower() == 'buy':
            # Buy order matches with asks
            levels = self.asks
        else:
            # Sell order matches with bids
            levels = self.bids
            
        remaining_qty = quantity
        total_cost = 0
        executed_qty = 0
        
        # Iterate through price levels
        for price, level_qty in levels:
            if remaining_qty <= 0:
                break
                
            # Calculate how much we can execute at this level
            executable_qty = min(remaining_qty, level_qty)
            
            # Add to total cost
            total_cost += executable_qty * price
            executed_qty += executable_qty
            
            # Reduce remaining quantity
            remaining_qty -= executable_qty
            
        # Calculate average execution price
        if executed_qty > 0:
            avg_price = total_cost / executed_qty
            
            # Calculate price impact in basis points
            mid_price = self.get_mid_price()
            if mid_price:
                if side.lower() == 'buy':
                    impact_bps = ((avg_price / mid_price) - 1) * 10000
                else:
                    impact_bps = ((mid_price / avg_price) - 1) * 10000
            else:
                impact_bps = 0
                
            return (avg_price, impact_bps, executed_qty)
        
        return (None, 0, 0)
    
    def calculate_order_book_imbalance(self):
        """
        Calculate the orderbook imbalance metric
        
        Returns:
            float: Imbalance value between -1 (sell pressure) and 1 (buy pressure)
        """
        if not self.asks or not self.bids:
            return 0
        
        # Calculate total volume at top 5 levels
        ask_volume = sum(qty for _, qty in self.asks[:5])
        bid_volume = sum(qty for _, qty in self.bids[:5])
        
        # Calculate imbalance
        total_volume = ask_volume + bid_volume
        if total_volume > 0:
            imbalance = (bid_volume - ask_volume) / total_volume
            return imbalance
        return 0
    
    def get_liquidity_profile(self, num_levels=10):
        """
        Get a profile of liquidity at different price levels
        
        Args:
            num_levels (int): Number of price levels to include
            
        Returns:
            dict: Liquidity profile
        """
        ask_liquidity = []
        bid_liquidity = []
        
        # Calculate liquidity at each level
        for i in range(min(num_levels, len(self.asks))):
            price, qty = self.asks[i]
            ask_liquidity.append({
                'price': price,
                'quantity': qty,
                'value': price * qty
            })
            
        for i in range(min(num_levels, len(self.bids))):
            price, qty = self.bids[i]
            bid_liquidity.append({
                'price': price,
                'quantity': qty,
                'value': price * qty
            })
            
        return {
            'asks': ask_liquidity,
            'bids': bid_liquidity
        }
    
    def calculate_slippage(self, side, quantity):
        """
        Calculate expected slippage for a market order
        
        Args:
            side (str): 'buy' or 'sell'
            quantity (float): Order quantity
            
        Returns:
            float: Expected slippage in basis points
        """
        # Get mid price as reference
        mid_price = self.get_mid_price()
        if not mid_price:
            return 0
            
        # Calculate market impact
        avg_price, _, executed_qty = self.calculate_market_impact(side, quantity)
        
        if avg_price and executed_qty > 0:
            # Calculate slippage in basis points
            if side.lower() == 'buy':
                slippage_bps = ((avg_price / mid_price) - 1) * 10000
            else:
                slippage_bps = ((mid_price / avg_price) - 1) * 10000
                
            return max(0, slippage_bps)  # Slippage should never be negative
            
        return 0
    
    def to_dataframe(self):
        """
        Convert orderbook to pandas DataFrame for analysis
        
        Returns:
            tuple: (asks_df, bids_df) DataFrames
        """
        asks_df = pd.DataFrame(self.asks, columns=['price', 'quantity'])
        bids_df = pd.DataFrame(self.bids, columns=['price', 'quantity'])
        
        # Add cumulative columns
        if not asks_df.empty:
            asks_df['cumulative_quantity'] = asks_df['quantity'].cumsum()
            asks_df['cumulative_value'] = (asks_df['price'] * asks_df['quantity']).cumsum()
            
        if not bids_df.empty:
            bids_df['cumulative_quantity'] = bids_df['quantity'].cumsum()
            bids_df['cumulative_value'] = (bids_df['price'] * bids_df['quantity']).cumsum()
            
        return asks_df, bids_df
    
    def get_orderbook_summary(self):
        """
        Get a summary of the current orderbook state
        
        Returns:
            dict: Orderbook summary
        """
        mid_price = self.get_mid_price()
        spread = self.get_spread()
        
        # Calculate total depth within 2% of mid price
        depth_range = mid_price * 0.02 if mid_price else 0
        
        ask_depth_qty = 0
        ask_depth_value = 0
        bid_depth_qty = 0
        bid_depth_value = 0
        
        if mid_price:
            for price, qty in self.asks:
                if price <= mid_price + depth_range:
                    ask_depth_qty += qty
                    ask_depth_value += price * qty
                    
            for price, qty in self.bids:
                if price >= mid_price - depth_range:
                    bid_depth_qty += qty
                    bid_depth_value += price * qty
        
        # Calculate imbalance
        imbalance = self.calculate_order_book_imbalance()
        
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'mid_price': mid_price,
            'spread_bps': spread,
            'best_ask': self.get_best_ask()[0] if self.asks else None,
            'best_bid': self.get_best_bid()[0] if self.bids else None,
            'ask_levels': len(self.asks),
            'bid_levels': len(self.bids),
            'ask_depth_qty': ask_depth_qty,
            'bid_depth_qty': bid_depth_qty,
            'ask_depth_value': ask_depth_value,
            'bid_depth_value': bid_depth_value,
            'imbalance': imbalance,
            'update_count': self.update_count
        }