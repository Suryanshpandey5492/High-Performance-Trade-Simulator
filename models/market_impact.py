import numpy as np
import logging

logger = logging.getLogger(__name__)

class MarketImpactModel:
    """
    Implementation of the Almgren-Chriss market impact model
    
    This model calculates the expected market impact of a trade based on 
    order size, market volatility, and orderbook characteristics.
    """
    
    def __init__(self):
        """Initialize the market impact model"""
        # Model parameters
        self.temp_impact_alpha = 1.0    # Temporary impact exponent
        self.perm_impact_beta = 1.0     # Permanent impact exponent
        self.temp_impact_eta = 0.05     # Temporary impact coefficient
        self.perm_impact_gamma = 0.05   # Permanent impact coefficient
        self.risk_aversion = 0.01       # Risk aversion parameter
        
    def _temporary_impact(self, volume):
        """
        Calculate temporary market impact
        
        Args:
            volume: Trading volume per unit time
            
        Returns:
            float: Temporary price impact
        """
        return self.temp_impact_eta * (volume ** self.temp_impact_alpha)
    
    def _permanent_impact(self, volume):
        """
        Calculate permanent market impact
        
        Args:
            volume: Trading volume per unit time
            
        Returns:
            float: Permanent price impact
        """
        return self.perm_impact_gamma * (volume ** self.perm_impact_beta)
    
    def _calculate_optimal_trajectory(self, quantity, volatility, time_steps=10):
        """
        Calculate the optimal execution trajectory using Almgren-Chriss model
        
        Args:
            quantity: Total quantity to execute
            volatility: Market volatility estimate (percentage)
            time_steps: Number of time steps for the execution
            
        Returns:
            tuple: (value_function, best_moves, inventory_path, optimal_trajectory)
        """
        # Convert volatility from percentage to decimal
        volatility_decimal = volatility / 100.0
        
        # Initialize arrays
        value_function = np.zeros((time_steps, int(quantity) + 1), dtype=float)
        best_moves = np.zeros((time_steps, int(quantity) + 1), dtype=int)
        inventory_path = np.zeros(time_steps, dtype=int)
        inventory_path[0] = quantity
        optimal_trajectory = []
        time_step_size = 0.5  # Time step size
        
        # Terminal condition - liquidate all remaining inventory
        for shares in range(int(quantity) + 1):
            value_function[time_steps - 1, shares] = shares * self._temporary_impact(shares / time_step_size)
            best_moves[time_steps - 1, shares] = shares
        
        # Backward induction
        for t in range(time_steps - 2, -1, -1):
            for shares in range(int(quantity) + 1):
                best_value = float('inf')
                best_share_amount = 0
                
                # Try different execution sizes
                for n in range(shares + 1):
                    # Temporary impact cost
                    temp_cost = n * self._temporary_impact(n / time_step_size)
                    
                    # Permanent impact cost
                    perm_cost = (shares - n) * self._permanent_impact(n / time_step_size)
                    
                    # Risk cost - volatility risk of holding inventory
                    risk_cost = 0.5 * (self.risk_aversion * volatility_decimal) ** 2 * (shares - n) ** 2 * time_step_size
                    
                    # Total cost
                    total_cost = temp_cost + perm_cost + risk_cost + value_function[t + 1, shares - n]
                    
                    if total_cost < best_value:
                        best_value = total_cost
                        best_share_amount = n
                
                value_function[t, shares] = best_value
                best_moves[t, shares] = best_share_amount
        
        # Forward simulation to get optimal trajectory
        curr_inventory = int(quantity)
        for t in range(time_steps - 1):
            move = best_moves[t, curr_inventory]
            optimal_trajectory.append(move)
            curr_inventory -= move
            inventory_path[t + 1] = curr_inventory
        
        return value_function, best_moves, inventory_path, optimal_trajectory
    
    def _adjust_params_from_orderbook(self, orderbook, quantity):
        """
        Adjust model parameters based on orderbook data
        
        Args:
            orderbook: OrderBook object with current market data
            quantity: Order quantity
            
        Returns:
            None: Updates model parameters in-place
        """
        # Calculate market depth (total size available within 0.5% of mid price)
        mid_price = orderbook.get_mid_price()
        depth = sum(float(size) for _, size in orderbook.asks if float(_) < mid_price * 1.005)
        
        # Adjust temporary impact parameter based on market depth
        relative_size = quantity / depth if depth > 0 else 1.0
        self.temp_impact_eta = max(0.01, min(0.1, 0.05 * (1 + 2 * relative_size)))
        
        # Adjust permanent impact parameter based on spread
        spread_ratio = orderbook.get_spread() / mid_price
        self.perm_impact_gamma = max(0.01, min(0.1, 0.05 * (1 + 10 * spread_ratio)))
        
        # Log parameter adjustments
        logger.debug(f"Adjusted market impact params: eta={self.temp_impact_eta:.4f}, gamma={self.perm_impact_gamma:.4f}")
    
    def calculate_impact(self, orderbook, quantity, volatility):
        """
        Calculate expected market impact for a given order
        
        Args:
            orderbook: OrderBook object with current market data
            quantity: Order quantity in USD
            volatility: Market volatility estimate (percentage)
            
        Returns:
            float: Expected market impact as a percentage of trade value
        """
        # Normalize quantity to a reasonable number for the algorithm
        normalized_quantity = min(1000, max(10, quantity / 10))
        
        # Adjust model parameters based on current market conditions
        self._adjust_params_from_orderbook(orderbook, quantity)
        
        try:
            # Calculate optimal execution trajectory
            _, _, _, optimal_trajectory = self._calculate_optimal_trajectory(
                normalized_quantity, volatility)
            
            # Calculate market impact based on optimal trajectory
            total_impact = 0
            
            # Temporary impact component
            for trade_size in optimal_trajectory:
                if trade_size > 0:
                    total_impact += trade_size * self._temporary_impact(trade_size)
            
            # Permanent impact component - affects all subsequent trades
            for i, trade_size in enumerate(optimal_trajectory):
                remaining_qty = sum(optimal_trajectory[i:])
                total_impact += remaining_qty * self._permanent_impact(trade_size)
            
            # Normalize back to percentage of order value and scale appropriately
            impact_percentage = (total_impact / normalized_quantity) * (quantity / 10000)
            
            # Cap at reasonable levels
            return max(0.0, min(0.1, impact_percentage))
            
        except Exception as e:
            logger.error(f"Error calculating market impact: {e}")
            # Fallback to simple estimate based on order size
            mid_price = orderbook.get_mid_price()
            depth = sum(float(size) for _, size in orderbook.asks if float(_) < mid_price * 1.005)
            relative_size = quantity / depth if depth > 0 else 1.0
            
            # Simple square root model as fallback
            return min(0.1, 0.02 * np.sqrt(relative_size))