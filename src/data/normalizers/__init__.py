# data/normalizers/__init__.py
"""
Normalization function for oscillator datasets.
Uses regression divergence (zscore) - mathematically rigorous approach.
"""

from . import zscore

__all__ = [
    'zscore'
]
