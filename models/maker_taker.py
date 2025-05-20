import numpy as np
import logging
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

class MakerTakerModel:
    """
    Model to predict the maker/taker proportion for a given order
    
    This model uses logistic regression to predict what proportion of an order
    will be executed as maker vs taker, based on market conditions like
    volatility and orderbook liquidity.
    """
    
    def __init__(self):
        """Initialize the maker/taker model"""
        self.model = LogisticRegression(random_state=42)
        self.history = []
        self.trained = False
    
    def _extract_features(self, orderbook, quantity, volatility):
        """
        Extract relevant features for the maker/taker model
        
        Args:
            orderbook: OrderBook object with current market data
            quantity: Order quantity in USD
            volatility: Market volatility estimate (percentage)
            
        Returns:
            numpy.ndarray: Feature vector
        """
        # Calculate spread width
        spread = orderbook.get_spread()
        
        # Calculate market depth
        depth_5bps = sum(float(size) for _, size in orderbook.asks if float(_) < orderbook.get_mid_price() * 1.0005)
        depth_10bps = sum(float(size) for _, size in orderbook.asks if float(_) < orderbook.get_mid_price() * 1.001)
        
        # Calculate relative order size as a proportion of available liquidity
        relative_size = quantity / depth_5bps if depth_5bps > 0 else 1.0
        
        # Normalize volatility to 0-1 range (assuming volatility is given as percentage)
        norm_volatility = min(volatility / 10.0, 1.0)
        
        # Return features as numpy array
        return np.array([
            spread,
            depth_5bps,
            depth_10bps,
            relative_size,
            norm_volatility
        ]).reshape(1, -1)
    
    def _simulate_execution(self, orderbook, quantity, volatility):
        """
        Simulate order execution to generate training data
        
        This is a simplified simulation model for maker/taker proportion.
        In a real system, this would ideally be trained on actual execution data.
        
        Args:
            orderbook: OrderBook object
            quantity: Order quantity in USD
            volatility: Market volatility (percentage)
            
        Returns:
            float: Estimated maker proportion between 0.0 and 1.0
        """
        # Base maker proportion depends on market volatility
        # Higher volatility -> lower maker proportion
        base_maker = max(0.0, min(0.9, 1.0 - volatility / 15.0))
        
        # Adjust based on order size relative to market depth
        depth_5bps = sum(float(size) for _, size in orderbook.asks if float(_) < orderbook.get_mid_price() * 1.0005)
        relative_size = quantity / depth_5bps if depth_5bps > 0 else 1.0
        
        # Larger orders -> lower maker proportion
        size_adjustment = max(0.0, min(0.5, 0.5 * (1.0 - relative_size)))
        
        # Spread adjustment - wider spreads favor maker orders
        spread_ratio = orderbook.get_spread() / orderbook.get_mid_price()
        spread_adjustment = min(0.2, spread_ratio * 100)
        
        # Final maker proportion
        maker_proportion = min(0.95, max(0.05, base_maker + size_adjustment + spread_adjustment))
        
        return maker_proportion
    
    def _update_model(self, features, maker_proportion):
        """Update the model with new data"""
        # Add to history with binary labels for multiple samples
        # This simulates having multiple orders with different outcomes
        num_samples = 10
        for _ in range(num_samples):
            # Create synthetic label: 1 = maker, 0 = taker
            is_maker = np.random.random() < maker_proportion
            self.history.append((features, int(is_maker)))
        
        # Keep history size manageable
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
            
        # Retrain model if we have enough data
        if len(self.history) >= 50:
            try:
                X = np.vstack([f for f, _ in self.history])
                y = np.array([l for _, l in self.history])
                self.model.fit(X, y)
                self.trained = True
                logger.debug(f"Maker/taker model retrained with {len(self.history)} observations")
            except Exception as e:
                logger.error(f"Failed to train maker/taker model: {e}")
    
    def predict(self, orderbook, quantity, volatility):
        """
        Predict maker/taker proportion for a given order
        
        Args:
            orderbook: OrderBook object with current market data
            quantity: Order quantity in USD
            volatility: Market volatility estimate (percentage)
            
        Returns:
            dict: Dictionary with 'maker_proportion' and 'taker_proportion' keys
        """
        # Extract features
        features = self._extract_features(orderbook, quantity, volatility)
        
        # Get simulated execution for model updating
        simulated_maker = self._simulate_execution(orderbook, quantity, volatility)
        
        # Make prediction
        if not self.trained or len(self.history) < 50:
            # Not enough data yet, use simulation result
            maker_proportion = simulated_maker
        else:
            try:
                # Predict probability of maker execution using logistic regression
                maker_proba = self.model.predict_proba(features)[0][1]
                
                # Blend model prediction with simulation for robustness
                maker_proportion = 0.7 * maker_proba + 0.3 * simulated_maker
            except Exception as e:
                logger.error(f"Error predicting maker/taker proportion: {e}")
                maker_proportion = simulated_maker
        
        # Update model
        self._update_model(features, simulated_maker)
        
        # Ensure proportions sum to 1.0
        maker_proportion = max(0.0, min(1.0, maker_proportion))
        taker_proportion = 1.0 - maker_proportion
        
        return {
            "maker_proportion": maker_proportion,
            "taker_proportion": taker_proportion
        }