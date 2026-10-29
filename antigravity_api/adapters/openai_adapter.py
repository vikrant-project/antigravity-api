"""OpenAI API Adapter for Antigravity backend.
Translates OpenAI chat completion format <-> Antigravity internal protocol.
"""

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from ..client import AntigravityClient
from ..models import resolve_model_id


class OpenAIAdapter:
    """Translates OpenAI Chat Completion requests to Antigravity and back."""

    def __init__(self, client: AntigravityClient):
        self.client = client

    @staticmethod
    def parse_openai_messages(
        messages: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Splits OpenAI messages into system_instruction and Antigravity contents."""
        system_instructions: List[str] = []
        contents: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # If content is a list of parts (e.g., text + image)
            parts: List[Dict[str, Any]] = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append({"text": item.get("text", "")})
                        elif item.get("type") == "image_url":
                            # Vision support
                            img_url = item.get("image_url", {}).get("url", "")
                            if img_url.startswith("data:"):
                                header, b64 = img_url.split(",", 1)
                                mime = header.split(";")[0].split(":")[1]
                                parts.append({
                                    "inlineData": {
                                        "mimeType": mime,
                                        "data": b64
                                    }
                                })
            else:
                parts.append({"text": str(content)})

            if role in ("system", "developer"):
                text_content = " ".join(p["text"] for p in parts if "text" in p)
                if text_content:
                    system_instructions.append(text_content)
            elif role == "assistant":
                # Check for tool_calls in assistant message
                if "tool_calls" in msg and msg["tool_calls"]:
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        try:
                            args_dict = json.loads(args) if isinstance(args, str) else args
                        except Exception:
                            args_dict = {}
                        parts.append({
                            "functionCall": {
                                "name": fn.get("name"),
                                "args": args_dict
                            }
                        })
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                # Tool result
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.get("name", "tool_result"),
                            "response": {"content": content}
                        }
                    }]
                })
            else:  # user
                contents.append({"role": "user", "parts": parts})

        system_instruction = "\n\n".join(system_instructions) if system_instructions else None
        return system_instruction, contents

    @staticmethod
    def parse_openai_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Converts OpenAI tools schema into Antigravity functionDeclarations."""
        if not tools:
            return None

        func_decls = []
        for t in tools:
            if t.get("type") == "function":
                fn = t.get("function", {})
                func_decls.append({
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "OBJECT", "properties": {}})
                })

        return [{"functionDeclarations": func_decls}] if func_decls else None

    async def chat_completion_stream(
        self,
        request: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Streams OpenAI-compatible chunk events."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        model_req = request.get("model", "gemini-2.5-flash")
        resolved_model = resolve_model_id(model_req)

        system_inst, contents = self.parse_openai_messages(request.get("messages", []))
        tools = self.parse_openai_tools(request.get("tools"))

        gen_config = {
            "temperature": request.get("temperature", 0.7),
            "maxOutputTokens": request.get("max_tokens", 4096),
        }
        if "top_p" in request:
            gen_config["topP"] = request["top_p"]

        # Initial role chunk
        initial_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": resolved_model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(initial_chunk)}\n\n"

        async for chunk in self.client.astream_generate_content(
            model=resolved_model,
            contents=contents,
            system_instruction=system_inst,
            generation_config=gen_config,
            tools=tools
        ):
            resp = chunk.get("response", {})
            for cand in resp.get("candidates", []):
                finish_reason = cand.get("finishReason")
                for part in cand.get("content", {}).get("parts", []):
                    # Text delta
                    if "text" in part and not part.get("thought", False):
                        text = part["text"]
                        if text:
                            delta_chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": resolved_model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(delta_chunk)}\n\n"

                    # Tool Call delta
                    if "functionCall" in part:
                        fc = part["functionCall"]
                        tool_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": resolved_model,
                            "choices": [{
                                "index": 0,
                                "delta": {
                                    "tool_calls": [{
                                        "index": 0,
                                        "id": fc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                        "type": "function",
                                        "function": {
                                            "name": fc.get("name"),
                                            "arguments": json.dumps(fc.get("args", {}))
                                        }
                                    }]
                                },
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(tool_chunk)}\n\n"

                if finish_reason:
                    stop_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": resolved_model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop" if finish_reason == "STOP" else finish_reason.lower()
                        }]
                    }
                    yield f"data: {json.dumps(stop_chunk)}\n\n"

        yield "data: [DONE]\n\n"

    def chat_completion_sync(
        self,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handles non-streaming OpenAI chat completion."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        model_req = request.get("model", "gemini-2.5-flash")
        resolved_model = resolve_model_id(model_req)

        system_inst, contents = self.parse_openai_messages(request.get("messages", []))
        tools = self.parse_openai_tools(request.get("tools"))

        gen_config = {
            "temperature": request.get("temperature", 0.7),
            "maxOutputTokens": request.get("max_tokens", 4096),
        }

        result = self.client.generate_content(
            model=resolved_model,
            contents=contents,
            system_instruction=system_inst,
            generation_config=gen_config,
            tools=tools
        )

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": result.get("text", "")
        }

        if result.get("function_calls"):
            tool_calls = []
            for i, fc in enumerate(result["function_calls"]):
                tool_calls.append({
                    "id": fc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                    "type": "function",
                    "function": {
                        "name": fc.get("name"),
                        "arguments": json.dumps(fc.get("args", {}))
                    }
                })
            message["tool_calls"] = tool_calls

        usage = result.get("usage", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": resolved_model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "stop" if result.get("finish_reason") == "STOP" else "tool_calls" if result.get("function_calls") else "stop"
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }
