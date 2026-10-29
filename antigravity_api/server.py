"""FastAPI Server exposing Antigravity direct API and Web Chatbot UI.
Zero CLI binary dependency - purely native HTTP & SSE.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.openai_adapter import OpenAIAdapter
from .auth import TokenManager
from .client import AntigravityClient
from .models import AVAILABLE_MODELS, resolve_model_id

logger = logging.getLogger("antigravity.server")

app = FastAPI(
    title="Antigravity Direct API & Chatbot",
    description="Native Python API and Web Chatbot for Google Antigravity cloud inference without CLI dependencies",
    version="1.0.0"
)

# Enable CORS for all frontends (OpenWebUI, LibreChat, Chatbox, Cursor, browser)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core services
token_mgr = TokenManager()
client = AntigravityClient(token_manager=token_mgr)
openai_adapter = OpenAIAdapter(client)
anthropic_adapter = AnthropicAdapter(client)

WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ---------------- Health & Meta ---------------- #

@app.get("/health")
async def health_check():
    """Health check endpoint showing account status and token validity."""
    has_token = bool(token_mgr.access_token)
    time_left = max(0, int(token_mgr.expiry_epoch - time.time()))
    return {
        "status": "online" if has_token else "needs_token",
        "authenticated_user": token_mgr.user_email or "Unknown",
        "user_name": token_mgr.user_name or "User",
        "token_expires_in_seconds": time_left,
        "token_source": token_mgr.token_path or "environment",
        "available_models_count": len(AVAILABLE_MODELS),
        "version": "1.0.0"
    }


@app.get("/api/quota")
async def get_quota():
    """Fetches real-time quota data directly from upstream."""
    try:
        data = client.fetch_models()
        quotas = {}
        for m_id, info in data.get("models", {}).items():
            quotas[m_id] = {
                "displayName": info.get("displayName", m_id),
                "remainingFraction": info.get("quotaInfo", {}).get("remainingFraction", 1.0),
                "resetTime": info.get("quotaInfo", {}).get("resetTime")
            }
        return {"status": "ok", "quotas": quotas}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/token/refresh")
async def force_refresh():
    """Forces an immediate OAuth token refresh."""
    ok = token_mgr.refresh()
    return {
        "success": ok,
        "user_email": token_mgr.user_email,
        "expires_in_seconds": max(0, int(token_mgr.expiry_epoch - time.time()))
    }


# ---------------- OpenAI Compatible Endpoints ---------------- #

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models listing."""
    data = []
    for model_id, info in AVAILABLE_MODELS.items():
        data.append({
            "id": model_id,
            "object": "model",
            "created": 1729000000,
            "owned_by": info.provider.lower(),
            "display_name": info.display_name,
            "permission": [],
            "root": model_id,
            "parent": None
        })
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint (supports streaming SSE)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    stream = body.get("stream", False)

    if stream:
        return StreamingResponse(
            openai_adapter.chat_completion_stream(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Non-streaming
        return JSONResponse(content=openai_adapter.chat_completion_sync(body))


# ---------------- Anthropic Compatible Endpoints ---------------- #

@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """Anthropic-compatible messages endpoint."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    stream = body.get("stream", True)
    if stream:
        return StreamingResponse(
            anthropic_adapter.messages_stream(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Simple fallback
        system_str, contents, tools = anthropic_adapter.parse_anthropic_payload(body)
        model = body.get("model", "claude-sonnet-4-6")
        res = client.generate_content(
            model=model,
            contents=contents,
            system_instruction=system_str,
            tools=tools
        )
        return {
            "id": f"msg_{time.time()}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": res.get("text", "")}],
            "model": resolve_model_id(model),
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 50}
        }


# ---------------- Simplified Direct Chat for Web UI ---------------- #

class DirectChatRequest(BaseModel):
    message: str
    model: Optional[str] = "gemini-2.5-flash"
    history: Optional[List[Dict[str, str]]] = []
    system_prompt: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096


@app.post("/api/chat")
async def direct_chat(req: DirectChatRequest):
    """Direct streaming chat endpoint for Web UI."""
    messages = []
    if req.history:
        for h in req.history:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    payload = {
        "model": req.model,
        "messages": messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": True
    }
    if req.system_prompt:
        payload["messages"].insert(0, {"role": "system", "content": req.system_prompt})

    return StreamingResponse(
        openai_adapter.chat_completion_stream(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ---------------- Web Interface ---------------- #

@app.get("/")
async def serve_index():
    """Serves the Chatbot Web Interface."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>Antigravity API is running! Web UI loading...</h1>")


# ---------------- OAuth Login Flow for Cloud ---------------- #

@app.get("/oauth/login")
async def oauth_login(request: Request):
    """Initiates Google OAuth login flow for new users/cloud deployment."""
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/oauth/callback"
    auth_url = TokenManager.get_authorization_url(redirect_uri)
    return RedirectResponse(auth_url)


@app.get("/oauth/callback")
async def oauth_callback(code: str, request: Request):
    """Handles OAuth callback and stores token."""
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/oauth/callback"
    import urllib.parse
    import urllib.request

    payload = urllib.parse.urlencode({
        "client_id": token_mgr.client_id,
        "client_secret": token_mgr.client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token_mgr.access_token = data.get("access_token")
            token_mgr.refresh_token = data.get("refresh_token", token_mgr.refresh_token)
            token_mgr.expiry_epoch = time.time() + data.get("expires_in", 3600)
            if "id_token" in data:
                token_mgr._extract_jwt_user_info(data["id_token"])
            return RedirectResponse("/?login_success=1")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {e}")
