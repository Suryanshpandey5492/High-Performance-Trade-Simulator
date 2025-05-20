import websocket
import json
import hmac
import base64
import zlib
import time
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class OKXWebsocket:
    """
    WebSocket client for OKX exchange
    Handles connection, authentication, and subscription to orderbook data
    """
    
    def __init__(self, api_key, api_secret, callback, passphrase=""):
        """
        Initialize the WebSocket client
        
        Args:
            api_key (str): OKX API key
            api_secret (str): OKX API secret
            callback (callable): Callback function for handling orderbook updates
            passphrase (str): API passphrase (if required)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.callback = callback
        
        self.ws = None
        self.ws_thread = None
        self.is_connected = False
        self.subscriptions = set()
        self.ping_thread = None
        self.should_reconnect = True
        
        # WebSocket endpoint
        self.endpoint = "wss://ws.okx.com:8443/ws/v5/public"
        
    def _generate_signature(self, timestamp):
        """
        Generate signature for authentication
        
        Args:
            timestamp (str): Current timestamp
            
        Returns:
            str: Base64 encoded signature
        """
        message = timestamp + 'GET' + '/users/self/verify'
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        d = mac.digest()
        return base64.b64encode(d).decode()
        
    def _on_message(self, ws, message):
        """
        Handle incoming WebSocket messages
        
        Args:
            ws: WebSocket connection
            message: Raw message data
        """
        if isinstance(message, bytes):
            # Decompress if it's binary data
            message = zlib.decompress(message, -zlib.MAX_WBITS).decode('utf-8')
            
        data = json.loads(message)
        
        # Handle different message types
        if 'event' in data:
            if data['event'] == 'error':
                logger.error(f"WebSocket error: {data['msg']}")
            elif data['event'] == 'subscribe':
                logger.info(f"Successfully subscribed to {data['arg']['channel']} for {data['arg']['instId']}")
        
        # Process orderbook data
        elif 'data' in data and len(data['data']) > 0:
            try:
                channel = data['arg']['channel']
                symbol = data['arg']['instId']
                
                if channel == 'books' or channel == 'books5' or channel == 'books-l2-tbt':
                    # Process orderbook data
                    self._process_orderbook(symbol, data['data'][0])
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
    def _process_orderbook(self, symbol, data):
        """
        Process orderbook data and send to callback
        
        Args:
            symbol (str): Trading pair symbol
            data (dict): Orderbook data
        """
        # Convert OKX format to our internal format
        asks = [[float(price), float(qty)] for price, qty, *_ in data.get('asks', [])]
        bids = [[float(price), float(qty)] for price, qty, *_ in data.get('bids', [])]
        
        # Create timestamp if not provided
        timestamp = int(data.get('ts', time.time() * 1000))
        
        # Prepare data for callback
        processed_data = {
            "symbol": symbol,
            "asks": asks,
            "bids": bids,
            "timestamp": timestamp
        }
        
        # Send to callback
        self.callback(processed_data)
        
    def _on_error(self, ws, error):
        """
        Handle WebSocket errors
        
        Args:
            ws: WebSocket connection
            error: Error information
        """
        logger.error(f"WebSocket error: {error}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """
        Handle WebSocket connection close
        
        Args:
            ws: WebSocket connection
            close_status_code: Status code for close
            close_msg: Close message
        """
        logger.info(f"WebSocket connection closed: {close_status_code} {close_msg}")
        self.is_connected = False
        
        # Attempt to reconnect if needed
        if self.should_reconnect:
            logger.info("Attempting to reconnect...")
            time.sleep(5)  # Wait before reconnecting
            self.connect()
        
    def _on_open(self, ws):
        """
        Handle WebSocket connection open
        
        Args:
            ws: WebSocket connection
        """
        logger.info("WebSocket connection established")
        self.is_connected = True
        
        # Login if API credentials are provided
        if self.api_key and self.api_secret:
            self._login()
            
        # Resubscribe to previously subscribed channels
        for symbol in self.subscriptions:
            self._subscribe(symbol)
            
        # Start ping thread to keep connection alive
        self._start_ping_thread()
        
    def _login(self):
        """
        Authenticate with the WebSocket API
        """
        timestamp = str(int(time.time()))
        signature = self._generate_signature(timestamp)
        
        login_data = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": signature
            }]
        }
        
        self.ws.send(json.dumps(login_data))
        logger.info("Sent authentication request")
        
    def _ping(self):
        """
        Send ping messages to keep connection alive
        """
        while self.is_connected:
            try:
                ping_data = {"op": "ping"}
                self.ws.send(json.dumps(ping_data))
                logger.debug("Sent ping")
                time.sleep(30)  # Send ping every 30 seconds
            except Exception as e:
                logger.error(f"Error sending ping: {e}")
                break
                
    def _start_ping_thread(self):
        """
        Start a thread for sending ping messages
        """
        if self.ping_thread is not None and self.ping_thread.is_alive():
            return
            
        self.ping_thread = threading.Thread(target=self._ping)
        self.ping_thread.daemon = True
        self.ping_thread.start()
        
    def connect(self):
        """
        Establish WebSocket connection
        """
        self.ws = websocket.WebSocketApp(
            self.endpoint,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
    def start(self):
        """
        Start the WebSocket client in a separate thread
        """
        if self.ws_thread is not None and self.ws_thread.is_alive():
            return
            
        self.should_reconnect = True
        self.connect()
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        logger.info("WebSocket client started")
        
    def stop(self):
        """
        Stop the WebSocket client
        """
        self.should_reconnect = False
        if self.is_connected and self.ws:
            self.ws.close()
            
        logger.info("WebSocket client stopped")
        
    def _subscribe(self, symbol):
        """
        Send subscription request for orderbook data
        
        Args:
            symbol (str): Trading pair symbol
        """
        subscribe_data = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "books",
                    "instId": symbol
                }
            ]
        }
        
        if self.is_connected and self.ws:
            self.ws.send(json.dumps(subscribe_data))
            logger.info(f"Sent subscription request for {symbol}")
        
    def subscribe(self, symbol):
        """
        Subscribe to orderbook data for a symbol
        
        Args:
            symbol (str): Trading pair symbol
        """
        self.subscriptions.add(symbol)
        
        if self.is_connected:
            self._subscribe(symbol)
            
    def unsubscribe(self, symbol):
        """
        Unsubscribe from orderbook data for a symbol
        
        Args:
            symbol (str): Trading pair symbol
        """
        if symbol in self.subscriptions:
            self.subscriptions.remove(symbol)
            
            if self.is_connected and self.ws:
                unsubscribe_data = {
                    "op": "unsubscribe",
                    "args": [
                        {
                            "channel": "books",
                            "instId": symbol
                        }
                    ]
                }
                
                self.ws.send(json.dumps(unsubscribe_data))
                logger.info(f"Sent unsubscription request for {symbol}")