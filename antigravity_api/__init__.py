"""Antigravity Direct API & Chatbot package.
Enables direct communication with Google Antigravity cloud inference without CLI dependencies.
"""

from .auth import TokenManager
from .client import AntigravityClient
from .models import AVAILABLE_MODELS, ModelInfo

__version__ = "1.0.0"
__all__ = ["TokenManager", "AntigravityClient", "AVAILABLE_MODELS", "ModelInfo"]
