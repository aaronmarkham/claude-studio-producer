"""Image provider implementations"""

from .dalle import DalleProvider
from .wikimedia import WikimediaProvider

__all__ = [
    "DalleProvider",
    "WikimediaProvider",
]
