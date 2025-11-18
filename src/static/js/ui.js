/**
 * UI Module - Handles all user interface interactions and event listeners
 */

// State for active plugins (will be managed by main.js)
let activePlugins = [];

// Callback functions provided by main.js
let callbacks = {
    onPluginChange: null,
    onDaysChange: null,
    zoomControls: null
};

/**
 * Initializes all UI controls and event listeners
 * This function should be called once when the application starts
 * @param {Object} config - Configuration object with callbacks
 * @param {Function} config.onPluginChange - Called when plugin selection changes
 * @param {Function} config.onDaysChange - Called when time range changes
 * @param {Object} config.zoomControls - Zoom control functions {resetZoom, zoomIn, zoomOut}
 * @param {Function} config.getDatasets - Function to fetch datasets from API
 */
export async function initializeControls(config) {
    // Store callbacks for use in event handlers
    callbacks = config;

    try {
        // Fetch available datasets from the API using provided function
        const datasets = await config.getDatasets();

        if (Object.keys(datasets).length === 0) {
            showError('No datasets configured on server. Please add data plugins to the data/ folder.');
            return;
        }

        // Build plugin controls dynamically
        buildPluginControls(datasets);

        // Setup event listeners for time range buttons
        setupTimeRangeButtons();

        // Setup event listeners for zoom control buttons
        setupZoomButtons();

        // Initial chart update with default selection
        if (activePlugins.length > 0 && callbacks.onPluginChange) {
            // Trigger initial chart update
            callbacks.onPluginChange(activePlugins);
        }

    } catch (error) {
        console.error('Failed to load datasets:', error);
        showError('Cannot connect to server. Please ensure Flask server is running on port 5000.');

        // Show connection instructions
        const container = document.getElementById('plugin-controls');
        container.innerHTML = '<span style="color: #ff4444; font-size: 12px;">No connection to backend</span>';
    }
}

/**
 * Builds plugin control checkboxes dynamically from datasets
 * @param {Object} datasets - Object containing dataset metadata
 */
function buildPluginControls(datasets) {
    const container = document.getElementById('plugin-controls');
    container.innerHTML = '';

    // Default plugins to select on initialization
    const defaultPlugins = ['eth', 'btc'];

    Object.entries(datasets).forEach(([key, metadata]) => {
        const wrapper = document.createElement('span');
        wrapper.className = `${key}-label`;

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = key;
        input.dataset.plugin = key;

        // Check default plugins
        if (defaultPlugins.includes(key)) {
            input.checked = true;
            activePlugins.push(key);
        }

        const label = document.createElement('label');
        label.htmlFor = key;
        label.textContent = metadata.label;
        label.style.setProperty('--plugin-color', metadata.color);

        // Calculate a dark version of the color for background
        const colorDark = metadata.color ?
            `${metadata.color}33` : 'rgba(255, 255, 255, 0.1)';
        label.style.setProperty('--plugin-color-dark', colorDark);

        wrapper.appendChild(input);
        wrapper.appendChild(label);
        container.appendChild(wrapper);

        // Attach event listener for this checkbox
        input.addEventListener('change', handlePluginChange);
    });
}

/**
 * Handles plugin checkbox change events
 */
function handlePluginChange(event) {
    activePlugins = Array.from(
        document.querySelectorAll('.plugins-container input:checked')
    ).map(el => el.dataset.plugin);

    // Call the plugin change callback
    if (callbacks.onPluginChange) {
        callbacks.onPluginChange(activePlugins);
    }
}

/**
 * Sets up event listeners for time range buttons (1M, 3M, 1Y, ALL)
 */
function setupTimeRangeButtons() {
    const buttons = document.querySelectorAll('.button-container button');

    buttons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            buttons.forEach(btn => btn.classList.remove('active'));

            // Add active class to clicked button
            this.classList.add('active');

            // Get the days value from data attribute
            const days = this.dataset.days;

            // Call the days change callback
            if (callbacks.onDaysChange) {
                callbacks.onDaysChange(days);
            }
        });
    });
}

/**
 * Sets up event listeners for zoom control buttons
 */
function setupZoomButtons() {
    const resetZoomBtn = document.getElementById('reset-zoom');
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');

    if (resetZoomBtn && callbacks.zoomControls) {
        resetZoomBtn.addEventListener('click', () => {
            if (callbacks.zoomControls.resetZoom) {
                callbacks.zoomControls.resetZoom();
            }
        });
    }

    if (zoomInBtn && callbacks.zoomControls) {
        zoomInBtn.addEventListener('click', () => {
            if (callbacks.zoomControls.zoomIn) {
                callbacks.zoomControls.zoomIn();
            }
        });
    }

    if (zoomOutBtn && callbacks.zoomControls) {
        zoomOutBtn.addEventListener('click', () => {
            if (callbacks.zoomControls.zoomOut) {
                callbacks.zoomControls.zoomOut();
            }
        });
    }
}

/**
 * Shows an error message in the chart container
 * @param {string} message - Error message to display
 */
function showError(message) {
    // TODO: This will need to be coordinated with chart.js or handled differently
    const container = document.getElementById('chart-container');

    // Remove any existing error/loading messages
    const existingMessages = container.querySelectorAll('.loading, .error');
    existingMessages.forEach(el => el.remove());

    // Create and show error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.innerHTML = `
        <div style="text-align: center;">
            <div style="font-size: 24px; margin-bottom: 10px;">�</div>
            <div>${message}</div>
        </div>
    `;
    container.appendChild(errorDiv);
}

/**
 * Gets the currently active plugins
 * @returns {Array<string>} Array of active plugin names
 */
export function getActivePlugins() {
    return activePlugins;
}

/**
 * Sets the active plugins (useful for external updates)
 * @param {Array<string>} plugins - Array of plugin names to set as active
 */
export function setActivePlugins(plugins) {
    activePlugins = plugins;

    // Update checkbox states
    document.querySelectorAll('.plugins-container input').forEach(input => {
        input.checked = activePlugins.includes(input.dataset.plugin);
    });
}
