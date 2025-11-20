// API Configuration
const API_BASE_URL = 'http://127.0.0.1:5000';

/**
 * Fetches the list of available datasets from the backend
 * @returns {Promise<Object>} Object containing metadata for all available datasets
 * @throws {Error} If the fetch request fails
 */
export async function getDatasets() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/datasets`);

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching datasets:', error);
        throw error;
    }
}

/**
 * Fetches data for a specific dataset with the given time range
 * @param {string} dataset - The name of the dataset/plugin (e.g., 'eth', 'gold_price', 'rsi')
 * @param {string|number} days - The number of days to fetch ('30', '90', '365', 'max')
 * @param {Object} options - Optional parameters (sensitivity, expiry_days for S/R)
 * @returns {Promise<Object>} Object containing data and metadata for the requested dataset
 * @throws {Error} If the fetch request fails
 */
export async function getDatasetData(dataset, days = '365', options = {}) {
    try {
        // Build query parameters
        let url = `${API_BASE_URL}/api/data?dataset=${dataset}&days=${days}`;

        // Add optional parameters if provided
        if (options.sensitivity) {
            url += `&sensitivity=${options.sensitivity}`;
        }
        if (options.expiry_days) {
            url += `&expiry_days=${options.expiry_days}`;
        }

        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`Error fetching data for ${dataset}:`, error);
        throw error;
    }
}

/**
 * Fetches System 2 velocity-anchored oscillator data
 * @param {string} asset - The asset symbol (currently only 'btc' supported)
 * @param {string|number} days - The number of days to fetch (default: 365)
 * @param {number} noiseLevel - Rolling window size for regression (default: 30)
 * @returns {Promise<Object>} Object containing breakdown oscillators and regime data
 * @throws {Error} If the fetch request fails
 */
export async function getSystem2Data(asset = 'btc', days = 365, noiseLevel = 30) {
    try {
        const url = `${API_BASE_URL}/api/system2-data?asset=${asset}&days=${days}&noise_level=${noiseLevel}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.breakdown) {
            console.warn('[System 2] Response missing breakdown data');
        }

        return data;
    } catch (error) {
        console.error(`Error fetching System 2 data for ${asset}:`, error);
        throw error;
    }
}

/**
 * Fetch System 3 (Tension² Pairs) data for a specific category
 * @param {string} category - Category A-F
 * @param {string} asset - Asset symbol (e.g., 'btc')
 * @param {number} days - Number of days to fetch
 * @param {number} window - Rolling window size for z-score calculations
 * @returns {Promise<Object>} System 3 data with pairs array
 */
export async function getSystem3Data(category, asset, days, window) {
    try {
        console.log(`[System 3] Fetching data: category=${category}, asset=${asset}, days=${days}, window=${window}`);
        const url = `${API_BASE_URL}/api/system3-data?category=${category}&asset=${asset}&days=${days}&window=${window}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.pairs) {
            console.warn('[System 3] Response missing pairs data');
        }

        console.log(`[System 3] Received ${data.pairs?.length || 0} pairs for category ${category}`);

        return data;
    } catch (error) {
        console.error(`Error fetching System 3 data for category ${category}:`, error);
        throw error;
    }
}
