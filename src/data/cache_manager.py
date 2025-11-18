# filename: data/cache_manager.py
import json
import os

# Create a directory for cache files if it doesn't exist
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'storage', 'cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def load_from_cache(dataset_name):
    """Loads a dataset from its JSON cache file, if it exists."""
    cache_file = os.path.join(CACHE_DIR, f"{dataset_name}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return [] # Return empty list if cache is corrupt
    return []

def save_to_cache(dataset_name, data):
    """Saves a dataset to its JSON cache file."""
    cache_file = os.path.join(CACHE_DIR, f"{dataset_name}.json")
    with open(cache_file, 'w') as f:
        json.dump(data, f)