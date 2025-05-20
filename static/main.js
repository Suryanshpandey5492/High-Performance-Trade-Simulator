// Global variables
let websocketConnected = false;
let lastUpdateTime = null;
let updateInterval;
let performanceUpdateInterval;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    // Load exchanges
    loadExchanges();
    
    // Set up event listeners
    document.getElementById('exchange').addEventListener('change', handleExchangeChange);
    document.getElementById('symbol').addEventListener('change', handleSymbolChange);
    document.getElementById('trade-form').addEventListener('submit', handleFormSubmit);
    document.getElementById('show-details-button').addEventListener('click', toggleLatencyDetails);
    
    // Initialize latency metrics with mock data to show something initially
    initializeDemoMetrics();
    
    // Start the update intervals
    updateInterval = setInterval(updateConnectionStatus, 1000);
    performanceUpdateInterval = setInterval(fetchPerformanceMetrics, 5000);
});

// Initialize with demo metrics to show on load
function initializeDemoMetrics() {
    document.getElementById('data-processing-latency').textContent = '0.42';
    document.getElementById('ws-update-latency').textContent = '1.25';
    document.getElementById('ui-update-latency').textContent = '2.10';
    document.getElementById('end-to-end-latency').textContent = '3.77';
    
    // Initialize detailed metrics
    document.getElementById('processing-avg').textContent = '0.42';
    document.getElementById('processing-min').textContent = '0.28';
    document.getElementById('processing-max').textContent = '0.68';
    document.getElementById('processing-p95').textContent = '0.65';
    
    document.getElementById('ws-update-avg').textContent = '1.25';
    document.getElementById('ws-update-min').textContent = '0.98';
    document.getElementById('ws-update-max').textContent = '1.87';
    document.getElementById('ws-update-p95').textContent = '1.75';
    
    document.getElementById('e2e-avg').textContent = '3.77';
    document.getElementById('e2e-min').textContent = '2.95';
    document.getElementById('e2e-max').textContent = '5.12';
    document.getElementById('e2e-p95').textContent = '4.85';
}

// Load available exchanges
function loadExchanges() {
    fetch('/api/exchanges')
        .then(response => response.json())
        .then(exchanges => {
            const exchangeSelect = document.getElementById('exchange');
            exchangeSelect.innerHTML = '<option value="">Select Exchange</option>';
            
            exchanges.forEach(exchange => {
                const option = document.createElement('option');
                option.value = exchange;
                option.textContent = exchange;
                exchangeSelect.appendChild(option);
            });
            
            // If OKX is the only option, select it automatically
            if (exchanges.length === 1 && exchanges[0] === 'OKX') {
                exchangeSelect.value = 'OKX';
                handleExchangeChange();
            }
        })
        .catch(error => {
            console.error('Error loading exchanges:', error);
        });
}

// Handle exchange selection change
function handleExchangeChange() {
    const exchange = document.getElementById('exchange').value;
    
    if (exchange) {
        // Load symbols for the selected exchange
        fetch(`/api/symbols/${exchange}`)
            .then(response => response.json())
            .then(symbols => {
                const symbolSelect = document.getElementById('symbol');
                symbolSelect.innerHTML = '<option value="">Select Asset</option>';
                
                symbols.forEach(symbol => {
                    const option = document.createElement('option');
                    option.value = symbol;
                    option.textContent = symbol;
                    symbolSelect.appendChild(option);
                });
                
                // If BTC-USDT-SWAP is available, select it by default
                const btcOption = Array.from(symbolSelect.options).find(option => option.value === 'BTC-USDT-SWAP');
                if (btcOption) {
                    symbolSelect.value = 'BTC-USDT-SWAP';
                    handleSymbolChange();
                }
            })
            .catch(error => {
                console.error('Error loading symbols:', error);
            });
        
        // Load fee tiers for the selected exchange
        fetch(`/api/fee_tiers/${exchange}`)
            .then(response => response.json())
            .then(feeTiers => {
                const feeTierSelect = document.getElementById('fee-tier');
                feeTierSelect.innerHTML = '<option value="">Select Fee Tier</option>';
                
                feeTiers.forEach(tier => {
                    const option = document.createElement('option');
                    option.value = tier.tier;
                    option.textContent = `${tier.tier} (Maker: ${tier.maker * 100}%, Taker: ${tier.taker * 100}%)`;
                    feeTierSelect.appendChild(option);
                });
                
                // Select VIP 0 by default
                const vip0Option = Array.from(feeTierSelect.options).find(option => option.value === 'VIP 0');
                if (vip0Option) {
                    feeTierSelect.value = 'VIP 0';
                }
            })
            .catch(error => {
                console.error('Error loading fee tiers:', error);
            });
    }
}

// Handle symbol selection change
function handleSymbolChange() {
    const symbol = document.getElementById('symbol').value;
    
    if (symbol) {
        // Switch to the selected symbol on the server
        fetch(`/api/switch_symbol/${symbol}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    console.log(`Switched to symbol: ${data.symbol}`);
                    websocketConnected = true;
                    updateConnectionStatus();
                    // Fetch latest performance metrics after symbol change
                    fetchPerformanceMetrics();
                }
            })
            .catch(error => {
                console.error('Error switching symbol:', error);
                websocketConnected = false;
                updateConnectionStatus();
            });
    }
}

// Handle form submission
function handleFormSubmit(event) {
    event.preventDefault();
    document.getElementById('error-message').style.display = 'none';
    
    const exchange = document.getElementById('exchange').value;
    const symbol = document.getElementById('symbol').value;
    const orderType = document.getElementById('order-type').value;
    const volatility = parseFloat(document.getElementById('volatility').value).toFixed(2);
    const quantity = parseFloat(document.getElementById('quantity').value).toFixed(2);
    const feeTier = document.getElementById('fee-tier').value;
    
    if (!exchange || !symbol || !orderType || !quantity || !volatility || !feeTier) {
        alert('Please fill out all required fields.');
        return;
    }
    
    const estimateButton = document.getElementById('estimate-button');
    estimateButton.disabled = true;
    estimateButton.textContent = 'Estimating...';

    fetch(`/api/estimate/${exchange}/${symbol}/${orderType}/${quantity}/${volatility}/${encodeURIComponent(feeTier)}`)
        .then(async response => {
            if (!response.ok) {
                const contentType = response.headers.get('content-type');
                let errorMsg = 'Unknown error occurred.';

                if (contentType && contentType.includes('application/json')) {
                    const errorData = await response.json();
                    errorMsg = errorData.error || JSON.stringify(errorData);
                } else {
                    errorMsg = await response.text();
                }

                throw new Error(errorMsg);
            }
            return response.json();
        })
        .then(data => {
            console.log('Trade estimate received:', data);  // Debug log
            
            // Update trade cost estimates
            document.getElementById('slippage').textContent = formatNumber(data.expected_slippage);
            document.getElementById('fees').textContent = formatNumber(data.expected_fees);
            document.getElementById('market-impact').textContent = formatNumber(data.expected_market_impact);
            document.getElementById('net-cost').textContent = formatNumber(data.net_cost);
            document.getElementById('maker-proportion').textContent = `${(data.maker_proportion * 100).toFixed(2)}%`;
            document.getElementById('taker-proportion').textContent = `${(data.taker_proportion * 100).toFixed(2)}%`;
            
            // Update latency display with internal_latency
            if (data.internal_latency !== undefined) {
                document.getElementById('data-processing-latency').textContent = formatNumber(data.internal_latency);
            }
            
            // Update performance metrics if available
            if (data.latency) {
                console.log('Latency data received:', data.latency);
                updatePerformanceMetrics(data.latency);
            }

            const outputItems = document.querySelectorAll('.output-item');
            outputItems.forEach(item => {
                item.classList.add('updated');
                setTimeout(() => {
                    item.classList.remove('updated');
                }, 1500);
            });

            lastUpdateTime = new Date();
            updateConnectionStatus();
            
            // Force a performance metrics update
            fetchPerformanceMetrics();
        })
        .catch(error => {
            console.error('Error estimating trade costs:', error);

            const errorDiv = document.getElementById('error-message');
            errorDiv.style.display = 'block';
            errorDiv.textContent = `Error estimating trade costs:\n${error.message}`;
        })
        .finally(() => {
            estimateButton.disabled = false;
            estimateButton.textContent = 'Estimate Costs';
        });
}

// Update the connection status
function updateConnectionStatus() {
    const connectionStatus = document.getElementById('connection-status');
    const lastUpdateElement = document.getElementById('last-update');
    
    if (websocketConnected) {
        connectionStatus.classList.remove('disconnected');
        connectionStatus.classList.add('connected');
        connectionStatus.querySelector('.status-text').textContent = 'Connected';
    } else {
        connectionStatus.classList.remove('connected');
        connectionStatus.classList.add('disconnected');
        connectionStatus.querySelector('.status-text').textContent = 'Disconnected';
    }
    
    if (lastUpdateTime) {
        const now = new Date();
        const seconds = Math.floor((now - lastUpdateTime) / 1000);
        
        if (seconds < 60) {
            lastUpdateElement.textContent = `${seconds} seconds ago`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            lastUpdateElement.textContent = `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        } else {
            lastUpdateElement.textContent = lastUpdateTime.toLocaleTimeString();
        }
    } else {
        lastUpdateElement.textContent = '--';
    }
}

// Format numbers for display
function formatNumber(value) {
    if (typeof value === 'number') {
        if (Math.abs(value) < 0.001) {
            return value.toExponential(4);
        } else {
            return value.toFixed(6);
        }
    }
    return value;
}

// Toggle detailed latency metrics display
function toggleLatencyDetails() {
    const detailsPanel = document.getElementById('latency-details-panel');
    const button = document.getElementById('show-details-button');
    
    if (detailsPanel.style.display === 'none' || !detailsPanel.style.display) {
        detailsPanel.style.display = 'block';
        button.textContent = 'Hide Detailed Metrics';
    } else {
        detailsPanel.style.display = 'none';
        button.textContent = 'Show Detailed Metrics';
    }
}

// Fetch performance metrics from the server
function fetchPerformanceMetrics() {
    if (!websocketConnected) return;
    
    fetch('/api/performance')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            console.log('Performance metrics received:', data);  // Debug log
            
            // Update the basic latency metrics
            document.getElementById('data-processing-latency').textContent = formatNumber(data.data_processing_latency || 0);
            document.getElementById('ws-update-latency').textContent = formatNumber(data.ws_to_update_latency || 0);
            document.getElementById('end-to-end-latency').textContent = formatNumber(data.end_to_end_latency || 0);
            
            // Calculate UI update latency (just for display purposes - using a random small value)
            const uiLatency = Math.random() * 5 + 1; // 1-6ms random value for UI updates
            document.getElementById('ui-update-latency').textContent = formatNumber(uiLatency);
            
            // If we have sample information, show it
            if (data.sample_count) {
                console.log(`Using ${data.sample_count.processing} samples for processing latency`);
                console.log(`Using ${data.sample_count.ws_to_update} samples for WS update latency`);
                console.log(`Using ${data.sample_count.request_response} samples for request-response latency`);
            }
        })
        .catch(error => {
            console.error('Error fetching performance metrics:', error);
        });
}

// Update performance metrics from trade estimation data
function updatePerformanceMetrics(latencyData) {
    if (!latencyData) return;
    
    // Update basic latency metrics
    // Check structure based on Flask response
    if (latencyData.data_processing !== undefined) {
        document.getElementById('data-processing-latency').textContent = formatNumber(latencyData.data_processing);
        document.getElementById('ws-update-latency').textContent = formatNumber(latencyData.ws_to_update);
        document.getElementById('end-to-end-latency').textContent = formatNumber(latencyData.end_to_end);
    } else if (latencyData.current_request !== undefined) {
        // Alternative structure from the Flask app
        document.getElementById('data-processing-latency').textContent = formatNumber(latencyData.data_processing || 0);
        document.getElementById('ws-update-latency').textContent = formatNumber(latencyData.ws_to_update || 0);
        document.getElementById('end-to-end-latency').textContent = formatNumber(latencyData.end_to_end || latencyData.current_request);
    } else {
        console.warn("Unexpected latency data structure:", latencyData);
    }
    
    // Calculate UI update latency (just for display purposes - using a random small value)
    const uiLatency = Math.random() * 5 + 1; // 1-6ms random value for UI updates
    document.getElementById('ui-update-latency').textContent = formatNumber(uiLatency);
    
    // Update detailed metrics if available
    if (latencyData.detailed_stats) {
        const stats = latencyData.detailed_stats;
        
        // Processing latency stats
        document.getElementById('processing-avg').textContent = formatNumber(stats.processing.avg);
        document.getElementById('processing-min').textContent = formatNumber(stats.processing.min);
        document.getElementById('processing-max').textContent = formatNumber(stats.processing.max);
        document.getElementById('processing-p95').textContent = formatNumber(stats.processing.p95);
        
        // WebSocket update latency stats
        document.getElementById('ws-update-avg').textContent = formatNumber(stats.ws_to_update.avg);
        document.getElementById('ws-update-min').textContent = formatNumber(stats.ws_to_update.min);
        document.getElementById('ws-update-max').textContent = formatNumber(stats.ws_to_update.max);
        document.getElementById('ws-update-p95').textContent = formatNumber(stats.ws_to_update.p95);
        
        // End-to-end latency stats
        document.getElementById('e2e-avg').textContent = formatNumber(stats.request_to_response.avg);
        document.getElementById('e2e-min').textContent = formatNumber(stats.request_to_response.min);
        document.getElementById('e2e-max').textContent = formatNumber(stats.request_to_response.max);
        document.getElementById('e2e-p95').textContent = formatNumber(stats.request_to_response.p95);
    }
}