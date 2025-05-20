import numpy as np
from sklearn.linear_model import LinearRegression, QuantileRegressor
import logging

logger = logging.getLogger(__name__)

class SlippageModel:
    """
    Model to estimate slippage for market orders based on orderbook data
    
    This model uses either linear regression or quantile regression to estimate
    the expected slippage based on the current state of the orderbook and the
    order quantity.
    """
    
    def __init__(self):
        """Initialize the slippage model"""
        self.linear_model = LinearRegression()
        self.quantile_model = None  # Initialized on first use
        self.history = []  # Store historical data for model training
        self.trained = False
    
    def _calculate_price_impact(self, orderbook, quantity, side="buy"):
        """Calculate the immediate price impact of a market order"""
        if side == "buy":
            # For buy orders, we walk up the ask side of the book
            book_side = orderbook.asks
            direction = 1
        else:
            # For sell orders, we walk down the bid side of the book
            book_side = orderbook.bids
            direction = -1
            
        remaining_qty = quantity
        executed_value = 0
        
        for price, size in book_side:
            price = float(price)
            size = float(size)
            
            if size >= remaining_qty:
                # This level has enough liquidity to fill the remaining order
                executed_value += remaining_qty * price
                remaining_qty = 0
                break
            else:
                # Consume the entire level and continue
                executed_value += size * price
                remaining_qty -= size
        
        # If there's still remaining quantity, use the last price
        if remaining_qty > 0:
            if book_side:
                last_price = float(book_side[-1][0])
                executed_value += remaining_qty * last_price
            else:
                # No liquidity in the orderbook, use mid price as fallback
                mid_price = orderbook.get_mid_price()
                executed_value += remaining_qty * mid_price
                
        # Calculate average execution price
        avg_price = executed_value / quantity
        
        # Calculate slippage compared to mid price
        slippage = direction * (avg_price - orderbook.get_mid_price())
        
        return slippage
    
    def _extract_features(self, orderbook, quantity):
        """Extract relevant features for the slippage model"""
        # Basic orderbook features
        bid_ask_spread = orderbook.get_spread()
        book_depth = min(len(orderbook.asks), len(orderbook.bids))
        
        # Calculate liquidity imbalance
        ask_liquidity = sum(float(size) for _, size in orderbook.asks[:5])
        bid_liquidity = sum(float(size) for _, size in orderbook.bids[:5])
        liquidity_imbalance = (bid_liquidity - ask_liquidity) / (bid_liquidity + ask_liquidity) if (bid_liquidity + ask_liquidity) > 0 else 0
        
        # Calculate relative order size
        top_5_liquidity = sum(float(size) for _, size in orderbook.asks[:5])
        relative_order_size = quantity / top_5_liquidity if top_5_liquidity > 0 else 1.0
        
        # Return features as a numpy array
        return np.array([
            bid_ask_spread,
            book_depth,
            liquidity_imbalance,
            relative_order_size,
            quantity
        ]).reshape(1, -1)
    
    def _update_model(self, features, slippage):
        """Update the model with new observation"""
        # Add to history
        self.history.append((features, slippage))
        
        # Keep only the last 1000 observations
        if len(self.history) > 1000:
            self.history.pop(0)
        
        # Retrain the model if we have enough data
        if len(self.history) >= 30:
            X = np.vstack([f for f, _ in self.history])
            y = np.array([s for _, s in self.history])
            
            try:
                self.linear_model.fit(X, y)
                self.trained = True
                logger.debug(f"Slippage model retrained with {len(self.history)} observations")
            except Exception as e:
                logger.error(f"Error training slippage model: {e}")
    
    def predict(self, orderbook, quantity, order_type="market"):
        """
        Predict expected slippage for a given order
        
        Args:
            orderbook: OrderBook object with current market data
            quantity: Order quantity in USD
            order_type: Type of order (currently only 'market' is supported)
            
        Returns:
            float: Expected slippage as a percentage of order value
        """
        if order_type != "market":
            logger.warning(f"Unsupported order type: {order_type}, using market order")
        
        # Calculate immediate price impact
        immediate_slippage = self._calculate_price_impact(orderbook, quantity)
        
        # Extract features
        features = self._extract_features(orderbook, quantity)
        
        if not self.trained or len(self.history) < 30:
            # Not enough data for model prediction, use immediate impact as estimate
            predicted_slippage = immediate_slippage
        else:
            # Use the trained model to predict slippage
            try:
                predicted_slippage = self.linear_model.predict(features)[0]
                
                # Blend model prediction with immediate impact for robustness
                predicted_slippage = 0.7 * predicted_slippage + 0.3 * immediate_slippage
            except Exception as e:
                logger.error(f"Error predicting slippage: {e}")
                predicted_slippage = immediate_slippage
        
        # Update the model with the current observation
        self._update_model(features, immediate_slippage)
        
        return predicted_slippage