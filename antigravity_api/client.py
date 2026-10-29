"""Core HTTP and SSE Client for Antigravity Cloud API.
Communicates directly with Google Cloud Code backend with zero CLI overhead.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Union
import httpx

from .auth import TokenManager
from .models import DEFAULT_MODEL_ID, resolve_model, resolve_model_id, resolve_upstream_id

logger = logging.getLogger("antigravity.client")

BASE_API_URL = "https://daily-cloudcode-pa.googleapis.com/v1internal"


class AntigravityClient:
    """Direct API client for Antigravity models (Gemini 3.8 Flash, Claude, GPT-OSS)."""

    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
        base_url: str = BASE_API_URL,
        timeout: float = 60.0
    ):
        self.token_manager = token_manager or TokenManager()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        token = self.token_manager.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity-cli"
        }

    def _prepare_generation_config(
        self,
        model_info,
        generation_config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepares generation config ensuring maxOutputTokens > thinkingBudget."""
        cfg = dict(generation_config or {"temperature": 0.7, "maxOutputTokens": 8192})
        max_tokens = cfg.get("maxOutputTokens", 8192)

        if model_info.supports_thinking and model_info.default_thinking_budget:
            budget = model_info.default_thinking_budget
            if "thinkingConfig" not in cfg:
                if max_tokens <= budget:
                    cfg["maxOutputTokens"] = budget + 2048
                cfg["thinkingConfig"] = {"thinkingBudget": budget}
            else:
                user_budget = cfg["thinkingConfig"].get("thinkingBudget", budget)
                if max_tokens <= user_budget:
                    cfg["maxOutputTokens"] = user_budget + 2048

        return cfg

    # ---------------- Sync Methods ---------------- #

    def fetch_models(self) -> Dict[str, Any]:
        """Queries upstream for all available models, quotas, and capabilities."""
        url = f"{self.base_url}:fetchAvailableModels"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._get_headers(), json={})
            resp.raise_for_status()
            return resp.json()

    def load_code_assist(self) -> Dict[str, Any]:
        """Queries user entitlement and account status."""
        url = f"{self.base_url}:loadCodeAssist"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._get_headers(), json={})
            resp.raise_for_status()
            return resp.json()

    def stream_generate_content(
        self,
        model: Optional[str] = None,
        contents: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Streams content generation tokens and function calls from Antigravity backend."""
        model_info = resolve_model(model)
        upstream_model = model_info.upstream_id
        gen_cfg = self._prepare_generation_config(model_info, generation_config)

        url = f"{self.base_url}:streamGenerateContent?alt=sse"

        request_payload: Dict[str, Any] = {
            "contents": contents or [],
            "generationConfig": gen_cfg
        }

        if system_instruction:
            request_payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        if tools:
            request_payload["tools"] = tools

        body = {
            "model": upstream_model,
            "request": request_payload
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=self._get_headers(), json=body)
            # Upstream temporary fallback (e.g. 503)
            if response.status_code == 503 and upstream_model != "gemini-3.8-flash-tiered":
                logger.warning(f"Upstream model {upstream_model} returned 503, falling back to gemini-3.8-flash-tiered")
                body["model"] = "gemini-3.8-flash-tiered"
                response = client.post(url, headers=self._get_headers(), json=body)

            if response.status_code != 200:
                err_text = response.text
                raise RuntimeError(f"Antigravity API Error ({response.status_code}): {err_text}")

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.strip()
                if line_str.startswith("data: "):
                    data_content = line_str[6:].strip()
                    if not data_content:
                        continue
                    try:
                        parsed = json.loads(data_content)
                        yield parsed
                    except json.JSONDecodeError:
                        continue

    def generate_content(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        contents: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Non-streaming generation returning full aggregated response."""
        if prompt and not contents:
            contents = [{"role": "user", "parts": [{"text": prompt}]}]

        model_info = resolve_model(model)
        full_text = ""
        thought_text = ""
        function_calls = []
        finish_reason = "STOP"
        usage_metadata = {}

        for chunk in self.stream_generate_content(
            model=model_info.id,
            contents=contents,
            system_instruction=system_instruction,
            generation_config=generation_config,
            tools=tools
        ):
            resp = chunk.get("response", {})
            if "usageMetadata" in resp:
                usage_metadata = resp["usageMetadata"]

            for cand in resp.get("candidates", []):
                if "finishReason" in cand:
                    finish_reason = cand["finishReason"]
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("thought", False):
                        thought_text += part.get("text", "")
                    elif "text" in part:
                        full_text += part["text"]
                    if "functionCall" in part:
                        function_calls.append(part["functionCall"])

        return {
            "text": full_text,
            "thought": thought_text,
            "function_calls": function_calls,
            "finish_reason": finish_reason,
            "usage": usage_metadata,
            "model": model_info.id
        }

    # ---------------- Async Methods ---------------- #

    async def astream_generate_content(
        self,
        model: Optional[str] = None,
        contents: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Asynchronous streaming generator for SSE events."""
        model_info = resolve_model(model)
        upstream_model = model_info.upstream_id
        gen_cfg = self._prepare_generation_config(model_info, generation_config)

        url = f"{self.base_url}:streamGenerateContent?alt=sse"

        request_payload: Dict[str, Any] = {
            "contents": contents or [],
            "generationConfig": gen_cfg
        }

        if system_instruction:
            request_payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        if tools:
            request_payload["tools"] = tools

        body = {
            "model": upstream_model,
            "request": request_payload
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=self._get_headers(), json=body) as response:
                if response.status_code == 503 and upstream_model != "gemini-3.8-flash-tiered":
                    logger.warning(f"Upstream model {upstream_model} is 503, falling back to gemini-3.8-flash-tiered")
                    body["model"] = "gemini-3.8-flash-tiered"
                    async with client.stream("POST", url, headers=self._get_headers(), json=body) as fallback_resp:
                        async for line in fallback_resp.aiter_lines():
                            if not line:
                                continue
                            line_str = line.strip()
                            if line_str.startswith("data: "):
                                data_content = line_str[6:].strip()
                                if not data_content:
                                    continue
                                try:
                                    parsed = json.loads(data_content)
                                    yield parsed
                                except json.JSONDecodeError:
                                    continue
                    return

                if response.status_code != 200:
                    err_text = (await response.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(f"Antigravity API Error ({response.status_code}): {err_text}")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    line_str = line.strip()
                    if line_str.startswith("data: "):
                        data_content = line_str[6:].strip()
                        if not data_content:
                            continue
                        try:
                            parsed = json.loads(data_content)
                            yield parsed
                        except json.JSONDecodeError:
                            continue
