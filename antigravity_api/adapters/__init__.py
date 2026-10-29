"""API Adapters for OpenAI and Anthropic compatibility."""
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

__all__ = ["OpenAIAdapter", "AnthropicAdapter"]
