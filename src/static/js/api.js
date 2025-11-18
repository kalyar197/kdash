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
