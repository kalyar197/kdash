/**
 * Main Application Module - Tab-based trading system
 * Handles BTC and ETH charts with independent time controls
 */

// Import functions from modules
import { getDatasetData } from './api.js';
import { initChart, renderChart, initFundingRateChart, renderFundingRateChart } from './chart.js';
import {
    initOscillatorChart, renderOscillatorChart, initBreakdownChart, renderBreakdownChart
} from './oscillator.js';

// Application state
const appState = {
    activeTab: 'main',         // Current active tab
    days: {
        btc: 180                    // Default 6M for BTC
    },
    chartData: {
        btc: null
    },
    chartsInitialized: {
        btc: false
    },
    colors: {
        btc: '#FFFFFF'              // White for better 0-line visibility
    },
    // Oscillator state
    oscillatorData: {
        btc: {}
    },
    oscillatorsInitialized: {
        btc: false
    },
    breakdownInitialized: {
        btc: false
    },
    breakdownPriceInitialized: {
        btc: false
    },
    breakdownMacroInitialized: {
        btc: false
    },
    breakdownDerivativesInitialized: {
        btc: false
    },
    selectedDatasets: {
        btc: ['rsi', 'adx']  // Only ADX (60%) and RSI (40%)
    },
    datasetColors: {
        rsi: '#FF9500',           // Orange
        macd_histogram: '#2196F3', // Blue
        adx: '#673AB7',           // Purple
        atr: '#FF5722'            // Orange-red
    },
    // Noise level state (unified for all oscillators)
    noiseLevel: {
        btc: 14                     // Default: Max noise level
    },
    compositeMode: true,  // Use composite oscillator mode by default
    // Overlay state (moving averages on price chart)
    overlaySelections: {
        btc: []                     // Selected overlays for BTC (e.g., ['sma_14_btc', 'sma_60_btc'])
    },
    // Funding rate state
    fundingRateData: {
        btc: null
    },
    fundingRateInitialized: {
        btc: false
    },
    // Regime data state (for price chart background)
    regimeData: {
        btc: null
    },
    // Global date extent for synchronized chart alignment
    globalDateExtent: null
};

// Expose appState globally for access from other modules (oscillator.js needs regime data)
window.appState = appState;

/**
 * Main application entry point
 */
async function main() {
    console.log('BTC Trading System initializing...');

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        await initialize();
    }
}

/**
 * Initialize the application
 */
async function initialize() {
    try {
        console.log('Initializing application...');

        // Setup tab switching
        setupTabs();

        // Setup time period controls
        setupTimeControls();

        // Setup oscillator controls
        setupOscillatorControls();

        // Setup noise level controls (unified for all oscillators)
        setupNoiseLevelControls();

        // Setup overlay controls (moving averages)
        setupOverlayControls();

        // Load main tab data on startup
        await loadTab('btc');

        console.log('Application initialized successfully!');

    } catch (error) {
        console.error('Failed to initialize application:', error);
        showErrorMessage('btc', 'Failed to initialize application. Please refresh the page.');
    }
}

/**
 * Setup tab switching behavior
 */
function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const tabName = button.dataset.tab;

            if (tabName === appState.activeTab) {
                return; // Already on this tab
            }

            // Update UI
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabName}-tab`).classList.add('active');

            // Update state
            appState.activeTab = tabName;
        });
    });
}

/**
 * Setup time period control buttons
 */
function setupTimeControls() {
    const timeButtons = document.querySelectorAll('.time-btn');

    timeButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const dataset = button.dataset.dataset;
            const days = parseInt(button.dataset.days);

            // Update active button for this dataset
            document.querySelectorAll(`.time-btn[data-dataset="${dataset}"]`).forEach(btn => {
                btn.classList.remove('active');
            });
            button.classList.add('active');

            // Update state and reload chart
            appState.days[dataset] = days;
            await loadChartData(dataset);
            await loadOscillatorData(dataset);
            await loadBreakdownOscillatorData(dataset);
            await loadBreakdownPriceOscillatorData(dataset);
            await loadMacroOscillatorData(dataset);
            await loadBreakdownDerivativesOscillatorData(dataset);
            await loadFundingRateData(dataset);
        });
    });
}

/**
 * Setup oscillator control event handlers
 * Handles checkbox toggles for oscillator datasets
 */
function setupOscillatorControls() {
    document.querySelectorAll('.oscillator-dataset-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', async () => {
            const asset = checkbox.dataset.asset;
            const datasetName = checkbox.dataset.dataset;

            // Update selected datasets
            if (checkbox.checked) {
                if (!appState.selectedDatasets[asset].includes(datasetName)) {
                    appState.selectedDatasets[asset].push(datasetName);
                }
            } else {
                appState.selectedDatasets[asset] = appState.selectedDatasets[asset].filter(
                    d => d !== datasetName
                );
            }

            console.log(`Oscillator dataset ${datasetName} toggled for ${asset}:`, checkbox.checked);
            console.log(`Current selections:`, appState.selectedDatasets[asset]);

            // Reload oscillator data with updated selections
            await loadOscillatorData(asset);
        });
    });
}

/**
 * Setup noise level controls for all oscillators (composite + breakdown)
 */
function setupNoiseLevelControls() {
    document.querySelectorAll('.noise-btn:not(.volatility-noise-btn)').forEach(button => {
        button.addEventListener('click', async () => {
            const asset = button.dataset.asset;
            const level = parseInt(button.dataset.level);

            // Update active button state for this asset
            document.querySelectorAll(`.noise-btn:not(.volatility-noise-btn)[data-asset="${asset}"]`).forEach(btn => {
                btn.classList.remove('active');
            });
            button.classList.add('active');

            // Update state
            appState.noiseLevel[asset] = level;

            console.log(`Noise level changed for ${asset}: ${level}`);

            // Reload all oscillator charts with new noise level
            await loadOscillatorData(asset);
            await loadBreakdownOscillatorData(asset);
            await loadBreakdownPriceOscillatorData(asset);
            await loadMacroOscillatorData(asset);
            await loadBreakdownDerivativesOscillatorData(asset);
        });
    });
}

/**
 * Setup overlay controls (moving averages on price chart)
 */
function setupOverlayControls() {
    document.querySelectorAll('.overlay-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', async () => {
            const asset = checkbox.dataset.asset;
            const overlayName = checkbox.dataset.overlay;

            // Update overlay selections
            if (checkbox.checked) {
                if (!appState.overlaySelections[asset].includes(overlayName)) {
                    appState.overlaySelections[asset].push(overlayName);
                }
            } else {
                appState.overlaySelections[asset] = appState.overlaySelections[asset].filter(
                    o => o !== overlayName
                );
            }

            console.log(`Overlay selection changed for ${asset}:`, appState.overlaySelections[asset]);

            // Reload chart data with updated overlays
            await loadChartData(asset);
        });
    });
}

/**
 * Load a tab (initialize chart if needed, fetch and render data)
 * @param {string} dataset - Dataset name ('btc', 'eth', 'gold')
 */
async function loadTab(dataset) {
    console.log(`Loading tab: ${dataset}`);

    // Initialize price chart if not already initialized
    if (!appState.chartsInitialized[dataset]) {
        const containerId = `${dataset}-chart-container`;
        const color = appState.colors[dataset];

        console.log(`Initializing price chart for ${dataset}`);
        initChart(containerId, dataset, color);
        appState.chartsInitialized[dataset] = true;
    }

    // Initialize oscillator chart if not already initialized
    if (!appState.oscillatorsInitialized[dataset]) {
        const containerId = `${dataset}-oscillator-container`;
        const color = appState.colors[dataset];

        console.log(`Initializing oscillator chart for ${dataset}`);
        initOscillatorChart(containerId, dataset, color);
        appState.oscillatorsInitialized[dataset] = true;
    }

    // Initialize funding rate chart if not already initialized
    if (!appState.fundingRateInitialized[dataset]) {
        const containerId = `${dataset}-funding-rate-container`;

        console.log(`Initializing funding rate chart for ${dataset}`);
        initFundingRateChart(containerId, dataset);
        appState.fundingRateInitialized[dataset] = true;
    }

    // Load price chart data
    await loadChartData(dataset);

    // Load all oscillator data (composite + 4 breakdown charts)
    await loadOscillatorData(dataset);
    await loadBreakdownOscillatorData(dataset);
    await loadBreakdownPriceOscillatorData(dataset);
    await loadMacroOscillatorData(dataset);
    await loadBreakdownDerivativesOscillatorData(dataset);

    // Load funding rate data
    await loadFundingRateData(dataset);
}

/**
 * Fetch data and render chart for a dataset
 * @param {string} dataset - Dataset name ('btc', 'eth', or 'gold')
 */
async function loadChartData(dataset) {
    const days = appState.days[dataset];

    console.log(`Fetching ${dataset} data for ${days} days...`);

    // Show loading state
    showLoadingMessage(dataset);

    try {
        // Fetch price data from API
        const result = await getDatasetData(dataset, days);

        if (!result || !result.data || result.data.length === 0) {
            throw new Error('No data available');
        }

        console.log(`Received ${result.data.length} data points for ${dataset}`);

        // Store data in state
        appState.chartData[dataset] = result.data;

        // Calculate and store global date extent for chart alignment (from BTC price data)
        if (dataset === 'btc' && result.data.length > 0) {
            const timestamps = result.data.map(d => new Date(d[0]));
            appState.globalDateExtent = d3.extent(timestamps);
            console.log(`Global date extent calculated: ${appState.globalDateExtent[0]} to ${appState.globalDateExtent[1]}`);
        }

        // Fetch overlay data (moving averages) if any are selected
        const overlays = [];
        const selectedOverlays = appState.overlaySelections[dataset] || [];

        for (const overlayName of selectedOverlays) {
            try {
                console.log(`Fetching overlay data: ${overlayName}`);
                const overlayResult = await getDatasetData(overlayName, days);

                if (overlayResult && overlayResult.data && overlayResult.data.length > 0) {
                    overlays.push({
                        data: overlayResult.data,
                        metadata: overlayResult.metadata
                    });
                    console.log(`Loaded overlay ${overlayName}: ${overlayResult.data.length} points`);
                }
            } catch (overlayError) {
                console.warn(`Failed to load overlay ${overlayName}:`, overlayError);
                // Continue loading other overlays even if one fails
            }
        }

        // Render chart with price data, overlays, regime background, and forced domain
        const regimeData = appState.regimeData[dataset] || null;
        const forcedDomain = appState.globalDateExtent || null;
        renderChart(dataset, result.data, overlays, regimeData, forcedDomain);

        // Clear loading message
        clearMessages(dataset);

    } catch (error) {
        console.error(`Error loading ${dataset} data:`, error);
        showErrorMessage(dataset, `Failed to load ${dataset.toUpperCase()} data. Please check server connection.`);
    }
}

/**
 * Fetch oscillator data and render oscillator chart
 * @param {string} asset - Asset name ('btc', 'eth', 'gold')
 */
async function loadOscillatorData(asset) {
    const days = appState.days[asset];
    const datasets = appState.selectedDatasets[asset].join(',');
    const mode = appState.compositeMode ? 'composite' : 'individual';
    const noiseLevel = appState.noiseLevel[asset];
    const normalizer = 'zscore';  // Always use zscore (regression divergence) normalizer

    if (!datasets) {
        console.log(`No datasets selected for ${asset} oscillator`);
        return;
    }

    console.log(`Fetching oscillator data for ${asset}: mode=${mode}, datasets=${datasets}, noise_level=${noiseLevel}, days=${days}`);

    try {
        // Build URL with mode and noise_level parameters
        const url = `/api/oscillator-data?asset=${asset}&datasets=${datasets}&days=${days}&normalizer=${normalizer}&mode=${mode}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        // Store data in state
        appState.oscillatorData[asset] = result;

        // Handle composite mode vs individual mode
        if (mode === 'composite') {
            if (!result || !result.composite || !result.regime) {
                throw new Error('Invalid composite oscillator data received');
            }

            console.log(`Received composite oscillator data for ${asset}`);
            console.log(`  Composite points: ${result.composite.data.length}`);
            console.log(`  Regime points: ${result.regime.data.length}`);
            console.log(`  Breakdown oscillators:`, result.breakdown ? Object.keys(result.breakdown) : 'none');

            // Store regime data for price chart background
            appState.regimeData[asset] = {
                data: result.regime.data,
                metadata: result.regime.metadata
            };

            // Re-render price chart with regime background if chart data is already loaded
            if (appState.chartData[asset]) {
                const overlays = [];
                const forcedDomain = appState.globalDateExtent || null;
                // Re-fetch overlays (simplified - just pass empty for now, chart will handle)
                renderChart(asset, appState.chartData[asset], overlays, appState.regimeData[asset], forcedDomain);
            }

            // Render composite oscillator chart with regime background and forced domain
            const forcedDomain = appState.globalDateExtent || null;
            renderOscillatorChart(asset, {
                composite: result.composite.data,
                regime: result.regime.data,
                metadata: {
                    composite: result.composite.metadata,
                    regime: result.regime.metadata
                }
            }, appState.datasetColors, true, forcedDomain);  // true = composite mode

            // Render breakdown chart if data is available
            if (result.breakdown && Object.keys(result.breakdown).length > 0) {
                // Initialize breakdown chart if not already done
                if (!appState.breakdownInitialized[asset]) {
                    const containerId = `${asset}-breakdown-oscillator-container`;
                    initBreakdownChart(containerId, asset);
                    appState.breakdownInitialized[asset] = true;
                }

                // Render breakdown chart with forced domain
                const forcedDomain = appState.globalDateExtent || null;
                renderBreakdownChart(asset, result.breakdown, forcedDomain);
            }

        } else {
            // Individual mode (existing logic)
            if (!result || !result.datasets) {
                throw new Error('Invalid oscillator data received');
            }

            console.log(`Received oscillator data for ${asset}:`, Object.keys(result.datasets));

            // Prepare data for rendering
            const datasetsData = {};
            Object.entries(result.datasets).forEach(([datasetName, datasetInfo]) => {
                datasetsData[datasetName] = datasetInfo.data;
            });

            // Render oscillator chart (individual mode)
            renderOscillatorChart(asset, datasetsData, appState.datasetColors, false);  // false = individual mode
        }

    } catch (error) {
        console.error(`Error loading oscillator data for ${asset}:`, error);
    }
}

/**
 * Load breakdown oscillator data (Momentum: RSI, MACD, ADX, ATR)
 */
async function loadBreakdownOscillatorData(asset) {
    const days = appState.days[asset];
    const datasets = 'rsi,adx';  // Only RSI + ADX
    const mode = 'composite';  // Use composite mode for normalization
    const noiseLevel = appState.noiseLevel[asset];  // Unified noise level
    const normalizer = 'zscore';

    console.log(`Fetching breakdown oscillator data for ${asset}: datasets=${datasets}, noise_level=${noiseLevel}, days=${days}`);

    try {
        // Build URL
        const url = `/api/oscillator-data?asset=${asset}&datasets=${datasets}&days=${days}&normalizer=${normalizer}&mode=${mode}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (!result || !result.breakdown) {
            throw new Error('Invalid breakdown oscillator data received');
        }

        console.log(`Received breakdown oscillator data for ${asset}:`, Object.keys(result.breakdown));

        // Initialize breakdown chart if not already done
        const containerId = `breakdown-${asset}-oscillator-container`;
        const breakdownKey = `breakdown-${asset}`;
        if (!appState.breakdownInitialized[breakdownKey]) {
            initBreakdownChart(containerId, breakdownKey);
            appState.breakdownInitialized[breakdownKey] = true;
        }

        // Render breakdown chart with all 4 oscillators and forced domain
        const forcedDomain = appState.globalDateExtent || null;
        renderBreakdownChart(breakdownKey, result.breakdown, forcedDomain);

    } catch (error) {
        console.error(`Error loading breakdown oscillator data for ${asset}:`, error);
    }
}

/**
 * Load price oscillator data (DXY, Gold, SPX)
 * @param {string} asset - Asset name (e.g., 'btc')
 */
async function loadBreakdownPriceOscillatorData(asset) {
    const days = appState.days[asset];
    const datasets = 'dxy_price_yfinance,gold_price_oscillator,spx_price_fmp';  // Price oscillators (market hours only)
    const mode = 'composite';  // Use composite mode for normalization
    const noiseLevel = appState.noiseLevel[asset];  // Unified noise level
    const normalizer = 'zscore';

    console.log(`Fetching breakdown price oscillator data for ${asset}: datasets=${datasets}, noise_level=${noiseLevel}, days=${days}`);

    try {
        // Build URL
        const url = `/api/oscillator-data?asset=${asset}&datasets=${datasets}&days=${days}&normalizer=${normalizer}&mode=${mode}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (!result || !result.breakdown) {
            throw new Error('Invalid breakdown price oscillator data received');
        }

        console.log(`Received breakdown price oscillator data for ${asset}:`, Object.keys(result.breakdown));

        // Initialize price oscillator chart if not already done
        const containerId = `breakdown-price-oscillator-container`;
        const breakdownKey = `breakdown-price-${asset}`;
        if (!appState.breakdownPriceInitialized[asset]) {
            initBreakdownChart(containerId, breakdownKey);
            appState.breakdownPriceInitialized[asset] = true;
        }

        // Render price oscillator chart with DXY, Gold, SPX and forced domain
        const forcedDomain = appState.globalDateExtent || null;
        renderBreakdownChart(breakdownKey, result.breakdown, forcedDomain);

    } catch (error) {
        console.error(`Error loading breakdown price oscillator data for ${asset}:`, error);
    }
}

/**
 * Load macro oscillator data (ETH, BTC.D, USDT.D)
 * @param {string} asset - Asset name (e.g., 'btc')
 */
async function loadMacroOscillatorData(asset) {
    const days = appState.days[asset];
    const datasets = 'eth_price_alpaca,btc_dominance_cmc,usdt_dominance_cmc';  // Macro oscillators (24/7 crypto)
    const mode = 'composite';  // Use composite mode for normalization
    const noiseLevel = appState.noiseLevel[asset];  // Unified noise level
    const normalizer = 'zscore';

    console.log(`Fetching breakdown macro oscillator data for ${asset}: datasets=${datasets}, noise_level=${noiseLevel}, days=${days}`);

    try {
        // Build URL
        const url = `/api/oscillator-data?asset=${asset}&datasets=${datasets}&days=${days}&normalizer=${normalizer}&mode=${mode}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (!result || !result.breakdown) {
            throw new Error('Invalid breakdown macro oscillator data received');
        }

        console.log(`Received breakdown macro oscillator data for ${asset}:`, Object.keys(result.breakdown));

        // Initialize macro oscillator chart if not already done
        const containerId = `breakdown-macro-oscillator-container`;
        const breakdownKey = `breakdown-macro-${asset}`;
        if (!appState.breakdownMacroInitialized[asset]) {
            initBreakdownChart(containerId, breakdownKey);
            appState.breakdownMacroInitialized[asset] = true;
        }

        // Render macro oscillator chart with ETH, BTC.D, USDT.D and forced domain
        const forcedDomain = appState.globalDateExtent || null;
        renderBreakdownChart(breakdownKey, result.breakdown, forcedDomain);

    } catch (error) {
        console.error(`Error loading breakdown macro oscillator data for ${asset}:`, error);
    }
}

/**
 * Load derivatives oscillator data (DVOL Index, Basis Spread)
 * @param {string} asset - Asset name (e.g., 'btc')
 */
async function loadBreakdownDerivativesOscillatorData(asset) {
    const days = appState.days[asset];
    const datasets = 'dvol_index_deribit,basis_spread_binance';  // Derivatives oscillators
    const mode = 'composite';  // Use composite mode for normalization
    const noiseLevel = appState.noiseLevel[asset];  // Unified noise level
    const normalizer = 'zscore';

    console.log(`Fetching breakdown derivatives oscillator data for ${asset}: datasets=${datasets}, noise_level=${noiseLevel}, days=${days}`);

    try {
        // Build URL
        const url = `/api/oscillator-data?asset=${asset}&datasets=${datasets}&days=${days}&normalizer=${normalizer}&mode=${mode}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (!result || !result.breakdown) {
            throw new Error('Invalid breakdown derivatives oscillator data received');
        }

        console.log(`Received breakdown derivatives oscillator data for ${asset}:`, Object.keys(result.breakdown));

        // Initialize derivatives oscillator chart if not already done
        const containerId = `breakdown-derivatives-oscillator-container`;
        const breakdownKey = `breakdown-derivatives-${asset}`;
        if (!appState.breakdownDerivativesInitialized[asset]) {
            initBreakdownChart(containerId, breakdownKey);
            appState.breakdownDerivativesInitialized[asset] = true;
        }

        // Render derivatives oscillator chart with DVOL, Basis Spread and forced domain
        const forcedDomain = appState.globalDateExtent || null;
        renderBreakdownChart(breakdownKey, result.breakdown, forcedDomain);

    } catch (error) {
        console.error(`Error loading breakdown derivatives oscillator data for ${asset}:`, error);
    }
}

/**
 * Show loading message in chart container
 * @param {string} dataset - Dataset name
 */
function showLoadingMessage(dataset) {
    const container = document.getElementById(`${dataset}-chart-container`);

    // Remove existing messages
    clearMessages(dataset);

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'loading';
    loadingDiv.textContent = `Loading ${dataset.toUpperCase()} data...`;
    container.appendChild(loadingDiv);
}

/**
 * Show error message in chart container
 * @param {string} dataset - Dataset name
 * @param {string} message - Error message
 */
function showErrorMessage(dataset, message) {
    const container = document.getElementById(`${dataset}-chart-container`);

    // Remove existing messages
    clearMessages(dataset);

    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.innerHTML = `
        <div style="text-align: center;">
            <div style="font-size: 24px; margin-bottom: 10px;">⚠</div>
            <div>${message}</div>
        </div>
    `;
    container.appendChild(errorDiv);
}

/**
 * Clear all messages from chart container
 * @param {string} dataset - Dataset name
 */
function clearMessages(dataset) {
    const container = document.getElementById(`${dataset}-chart-container`);

    // Remove loading and error messages
    const messages = container.querySelectorAll('.loading, .error');
    messages.forEach(msg => msg.remove());
}

/**
 * Fetch funding rate data and render chart
 * @param {string} asset - Asset name ('btc', 'eth', etc.)
 */
async function loadFundingRateData(asset) {
    const days = appState.days[asset];

    console.log(`Fetching funding rate data for ${asset}: ${days} days`);

    try {
        // Fetch funding rate data from API
        const result = await getDatasetData(`funding_rate_${asset}`, days);

        if (!result || !result.data || result.data.length === 0) {
            console.warn(`No funding rate data available for ${asset}`);
            return;
        }

        console.log(`Received ${result.data.length} funding rate data points for ${asset}`);

        // Store data in state
        appState.fundingRateData[asset] = result.data;

        // Render funding rate chart with forced domain
        const forcedDomain = appState.globalDateExtent || null;
        renderFundingRateChart(asset, result.data, forcedDomain);

    } catch (error) {
        console.error(`Error loading funding rate data for ${asset}:`, error);
    }
}

// Start the application
main();
