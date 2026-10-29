"""Model definitions, aliases, and upstream mapping for Antigravity backend."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelInfo:
    id: str                         # Client-facing ID (e.g. gemini-3.8-flash-high)
    upstream_id: str                # Upstream Google backend ID (e.g. gemini-3.8-flash-tiered)
    display_name: str
    provider: str
    default_thinking_budget: Optional[int] = None
    max_tokens: int = 1048576
    max_output_tokens: int = 65536
    supports_thinking: bool = False
    supports_tools: bool = True
    supports_vision: bool = True
    aliases: List[str] = field(default_factory=list)


AVAILABLE_MODELS: Dict[str, ModelInfo] = {
    "gemini-3.8-flash-high": ModelInfo(
        id="gemini-3.8-flash-high",
        upstream_id="gemini-3.8-flash-tiered",
        display_name="Gemini 3.8 Flash (High)",
        provider="Google",
        default_thinking_budget=8192,
        max_tokens=1048576,
        max_output_tokens=65536,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-3.8-flash", "gemini-3.8", "gemini-3.8-high", "gemini-flash-high", "3.8-flash"]
    ),
    "gemini-3.8-flash-medium": ModelInfo(
        id="gemini-3.8-flash-medium",
        upstream_id="gemini-3.8-flash-tiered",
        display_name="Gemini 3.8 Flash (Medium)",
        provider="Google",
        default_thinking_budget=2048,
        max_tokens=1048576,
        max_output_tokens=65536,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-3.8-medium", "gemini-flash-medium"]
    ),
    "gemini-3.8-flash-low": ModelInfo(
        id="gemini-3.8-flash-low",
        upstream_id="gemini-3.8-flash-tiered",
        display_name="Gemini 3.8 Flash (Low)",
        provider="Google",
        default_thinking_budget=512,
        max_tokens=1048576,
        max_output_tokens=65536,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-3.8-low", "gemini-flash-low"]
    ),
    "claude-sonnet-4-6": ModelInfo(
        id="claude-sonnet-4-6",
        upstream_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6 (Thinking)",
        provider="Anthropic",
        default_thinking_budget=4096,
        max_tokens=200000,
        max_output_tokens=8192,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["claude-sonnet", "claude-3-5-sonnet", "claude-3.5-sonnet", "sonnet"]
    ),
    "claude-opus-4-6-thinking": ModelInfo(
        id="claude-opus-4-6-thinking",
        upstream_id="claude-opus-4-6-thinking",
        display_name="Claude Opus 4.6 (Thinking)",
        provider="Anthropic",
        default_thinking_budget=4096,
        max_tokens=200000,
        max_output_tokens=8192,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["claude-opus", "claude-3-opus", "opus"]
    ),
    "gemini-2.5-flash": ModelInfo(
        id="gemini-2.5-flash",
        upstream_id="gemini-2.5-flash",
        display_name="Gemini 3.5 Flash Lite",
        provider="Google",
        default_thinking_budget=1024,
        max_tokens=1048576,
        max_output_tokens=65536,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite"]
    ),
    "gemini-3-flash": ModelInfo(
        id="gemini-3-flash",
        upstream_id="gemini-3-flash",
        display_name="Gemini 3 Flash",
        provider="Google",
        default_thinking_budget=2048,
        max_tokens=1048576,
        max_output_tokens=32768,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-3", "gemini-v3"]
    ),
    "gemini-2.5-pro": ModelInfo(
        id="gemini-2.5-pro",
        upstream_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider="Google",
        default_thinking_budget=4096,
        max_tokens=2097152,
        max_output_tokens=65536,
        supports_thinking=True,
        supports_tools=True,
        supports_vision=True,
        aliases=["gemini-pro", "gemini-1.5-pro", "gemini-2-pro"]
    ),
    "gpt-oss-120b-medium": ModelInfo(
        id="gpt-oss-120b-medium",
        upstream_id="gpt-oss-120b-medium",
        display_name="GPT-OSS 120B (Medium)",
        provider="OpenAI",
        default_thinking_budget=None,
        max_tokens=128000,
        max_output_tokens=4096,
        supports_thinking=False,
        supports_tools=True,
        supports_vision=False,
        aliases=["gpt-oss", "gpt-120b", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]
    ),
}

DEFAULT_MODEL_ID = "gemini-3.8-flash-high"


def resolve_model(input_name: Optional[str]) -> ModelInfo:
    """Resolves an input model name or alias to its ModelInfo dataclass."""
    if not input_name:
        return AVAILABLE_MODELS[DEFAULT_MODEL_ID]

    low = input_name.strip().lower()

    # Exact match on ID
    if low in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[low]

    # Check aliases and display names
    for model_id, info in AVAILABLE_MODELS.items():
        if low in info.aliases or low == model_id.lower() or low == info.display_name.lower():
            return info

    # Specific checks for 3.8
    if "3.8" in low:
        if "low" in low:
            return AVAILABLE_MODELS["gemini-3.8-flash-low"]
        if "med" in low:
            return AVAILABLE_MODELS["gemini-3.8-flash-medium"]
        return AVAILABLE_MODELS["gemini-3.8-flash-high"]

    # Claude checks
    if "claude" in low:
        if "opus" in low:
            return AVAILABLE_MODELS["claude-opus-4-6-thinking"]
        return AVAILABLE_MODELS["claude-sonnet-4-6"]

    # Gemini checks
    if "pro" in low:
        return AVAILABLE_MODELS["gemini-2.5-pro"]
    if "3-flash" in low:
        return AVAILABLE_MODELS["gemini-3-flash"]
    if "gpt" in low or "oss" in low:
        return AVAILABLE_MODELS["gpt-oss-120b-medium"]

    return AVAILABLE_MODELS[DEFAULT_MODEL_ID]


def resolve_model_id(input_name: Optional[str]) -> str:
    """Returns the client-facing model ID."""
    return resolve_model(input_name).id


def resolve_upstream_id(input_name: Optional[str]) -> str:
    """Returns the upstream Google backend model ID (e.g. gemini-3.8-flash-tiered)."""
    return resolve_model(input_name).upstream_id
