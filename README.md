High-Performance-Trade-Simulator ⚙️📉

This Flask-based web application provides real-time analysis and estimation of trading costs, slippage, market impact, and fee structures for crypto derivatives on the OKX Exchange.

---

Features

- 📡 Live order book updates via WebSocket  
- 📊 Slippage, market impact, and maker-taker model predictions  
- 💰 Fee estimation across different VIP tiers  
- ⚡ Performance metrics for data processing and API response times  
- 🔄 Real-time symbol and exchange data for user selection  

---

Setup Instructions

Follow the steps below to get the application running on your local machine.

1. Clone the Repository

```
git clone https://github.com/Suryanshpandey5492/High-Performance-Trade-Simulator.git
cd High-Performance-Trade-Simulator
```

2. Setup Python Environment
Make sure you have Python 3.7+ installed.

Install dependencies via pip:
```
python -m venv venv
source venv/bin/activate   # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```
3. Run the Flask Application
```
python app.py
```

The application will be available at: http://127.0.0.1:5000

Additional Notes
Ensure your WebSocket connection to the OKX Exchange API is enabled and configured in the application settings.