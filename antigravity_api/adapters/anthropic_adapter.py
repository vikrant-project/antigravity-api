"""Anthropic Messages API Adapter for Antigravity backend.
Translates Anthropic /v1/messages requests <-> Antigravity internal protocol.
"""

import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..client import AntigravityClient
from ..models import resolve_model_id


class AnthropicAdapter:
    """Translates Anthropic Messages requests to Antigravity and back."""

    def __init__(self, client: AntigravityClient):
        self.client = client

    @staticmethod
    def parse_anthropic_payload(payload: Dict[str, Any]):
        """Parses Anthropic messages payload into Antigravity internal structure."""
        system_content = payload.get("system", "")
        if isinstance(system_content, list):
            system_str = " ".join(b.get("text", "") for b in system_content if isinstance(b, dict))
        else:
            system_str = str(system_content) if system_content else None

        contents = []
        for msg in payload.get("messages", []):
            role = "user" if msg.get("role") == "user" else "model"
            content = msg.get("content", "")
            parts = []

            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        btype = b.get("type")
                        if btype == "text":
                            parts.append({"text": b.get("text", "")})
                        elif btype == "tool_use":
                            parts.append({
                                "functionCall": {
                                    "name": b.get("name"),
                                    "args": b.get("input", {}),
                                    "id": b.get("id")
                                }
                            })
                        elif btype == "tool_result":
                            parts.append({
                                "functionResponse": {
                                    "name": b.get("tool_use_id", "tool"),
                                    "response": {"content": b.get("content", "")}
                                }
                            })
            contents.append({"role": role, "parts": parts})

        # Parse tools
        tools = None
        raw_tools = payload.get("tools")
        if raw_tools and isinstance(raw_tools, list):
            func_decls = []
            for t in raw_tools:
                func_decls.append({
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "OBJECT", "properties": {}})
                })
            tools = [{"functionDeclarations": func_decls}]

        return system_str, contents, tools

    async def messages_stream(self, request: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Streams Anthropic SSE events."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        model_req = request.get("model", "claude-sonnet-4-6")
        resolved_model = resolve_model_id(model_req)

        system_str, contents, tools = self.parse_anthropic_payload(request)
        gen_config = {
            "temperature": request.get("temperature", 0.7),
            "maxOutputTokens": request.get("max_tokens", 4096)
        }

        # message_start
        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': resolved_model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"

        # content_block_start
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

        stop_reason = "end_turn"
        output_tokens = 0

        async for chunk in self.client.astream_generate_content(
            model=resolved_model,
            contents=contents,
            system_instruction=system_str,
            generation_config=gen_config,
            tools=tools
        ):
            resp = chunk.get("response", {})
            for cand in resp.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "text" in part and not part.get("thought", False):
                        text = part["text"]
                        if text:
                            output_tokens += 1
                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}})}\n\n"
                    if "functionCall" in part:
                        stop_reason = "tool_use"
                if cand.get("finishReason") == "STOP":
                    stop_reason = "end_turn"

        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
