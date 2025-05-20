from flask import Flask, render_template, jsonify
import os
import time
import threading
import logging
import statistics
from ws.okx_ws import OKXWebsocket
from utils.orderbook import OrderBook
from models.slippage import SlippageModel
from models.market_impact import MarketImpactModel
from models.maker_taker import MakerTakerModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables
orderbook = None
ws_client = None
current_symbol = "BTC-USDT-SWAP"

# Performance metrics
processing_times = []  # Store processing times for data processing latency
ws_to_update_times = []  # Store times between WS message and orderbook update completion
request_to_response_times = []  # Store API request-to-response latency

# Initialize models
slippage_model = SlippageModel()
market_impact_model = MarketImpactModel()
maker_taker_model = MakerTakerModel()

def process_orderbook_update(data):
    """Process new orderbook data and update models"""
    # Record when we start processing the data
    start_time = time.time()
    ws_receive_time = data.get("receive_time", start_time)  # Time when WS message was received
    
    global orderbook
    if not orderbook:
        orderbook = OrderBook(data["symbol"])
    
    # Update orderbook with new data
    orderbook.update(data["asks"], data["bids"], data["timestamp"])
    
    # Calculate processing time
    end_time = time.time()
    processing_time = (end_time - start_time) * 1000  # Convert to milliseconds
    processing_times.append(processing_time)
    
    # Calculate WS to update completion time
    ws_to_update_time = (end_time - ws_receive_time) * 1000  # Convert to milliseconds
    ws_to_update_times.append(ws_to_update_time)
    
    # Keep only the last 100 measurements for latency calculations
    if len(processing_times) > 100:
        processing_times.pop(0)
    if len(ws_to_update_times) > 100:
        ws_to_update_times.pop(0)
    
    logger.debug(f"Processed orderbook update in {processing_time:.2f} ms")

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/exchanges')
def get_exchanges():
    """Return available exchanges"""
    # For now, only OKX is supported
    return jsonify(["OKX"])

@app.route('/api/symbols/<exchange>')
def get_symbols(exchange):
    """Return available symbols for the given exchange"""
    # For demo purposes, return a limited set of symbols
    if exchange.lower() == "okx":
        return jsonify([ 
            "BTC-USDT-SWAP", 
            "ETH-USDT-SWAP",
            "SOL-USDT-SWAP",
            "AVAX-USDT-SWAP",
            "BNB-USDT-SWAP"
        ])
    return jsonify([])

@app.route('/api/fee_tiers/<exchange>')
def get_fee_tiers(exchange):
    """Return available fee tiers for the given exchange"""
    if exchange.lower() == "okx":
        return jsonify([
            {"tier": "VIP 0", "maker": 0.0008, "taker": 0.0010},
            {"tier": "VIP 1", "maker": 0.0006, "taker": 0.0008},
            {"tier": "VIP 2", "maker": 0.0004, "taker": 0.0006},
            {"tier": "VIP 3", "maker": 0.0002, "taker": 0.0004},
            {"tier": "VIP 4", "maker": 0.0000, "taker": 0.0002},
            {"tier": "VIP 5", "maker": 0.0000, "taker": 0.0000}
        ])
    return jsonify([])

@app.route('/api/estimate/<exchange>/<symbol>/<order_type>/<float:quantity>/<float:volatility>/<fee_tier>')
def estimate_trade(exchange, symbol, order_type, quantity, volatility, fee_tier):
    """Estimate trade costs and market impact"""
    # Record request start time
    request_start_time = time.time()
    
    global orderbook
    
    if not orderbook or orderbook.symbol != symbol:
        return jsonify({
            "error": "Orderbook data not available for the selected symbol"
        }), 400
    
    # Get fee rates based on the fee tier
    fee_tiers = {
        "VIP 0": {"maker": 0.0008, "taker": 0.0010},
        "VIP 1": {"maker": 0.0006, "taker": 0.0008},
        "VIP 2": {"maker": 0.0004, "taker": 0.0006},
        "VIP 3": {"maker": 0.0002, "taker": 0.0004},
        "VIP 4": {"maker": 0.0000, "taker": 0.0002},
        "VIP 5": {"maker": 0.0000, "taker": 0.0000}
    }
    
    fee_rate = fee_tiers.get(fee_tier, {"maker": 0.0008, "taker": 0.0010})
    
    # Calculate maker/taker proportion
    maker_taker = maker_taker_model.predict(
        orderbook=orderbook,
        quantity=quantity,
        volatility=volatility
    )
    
    # Calculate expected slippage
    slippage = slippage_model.predict(
        orderbook=orderbook,
        quantity=quantity,
        order_type=order_type
    )
    
    # Calculate expected market impact
    market_impact = market_impact_model.calculate_impact(
        orderbook=orderbook,
        quantity=quantity,
        volatility=volatility
    )
    
    # Calculate expected fees
    fees = (fee_rate["maker"] * maker_taker["maker_proportion"] + 
            fee_rate["taker"] * maker_taker["taker_proportion"]) * quantity
    
    # Calculate net cost
    net_cost = slippage + fees + market_impact
    
    # Calculate performance metrics
    # Data processing latency
    avg_processing_latency = sum(processing_times) / len(processing_times) if processing_times else 0
    
    # WS-to-update latency
    avg_ws_to_update_latency = sum(ws_to_update_times) / len(ws_to_update_times) if ws_to_update_times else 0
    
    # Request-to-response latency (end-to-end)
    request_end_time = time.time()
    request_latency = (request_end_time - request_start_time) * 1000  # Convert to milliseconds
    request_to_response_times.append(request_latency)
    
    # Keep only the last 100 measurements
    if len(request_to_response_times) > 100:
        request_to_response_times.pop(0)
    
    avg_request_latency = sum(request_to_response_times) / len(request_to_response_times) if request_to_response_times else 0
    
    # Calculate additional statistics
    latency_stats = {
        "processing": {
            "avg": avg_processing_latency,
            "min": min(processing_times) if processing_times else 0,
            "max": max(processing_times) if processing_times else 0,
            "p95": statistics.quantiles(processing_times, n=20)[18] if len(processing_times) >= 20 else (max(processing_times) if processing_times else 0)
        },
        "ws_to_update": {
            "avg": avg_ws_to_update_latency,
            "min": min(ws_to_update_times) if ws_to_update_times else 0,
            "max": max(ws_to_update_times) if ws_to_update_times else 0,
            "p95": statistics.quantiles(ws_to_update_times, n=20)[18] if len(ws_to_update_times) >= 20 else (max(ws_to_update_times) if ws_to_update_times else 0)
        },
        "request_to_response": {
            "avg": avg_request_latency,
            "min": min(request_to_response_times) if request_to_response_times else 0,
            "max": max(request_to_response_times) if request_to_response_times else 0,
            "p95": statistics.quantiles(request_to_response_times, n=20)[18] if len(request_to_response_times) >= 20 else (max(request_to_response_times) if request_to_response_times else 0)
        }
    }
    
    return jsonify({
        "expected_slippage": round(slippage, 6),
        "expected_fees": round(fees, 6),
        "expected_market_impact": round(market_impact, 6),
        "net_cost": round(net_cost, 6),
        "maker_proportion": round(maker_taker["maker_proportion"], 4),
        "taker_proportion": round(maker_taker["taker_proportion"], 4),
        "latency": {
            "data_processing": round(avg_processing_latency, 2),
            "ws_to_update": round(avg_ws_to_update_latency, 2),
            "end_to_end": round(avg_request_latency, 2),
            "current_request": round(request_latency, 2),
            "detailed_stats": {
                "processing": {
                    "avg": round(latency_stats["processing"]["avg"], 2),
                    "min": round(latency_stats["processing"]["min"], 2),
                    "max": round(latency_stats["processing"]["max"], 2),
                    "p95": round(latency_stats["processing"]["p95"], 2)
                },
                "ws_to_update": {
                    "avg": round(latency_stats["ws_to_update"]["avg"], 2),
                    "min": round(latency_stats["ws_to_update"]["min"], 2),
                    "max": round(latency_stats["ws_to_update"]["max"], 2),
                    "p95": round(latency_stats["ws_to_update"]["p95"], 2)
                },
                "request_to_response": {
                    "avg": round(latency_stats["request_to_response"]["avg"], 2),
                    "min": round(latency_stats["request_to_response"]["min"], 2),
                    "max": round(latency_stats["request_to_response"]["max"], 2),
                    "p95": round(latency_stats["request_to_response"]["p95"], 2)
                }
            }
        }
    })

@app.route('/api/performance')
def get_performance_metrics():
    """Return current performance metrics"""
    # Calculate performance metrics
    avg_processing_latency = sum(processing_times) / len(processing_times) if processing_times else 0
    avg_ws_to_update_latency = sum(ws_to_update_times) / len(ws_to_update_times) if ws_to_update_times else 0
    avg_request_latency = sum(request_to_response_times) / len(request_to_response_times) if request_to_response_times else 0
    
    return jsonify({
        "data_processing_latency": round(avg_processing_latency, 2),
        "ws_to_update_latency": round(avg_ws_to_update_latency, 2),
        "end_to_end_latency": round(avg_request_latency, 2),
        "sample_count": {
            "processing": len(processing_times),
            "ws_to_update": len(ws_to_update_times),
            "request_response": len(request_to_response_times)
        }
    })

def start_websocket():
    """Start the WebSocket client in a separate thread"""
    global ws_client, current_symbol
    
    # OKX API credentials
    api_key = "d9f5b1f0-f699-4dbd-8341-b1a985f64a2c"
    api_secret = "8320349645BF7E0C843F2A0BBAD773DA"
    
    ws_client = OKXWebsocket(
        api_key=api_key,
        api_secret=api_secret,
        callback=process_orderbook_update
    )
    
    # Subscribe to the initial symbol
    ws_client.subscribe(current_symbol)
    
    # Start the WebSocket client
    ws_client.start()

@app.route('/api/switch_symbol/<symbol>')
def switch_symbol(symbol):
    """Switch to a different symbol"""
    global ws_client, current_symbol, orderbook
    
    if ws_client and current_symbol != symbol:
        # Unsubscribe from the old symbol and subscribe to the new one
        ws_client.unsubscribe(current_symbol)
        ws_client.subscribe(symbol)
        
        # Update the current symbol
        current_symbol = symbol
        
        # Reset orderbook for the new symbol
        # orderbook = None
        
    return jsonify({"status": "success", "symbol": symbol})

if __name__ == '__main__':
    # Start WebSocket client in a separate thread
    ws_thread = threading.Thread(target=start_websocket)
    ws_thread.daemon = True
    ws_thread.start()
    
    # Start Flask app
    app.run(debug=True, use_reloader=False)