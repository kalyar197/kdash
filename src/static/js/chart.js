/**
 * Chart Module - Candlestick chart rendering for OHLCV data
 * Uses D3.js for visualization
 */

import { syncOscillatorZoom } from './oscillator.js';

// Chart state for each dataset
const chartInstances = {};

/**
 * Initialize a chart for a specific dataset
 * @param {string} containerId - DOM ID of the chart container
 * @param {string} dataset - Dataset name ('btc' or 'eth')
 * @param {string} color - Base color for the chart
 */
export function initChart(containerId, dataset, color) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container ${containerId} not found`);
        return;
    }

    // Clear any existing content
    container.innerHTML = '';

    // Get container dimensions
    const containerRect = container.getBoundingClientRect();
    const margin = { top: 20, right: 60, bottom: 40, left: 60 };
    const width = containerRect.width - margin.left - margin.right;
    const height = containerRect.height - margin.top - margin.bottom;

    // Create SVG with viewBox for responsive scaling
    const svg = d3.select(`#${containerId}`)
        .append('svg')
        .attr('width', containerRect.width)
        .attr('height', containerRect.height)
        .attr('viewBox', `0 0 ${containerRect.width} ${containerRect.height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet');

    // Create main group
    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create clip path for zoom
    g.append('defs').append('clipPath')
        .attr('id', `clip-${dataset}`)
        .append('rect')
        .attr('width', width)
        .attr('height', height);

    // Create groups for different elements
    const gridGroup = g.append('g').attr('class', 'grid');
    const candlesGroup = g.append('g').attr('class', 'candles').attr('clip-path', `url(#clip-${dataset})`);
    const overlaysGroup = g.append('g').attr('class', 'overlays').attr('clip-path', `url(#clip-${dataset})`);
    const xAxisGroup = g.append('g').attr('class', 'x-axis').attr('transform', `translate(0,${height})`);
    const yAxisGroup = g.append('g').attr('class', 'y-axis');

    // Crosshair elements
    const crosshairGroup = g.append('g').attr('class', 'crosshair').style('display', 'none');
    crosshairGroup.append('line').attr('class', 'crosshair-line crosshair-x');
    crosshairGroup.append('line').attr('class', 'crosshair-line crosshair-y');

    // Store chart instance
    chartInstances[dataset] = {
        svg,
        g,
        width,
        height,
        margin,
        color,
        gridGroup,
        candlesGroup,
        overlaysGroup,
        xAxisGroup,
        yAxisGroup,
        crosshairGroup,
        xScale: null,
        yScale: null,
        zoom: null,
        currentTransform: d3.zoomIdentity,
        overlayData: []  // Store overlay data for zoom updates
    };

    console.log(`Chart initialized for ${dataset}`);
}

/**
 * Render candlestick chart with OHLCV data and optional overlays
 * @param {string} dataset - Dataset name ('btc', 'eth', or 'gold')
 * @param {Array} data - OHLCV data [[timestamp, open, high, low, close, volume], ...]
 * @param {Array} overlays - Optional array of overlay datasets [{data: [[ts, value], ...], metadata: {...}}, ...]
 * @param {Object} regimeData - Optional regime data for background shading
 * @param {Array} forcedDomain - Optional forced x-axis domain [minDate, maxDate] for chart alignment
 */
export function renderChart(dataset, data, overlays = [], regimeData = null, forcedDomain = null) {
    const chart = chartInstances[dataset];
    if (!chart) {
        console.error(`Chart instance for ${dataset} not found`);
        return;
    }

    if (!data || data.length === 0) {
        console.warn(`No data to render for ${dataset}`);
        showChartMessage(dataset, 'No data available');
        return;
    }

    console.log(`Rendering ${data.length} candles for ${dataset}`);
    if (overlays && overlays.length > 0) {
        console.log(`Rendering ${overlays.length} overlay(s) for ${dataset}`);
    }
    if (regimeData) {
        console.log(`Rendering regime background for ${dataset}`);
    }

    // Store overlay data and regime data for zoom updates
    chart.overlayData = overlays || [];
    chart.regimeData = regimeData;

    // Create scales
    // Use forced domain if provided, otherwise calculate from data
    const xDomain = forcedDomain || d3.extent(data, d => new Date(d[0]));
    chart.xScale = d3.scaleTime()
        .domain(xDomain)
        .range([0, chart.width]);

    // Find price range (considering high/low and overlay values)
    const prices = data.flatMap(d => [d[2], d[3]]); // high, low

    // Include overlay values in Y-domain calculation
    if (overlays && overlays.length > 0) {
        overlays.forEach(overlay => {
            if (overlay.data && overlay.data.length > 0) {
                const overlayValues = overlay.data.map(d => d[1]);
                prices.push(...overlayValues);
            }
        });
    }

    chart.yScale = d3.scaleLinear()
        .domain([d3.min(prices) * 0.98, d3.max(prices) * 1.02])
        .range([chart.height, 0]);

    // Create axes
    const xAxis = d3.axisBottom(chart.xScale)
        .ticks(8)
        .tickFormat(d3.timeFormat('%b %d'));

    const yAxis = d3.axisLeft(chart.yScale)
        .ticks(8)
        .tickFormat(d => `$${d.toLocaleString()}`);

    // Draw grid
    chart.gridGroup.selectAll('*').remove();
    chart.gridGroup.selectAll('.grid-line-x')
        .data(chart.xScale.ticks(8))
        .enter()
        .append('line')
        .attr('class', 'grid-line-x')
        .attr('x1', d => chart.xScale(d))
        .attr('x2', d => chart.xScale(d))
        .attr('y1', 0)
        .attr('y2', chart.height)
        .style('stroke', '#222')
        .style('stroke-dasharray', '2,2');

    chart.gridGroup.selectAll('.grid-line-y')
        .data(chart.yScale.ticks(8))
        .enter()
        .append('line')
        .attr('class', 'grid-line-y')
        .attr('x1', 0)
        .attr('x2', chart.width)
        .attr('y1', d => chart.yScale(d))
        .attr('y2', d => chart.yScale(d))
        .style('stroke', '#222')
        .style('stroke-dasharray', '2,2');

    // Calculate candle width based on data density
    const candleWidth = Math.max(2, Math.min(12, chart.width / data.length * 0.7));

    // Clear existing candlesticks and regime backgrounds
    chart.candlesGroup.selectAll('*').remove();

    // Draw regime background FIRST (behind candlesticks)
    if (regimeData && regimeData.data && regimeData.metadata) {
        renderPriceChartRegimeBackground(chart, regimeData.data, regimeData.metadata);
    }

    // Draw wicks (high-low lines)
    chart.candlesGroup.selectAll('.wick')
        .data(data)
        .enter()
        .append('line')
        .attr('class', 'wick')
        .attr('x1', d => chart.xScale(new Date(d[0])))
        .attr('x2', d => chart.xScale(new Date(d[0])))
        .attr('y1', d => chart.yScale(d[2])) // high
        .attr('y2', d => chart.yScale(d[3])) // low
        .style('stroke', d => d[4] >= d[1] ? '#26a69a' : '#ef5350') // close >= open ? green : red
        .style('stroke-width', 1);

    // Draw candle bodies (open-close rectangles)
    chart.candlesGroup.selectAll('.candle')
        .data(data)
        .enter()
        .append('rect')
        .attr('class', 'candle')
        .attr('x', d => chart.xScale(new Date(d[0])) - candleWidth / 2)
        .attr('y', d => chart.yScale(Math.max(d[1], d[4]))) // top of candle
        .attr('width', candleWidth)
        .attr('height', d => {
            const height = Math.abs(chart.yScale(d[1]) - chart.yScale(d[4]));
            return height < 1 ? 1 : height; // Minimum 1px for doji candles
        })
        .style('fill', d => d[4] >= d[1] ? '#26a69a' : '#ef5350') // close >= open ? green : red
        .style('stroke', d => d[4] >= d[1] ? '#26a69a' : '#ef5350')
        .style('stroke-width', 0.5);

    // Update axes
    chart.xAxisGroup.call(xAxis)
        .selectAll('text')
        .style('fill', '#888')
        .style('font-size', '11px');

    chart.yAxisGroup.call(yAxis)
        .selectAll('text')
        .style('fill', '#888')
        .style('font-size', '11px');

    // Style axis lines
    chart.xAxisGroup.selectAll('path, line').style('stroke', '#333');
    chart.yAxisGroup.selectAll('path, line').style('stroke', '#333');

    // Render overlays (moving averages, etc.)
    // Always call renderOverlays to clear old overlays even if array is empty
    renderOverlays(dataset, overlays);

    // Add zoom behavior
    setupZoom(dataset, data);

    // Add hover behavior
    setupCrosshair(dataset, data);
}

/**
 * Render regime background for price chart
 * @param {Object} chart - Chart instance
 * @param {Array} regimeData - Regime data [[timestamp, regime], ...]
 * @param {Object} metadata - Regime metadata with states info
 */
function renderPriceChartRegimeBackground(chart, regimeData, metadata) {
    if (!regimeData || regimeData.length === 0) return;

    const states = metadata.states;

    // Clear existing regime backgrounds
    chart.candlesGroup.selectAll('[class*="regime-bg"]').remove();

    // Group consecutive timestamps with same regime
    const regimeSegments = [];
    let currentSegment = null;

    regimeData.forEach((d, i) => {
        const timestamp = d[0];
        const regime = d[1];

        if (!currentSegment || currentSegment.regime !== regime) {
            // Start new segment
            if (currentSegment) {
                regimeSegments.push(currentSegment);
            }
            currentSegment = {
                regime: regime,
                startTime: timestamp,
                endTime: timestamp
            };
        } else {
            // Extend current segment
            currentSegment.endTime = timestamp;
        }
    });

    // Push last segment
    if (currentSegment) {
        regimeSegments.push(currentSegment);
    }

    // Store regime segments and metadata for zoom updates
    chart.regimeSegments = regimeSegments;
    chart.regimeMetadata = metadata;

    // Render background rectangles (insert at beginning, behind candlesticks)
    regimeSegments.forEach((segment, index) => {
        const state = states[segment.regime];
        if (!state) return;

        const x1 = chart.xScale(new Date(segment.startTime));
        const x2 = chart.xScale(new Date(segment.endTime));
        const width = x2 - x1 || 2;  // Minimum width of 2px

        chart.candlesGroup.insert('rect', ':first-child')  // Insert at beginning (background)
            .attr('class', `regime-bg regime-bg-${segment.regime}`)
            .attr('data-regime-index', index)  // For zoom updates
            .attr('x', x1)
            .attr('y', 0)
            .attr('width', width)
            .attr('height', chart.height)
            .style('fill', state.color)
            .style('opacity', 1);
    });
}

/**
 * Update regime background rectangles with new X scale (for zoom sync)
 * @param {Object} chart - Chart instance
 * @param {Function} newXScale - Transformed X scale
 */
function updatePriceChartRegimeRectangles(chart, newXScale) {
    if (!chart.regimeSegments || chart.regimeSegments.length === 0) return;

    const states = chart.regimeMetadata.states;

    // Update all regime rectangles using data-regime-index attribute
    chart.regimeSegments.forEach((segment, index) => {
        const state = states[segment.regime];
        if (!state) return;

        const x1 = newXScale(new Date(segment.startTime));
        const x2 = newXScale(new Date(segment.endTime));
        const width = x2 - x1 || 2;  // Minimum width of 2px

        // Update rectangle by data-regime-index attribute
        chart.candlesGroup.select(`[data-regime-index="${index}"]`)
            .attr('x', x1)
            .attr('width', width);
    });
}

/**
 * Render overlay lines (moving averages, etc.) or dots (Parabolic SAR)
 * @param {string} dataset - Dataset name
 * @param {Array} overlays - Array of overlay datasets [{data: [[ts, value], ...], metadata: {...}}, ...]
 */
function renderOverlays(dataset, overlays) {
    const chart = chartInstances[dataset];
    if (!chart) {
        return;
    }

    // Always clear existing overlays first
    chart.overlaysGroup.selectAll('*').remove();

    // If no overlays to render, we're done (already cleared)
    if (!overlays || overlays.length === 0) {
        return;
    }

    // Render each overlay
    overlays.forEach((overlay, index) => {
        if (!overlay.data || overlay.data.length === 0) {
            return;
        }

        const metadata = overlay.metadata || {};
        const renderType = metadata.renderType || 'line';
        const label = metadata.label || `Overlay ${index + 1}`;

        if (renderType === 'dots') {
            // Render as dots (e.g., Parabolic SAR)
            const dotRadius = metadata.dotRadius || 3;
            const dotColors = metadata.dotColors || { bullish: '#00D9FF', bearish: '#FF1493' };

            chart.overlaysGroup.selectAll(`.sar-dot-${index}`)
                .data(overlay.data)
                .enter()
                .append('circle')
                .attr('class', `sar-dot sar-dot-${index}`)
                .attr('cx', d => chart.xScale(new Date(d[0])))
                .attr('cy', d => chart.yScale(d[1]))
                .attr('r', dotRadius)
                .style('fill', d => {
                    // d[2] is trend: 1 = bullish (below price), -1 = bearish (above price)
                    const trend = d[2] || 1;
                    return trend === 1 ? dotColors.bullish : dotColors.bearish;
                })
                .style('stroke', 'none')
                .style('opacity', 0.85);

            console.log(`Rendered overlay dots: ${label} with ${overlay.data.length} points`);
        } else {
            // Render as line (default for SMA, etc.)
            const color = metadata.color || '#888';
            const strokeWidth = metadata.strokeWidth || 2;

            // Create line generator
            const line = d3.line()
                .x(d => chart.xScale(new Date(d[0])))
                .y(d => chart.yScale(d[1]))
                .defined(d => d[1] !== null && d[1] !== undefined && !isNaN(d[1]))
                .curve(d3.curveLinear);

            // Draw the line
            chart.overlaysGroup.append('path')
                .datum(overlay.data)
                .attr('class', `overlay-line overlay-${index}`)
                .attr('d', line)
                .style('fill', 'none')
                .style('stroke', color)
                .style('stroke-width', strokeWidth)
                .style('opacity', 0.85);

            console.log(`Rendered overlay line: ${label} with ${overlay.data.length} points`);
        }
    });
}

/**
 * Setup zoom and pan behavior
 * @param {string} dataset - Dataset name
 * @param {Array} data - OHLCV data
 */
function setupZoom(dataset, data) {
    const chart = chartInstances[dataset];

    // Remove existing zoom overlay
    chart.g.selectAll('.zoom-overlay').remove();

    // Create zoom behavior
    chart.zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .translateExtent([[0, 0], [chart.width, chart.height]])
        .extent([[0, 0], [chart.width, chart.height]])
        .on('zoom', (event) => {
            chart.currentTransform = event.transform;
            updateZoom(dataset, data, event.transform);
            // Sync oscillator chart zoom
            syncOscillatorZoom(dataset, event.transform);
        });

    // Add zoom overlay
    chart.g.append('rect')
        .attr('class', 'zoom-overlay')
        .attr('width', chart.width)
        .attr('height', chart.height)
        .style('fill', 'none')
        .style('pointer-events', 'all')
        .call(chart.zoom);

    // Setup zoom controls
    setupZoomControls(dataset, data);
}

/**
 * Update chart with zoom transform
 * @param {string} dataset - Dataset name
 * @param {Array} data - OHLCV data
 * @param {Object} transform - D3 zoom transform
 */
function updateZoom(dataset, data, transform) {
    const chart = chartInstances[dataset];

    // Update scales with transform
    const newXScale = transform.rescaleX(chart.xScale);

    // Update axes
    const xAxis = d3.axisBottom(newXScale)
        .ticks(8)
        .tickFormat(d3.timeFormat('%b %d'));

    chart.xAxisGroup.call(xAxis)
        .selectAll('text')
        .style('fill', '#888');

    chart.xAxisGroup.selectAll('path, line').style('stroke', '#333');

    // Update candles position
    const candleWidth = Math.max(2, Math.min(12, chart.width / data.length * 0.7)) * transform.k;

    chart.candlesGroup.selectAll('.wick')
        .attr('x1', d => newXScale(new Date(d[0])))
        .attr('x2', d => newXScale(new Date(d[0])));

    chart.candlesGroup.selectAll('.candle')
        .attr('x', d => newXScale(new Date(d[0])) - candleWidth / 2)
        .attr('width', candleWidth);

    // Update overlay lines and dots position
    if (chart.overlayData && chart.overlayData.length > 0) {
        chart.overlayData.forEach((overlay, index) => {
            if (!overlay.data || overlay.data.length === 0) {
                return;
            }

            const metadata = overlay.metadata || {};
            const renderType = metadata.renderType || 'line';

            if (renderType === 'dots') {
                // Update dot positions (keep radius fixed at 3px)
                chart.overlaysGroup.selectAll(`.sar-dot-${index}`)
                    .attr('cx', d => newXScale(new Date(d[0])));
            } else {
                // Update line path
                const line = d3.line()
                    .x(d => newXScale(new Date(d[0])))
                    .y(d => chart.yScale(d[1]))
                    .defined(d => d[1] !== null && d[1] !== undefined && !isNaN(d[1]))
                    .curve(d3.curveLinear);

                chart.overlaysGroup.select(`.overlay-${index}`)
                    .datum(overlay.data)
                    .attr('d', line);
            }
        });
    }

    // Update regime background rectangles position
    updatePriceChartRegimeRectangles(chart, newXScale);
}

/**
 * Setup zoom control buttons
 * @param {string} dataset - Dataset name
 * @param {Array} data - OHLCV data
 */
function setupZoomControls(dataset, data) {
    const chart = chartInstances[dataset];
    const containerSelector = dataset === 'btc' ? '#btc-chart-container' : '#eth-chart-container';

    // Reset zoom
    d3.select(`${containerSelector} .reset-zoom`).on('click', () => {
        chart.svg.transition().duration(750).call(chart.zoom.transform, d3.zoomIdentity);
    });

    // Zoom in
    d3.select(`${containerSelector} .zoom-in`).on('click', () => {
        chart.svg.transition().duration(300).call(chart.zoom.scaleBy, 1.3);
    });

    // Zoom out
    d3.select(`${containerSelector} .zoom-out`).on('click', () => {
        chart.svg.transition().duration(300).call(chart.zoom.scaleBy, 0.77);
    });
}

/**
 * Setup crosshair hover behavior
 * @param {string} dataset - Dataset name
 * @param {Array} data - OHLCV data
 */
function setupCrosshair(dataset, data) {
    const chart = chartInstances[dataset];
    const tooltip = d3.select('#tooltip');

    chart.g.select('.zoom-overlay')
        .on('mousemove', function(event) {
            const [mx, my] = d3.pointer(event);

            // Transform mouse coordinates if zoomed
            const x = chart.currentTransform.invertX(mx);
            const dateAtMouse = chart.xScale.invert(x);

            // Find closest data point
            const bisect = d3.bisector(d => new Date(d[0])).left;
            const index = bisect(data, dateAtMouse);
            const d = data[index];

            if (d) {
                // Show crosshair
                chart.crosshairGroup.style('display', null);

                chart.crosshairGroup.select('.crosshair-x')
                    .attr('x1', mx)
                    .attr('x2', mx)
                    .attr('y1', 0)
                    .attr('y2', chart.height);

                chart.crosshairGroup.select('.crosshair-y')
                    .attr('x1', 0)
                    .attr('x2', chart.width)
                    .attr('y1', my)
                    .attr('y2', my);

                // Show tooltip
                const tooltipHTML = `
                    <div class="tooltip-header">${new Date(d[0]).toLocaleDateString()}</div>
                    <div class="tooltip-row">
                        <span>Open:</span>
                        <span class="tooltip-value">$${d[1].toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="tooltip-row">
                        <span>High:</span>
                        <span class="tooltip-value">$${d[2].toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="tooltip-row">
                        <span>Low:</span>
                        <span class="tooltip-value">$${d[3].toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="tooltip-row">
                        <span>Close:</span>
                        <span class="tooltip-value">$${d[4].toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="tooltip-row">
                        <span>Volume:</span>
                        <span class="tooltip-value">${d[5].toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                `;

                tooltip.html(tooltipHTML)
                    .classed('show', true)
                    .style('left', (event.pageX + 15) + 'px')
                    .style('top', (event.pageY - 15) + 'px');
            }
        })
        .on('mouseleave', () => {
            chart.crosshairGroup.style('display', 'none');
            tooltip.classed('show', false);
        });
}

/**
 * Show a message in the chart area
 * @param {string} dataset - Dataset name
 * @param {string} message - Message to display
 */
function showChartMessage(dataset, message) {
    const containerSelector = dataset === 'btc' ? '#btc-chart-container' : '#eth-chart-container';
    const container = document.querySelector(containerSelector);

    const messageDiv = document.createElement('div');
    messageDiv.className = 'loading';
    messageDiv.textContent = message;
    container.appendChild(messageDiv);
}

// ============================================================================
// FUNDING RATE CHART
// ============================================================================

// Funding rate chart instances
const fundingRateChartInstances = {};

/**
 * Initialize funding rate chart
 * @param {string} containerId - Container DOM ID
 * @param {string} dataset - Dataset name ('btc', 'eth', etc.)
 */
export function initFundingRateChart(containerId, dataset) {
    console.log(`Initializing funding rate chart: ${containerId}`);

    const container = d3.select(`#${containerId}`);
    const containerNode = container.node();

    if (!containerNode) {
        console.error(`Container not found: ${containerId}`);
        return;
    }

    // Chart dimensions
    const margin = { top: 30, right: 60, bottom: 40, left: 60 };
    const width = containerNode.offsetWidth - margin.left - margin.right;
    const height = containerNode.offsetHeight - margin.top - margin.bottom;

    // Clear any existing SVG (preserve zoom controls)
    container.selectAll('svg').remove();

    // Create SVG with viewBox for responsive scaling
    const svg = container.append('svg')
        .attr('width', containerNode.offsetWidth)
        .attr('height', containerNode.offsetHeight)
        .attr('viewBox', `0 0 ${containerNode.offsetWidth} ${containerNode.offsetHeight}`)
        .attr('preserveAspectRatio', 'xMidYMid meet');

    // Create main group with margins
    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create clip path for chart area
    g.append('defs').append('clipPath')
        .attr('id', `clip-funding-${dataset}`)
        .append('rect')
        .attr('width', width)
        .attr('height', height);

    // Chart groups (order matters for layering)
    const referenceGroup = g.append('g').attr('class', 'reference-lines');
    const areaGroup = g.append('g').attr('class', 'area-group').attr('clip-path', `url(#clip-funding-${dataset})`);
    const lineGroup = g.append('g').attr('class', 'line-group').attr('clip-path', `url(#clip-funding-${dataset})`);
    const axisGroup = g.append('g').attr('class', 'axis-group');
    const crosshairGroup = g.append('g').attr('class', 'crosshair').style('display', 'none');

    // Crosshair lines
    crosshairGroup.append('line').attr('class', 'crosshair-x').attr('stroke', '#888').attr('stroke-width', 1).attr('stroke-dasharray', '3,3');
    crosshairGroup.append('line').attr('class', 'crosshair-y').attr('stroke', '#888').attr('stroke-width', 1).attr('stroke-dasharray', '3,3');

    // Add zoom overlay (transparent rect for interaction)
    const zoomOverlay = g.append('rect')
        .attr('class', 'zoom-overlay')
        .attr('width', width)
        .attr('height', height)
        .style('fill', 'none')
        .style('pointer-events', 'all');

    // Store chart instance
    fundingRateChartInstances[dataset] = {
        svg, g, width, height, margin,
        referenceGroup, areaGroup, lineGroup, axisGroup, crosshairGroup, zoomOverlay,
        xScale: null,
        yScale: null,
        data: null
    };

    console.log(`Funding rate chart initialized for ${dataset}`);
}

/**
 * Render funding rate chart with color-coded sentiment
 * @param {string} dataset - Dataset name
 * @param {Array} data - Funding rate data [[timestamp, rate_percentage], ...]
 * @param {Array} forcedDomain - Optional forced x-axis domain [minDate, maxDate] for chart alignment
 */
export function renderFundingRateChart(dataset, data, forcedDomain = null) {
    const chart = fundingRateChartInstances[dataset];

    if (!chart) {
        console.error(`Funding rate chart not initialized for ${dataset}`);
        return;
    }

    if (!data || data.length === 0) {
        console.warn(`No funding rate data available for ${dataset}`);
        return;
    }

    console.log(`Rendering funding rate chart for ${dataset} with ${data.length} points`);

    // Store data
    chart.data = data;

    // Create scales
    // Use forced domain if provided, otherwise calculate from data
    const xExtent = forcedDomain || d3.extent(data, d => new Date(d[0]));
    const yExtent = d3.extent(data, d => d[1]);

    // Add padding to Y domain (10% on each side)
    const yPadding = (yExtent[1] - yExtent[0]) * 0.1;
    const yDomain = [yExtent[0] - yPadding, yExtent[1] + yPadding];

    chart.xScale = d3.scaleTime()
        .domain(xExtent)
        .range([0, chart.width]);

    chart.yScale = d3.scaleLinear()
        .domain(yDomain)
        .range([chart.height, 0]);

    // Clear previous content
    chart.referenceGroup.selectAll('*').remove();
    chart.areaGroup.selectAll('*').remove();
    chart.lineGroup.selectAll('*').remove();
    chart.axisGroup.selectAll('*').remove();

    // Define color thresholds
    const positiveThreshold = 0.01;  // 0.01%
    const negativeThreshold = -0.01; // -0.01%

    // Color function based on value
    const getColor = (value) => {
        if (value > positiveThreshold) return '#26a69a';  // Green (bullish)
        if (value < negativeThreshold) return '#ef5350';  // Red (bearish)
        return '#888888';  // Gray (neutral)
    };

    // Render reference lines
    const referenceLines = [
        { value: positiveThreshold, label: '+0.01%', color: '#26a69a' },
        { value: 0, label: '0%', color: '#888' },
        { value: negativeThreshold, label: '-0.01%', color: '#ef5350' }
    ];

    referenceLines.forEach(line => {
        const y = chart.yScale(line.value);

        // Horizontal line
        chart.referenceGroup.append('line')
            .attr('x1', 0)
            .attr('x2', chart.width)
            .attr('y1', y)
            .attr('y2', y)
            .attr('stroke', line.color)
            .attr('stroke-width', line.value === 0 ? 2 : 1)
            .attr('stroke-opacity', line.value === 0 ? 0.5 : 0.3)
            .attr('stroke-dasharray', line.value === 0 ? '0' : '3,3');

        // Label (right side)
        chart.referenceGroup.append('text')
            .attr('x', chart.width + 5)
            .attr('y', y)
            .attr('dy', '0.32em')
            .attr('fill', line.color)
            .attr('font-size', '10px')
            .text(line.label);
    });

    // Render area fill (color segments)
    // Group data into segments by color
    const segments = [];
    let currentSegment = null;

    data.forEach((d, i) => {
        const color = getColor(d[1]);

        if (!currentSegment || currentSegment.color !== color) {
            // Start new segment
            if (currentSegment) {
                // Add transition point to previous segment
                currentSegment.data.push(d);
                segments.push(currentSegment);
            }
            currentSegment = { color, data: [d] };
        } else {
            // Continue current segment
            currentSegment.data.push(d);
        }
    });

    // Push final segment
    if (currentSegment) {
        segments.push(currentSegment);
    }

    // Area generator
    const area = d3.area()
        .x(d => chart.xScale(new Date(d[0])))
        .y0(chart.yScale(0))
        .y1(d => chart.yScale(d[1]))
        .curve(d3.curveLinear);

    // Render area segments
    segments.forEach((segment, i) => {
        chart.areaGroup.append('path')
            .datum(segment.data)
            .attr('class', `area-segment-${i}`)
            .attr('fill', segment.color)
            .attr('fill-opacity', 0.2)
            .attr('d', area);
    });

    // Line generator
    const line = d3.line()
        .x(d => chart.xScale(new Date(d[0])))
        .y(d => chart.yScale(d[1]))
        .curve(d3.curveLinear);

    // Render line segments (colored)
    segments.forEach((segment, i) => {
        chart.lineGroup.append('path')
            .datum(segment.data)
            .attr('class', `line-segment-${i}`)
            .attr('fill', 'none')
            .attr('stroke', segment.color)
            .attr('stroke-width', 2)
            .attr('d', line);
    });

    // X-axis
    const xAxis = d3.axisBottom(chart.xScale)
        .ticks(6)
        .tickFormat(d3.timeFormat('%b %d'));

    chart.axisGroup.append('g')
        .attr('class', 'x-axis')
        .attr('transform', `translate(0,${chart.height})`)
        .call(xAxis)
        .selectAll('text')
        .attr('fill', '#888')
        .style('font-size', '11px');

    // Y-axis
    const yAxis = d3.axisLeft(chart.yScale)
        .ticks(6)
        .tickFormat(d => `${d.toFixed(3)}%`);

    chart.axisGroup.append('g')
        .attr('class', 'y-axis')
        .call(yAxis)
        .selectAll('text')
        .attr('fill', '#888')
        .style('font-size', '11px');

    // Setup crosshair and tooltip
    setupFundingRateCrosshair(dataset, data);

    // Setup zoom and pan behavior (mouse interaction only, no button controls)
    setupFundingRateZoom(dataset);

    console.log(`Funding rate chart rendered for ${dataset}`);
}

/**
 * Setup crosshair and tooltip for funding rate chart
 * @param {string} dataset - Dataset name
 * @param {Array} data - Funding rate data
 */
function setupFundingRateCrosshair(dataset, data) {
    const chart = fundingRateChartInstances[dataset];
    const tooltip = d3.select('#tooltip');

    chart.zoomOverlay
        .on('mousemove', function(event) {
            const [mx, my] = d3.pointer(event);
            const dateAtMouse = chart.xScale.invert(mx);

            // Find closest data point
            const bisect = d3.bisector(d => new Date(d[0])).left;
            const index = bisect(data, dateAtMouse);
            const d = data[index];

            if (d) {
                // Show crosshair
                chart.crosshairGroup.style('display', null);

                chart.crosshairGroup.select('.crosshair-x')
                    .attr('x1', mx)
                    .attr('x2', mx)
                    .attr('y1', 0)
                    .attr('y2', chart.height);

                chart.crosshairGroup.select('.crosshair-y')
                    .attr('x1', 0)
                    .attr('x2', chart.width)
                    .attr('y1', my)
                    .attr('y2', my);

                // Determine sentiment
                const rate = d[1];
                let sentiment, color;
                if (rate > 0.01) {
                    sentiment = 'Bullish Premium';
                    color = '#26a69a';
                } else if (rate < -0.01) {
                    sentiment = 'Bearish Premium';
                    color = '#ef5350';
                } else {
                    sentiment = 'Neutral';
                    color = '#888';
                }

                // Show tooltip
                const tooltipHTML = `
                    <div class="tooltip-header">${new Date(d[0]).toLocaleDateString()}</div>
                    <div class="tooltip-row">
                        <span>Funding Rate:</span>
                        <span class="tooltip-value" style="color: ${color};">${rate.toFixed(4)}%</span>
                    </div>
                    <div class="tooltip-row">
                        <span>Sentiment:</span>
                        <span class="tooltip-value" style="color: ${color};">${sentiment}</span>
                    </div>
                `;

                tooltip.html(tooltipHTML)
                    .classed('show', true)
                    .style('left', (event.pageX + 15) + 'px')
                    .style('top', (event.pageY - 15) + 'px');
            }
        })
        .on('mouseleave', () => {
            chart.crosshairGroup.style('display', 'none');
            tooltip.classed('show', false);
        });
}

/**
 * Setup zoom and pan behavior for funding rate chart
 * @param {string} dataset - Dataset name
 */
function setupFundingRateZoom(dataset) {
    const chart = fundingRateChartInstances[dataset];

    // Store data for zoom updates
    const data = chart.data;

    // Create zoom behavior
    chart.zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .translateExtent([[0, 0], [chart.width, chart.height]])
        .extent([[0, 0], [chart.width, chart.height]])
        .on('zoom', (event) => {
            chart.currentTransform = event.transform;
            updateFundingRateZoom(dataset, data, event.transform);
        });

    // Attach zoom to overlay
    chart.zoomOverlay.call(chart.zoom);
}

/**
 * Update funding rate chart with zoom transform
 * @param {string} dataset - Dataset name
 * @param {Array} data - Funding rate data
 * @param {Object} transform - D3 zoom transform
 */
function updateFundingRateZoom(dataset, data, transform) {
    const chart = fundingRateChartInstances[dataset];

    // Update X scale with transform
    const newXScale = transform.rescaleX(chart.xScale);

    // Update X axis
    const xAxis = d3.axisBottom(newXScale)
        .ticks(6)
        .tickFormat(d3.timeFormat('%b %d'));

    chart.axisGroup.select('.x-axis')
        .call(xAxis)
        .selectAll('text')
        .attr('fill', '#888')
        .style('font-size', '11px');

    // Update reference lines
    chart.referenceGroup.selectAll('line')
        .attr('x1', 0)
        .attr('x2', chart.width);

    chart.referenceGroup.selectAll('text')
        .attr('x', chart.width + 5);

    // Rebuild segments with new X scale
    const positiveThreshold = 0.01;
    const negativeThreshold = -0.01;

    const getColor = (value) => {
        if (value > positiveThreshold) return '#26a69a';
        if (value < negativeThreshold) return '#ef5350';
        return '#888888';
    };

    const segments = [];
    let currentSegment = null;

    data.forEach((d, i) => {
        const color = getColor(d[1]);

        if (!currentSegment || currentSegment.color !== color) {
            if (currentSegment) {
                currentSegment.data.push(d);
                segments.push(currentSegment);
            }
            currentSegment = { color, data: [d] };
        } else {
            currentSegment.data.push(d);
        }
    });

    if (currentSegment) {
        segments.push(currentSegment);
    }

    // Area generator with new X scale
    const area = d3.area()
        .x(d => newXScale(new Date(d[0])))
        .y0(chart.yScale(0))
        .y1(d => chart.yScale(d[1]))
        .curve(d3.curveLinear);

    // Line generator with new X scale
    const line = d3.line()
        .x(d => newXScale(new Date(d[0])))
        .y(d => chart.yScale(d[1]))
        .curve(d3.curveLinear);

    // Update area segments
    chart.areaGroup.selectAll('*').remove();
    segments.forEach((segment, i) => {
        chart.areaGroup.append('path')
            .datum(segment.data)
            .attr('class', `area-segment-${i}`)
            .attr('fill', segment.color)
            .attr('fill-opacity', 0.2)
            .attr('d', area);
    });

    // Update line segments
    chart.lineGroup.selectAll('*').remove();
    segments.forEach((segment, i) => {
        chart.lineGroup.append('path')
            .datum(segment.data)
            .attr('class', `line-segment-${i}`)
            .attr('fill', 'none')
            .attr('stroke', segment.color)
            .attr('stroke-width', 2)
            .attr('d', line);
    });
}

