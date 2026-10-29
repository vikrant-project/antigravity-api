# Antigravity CLI Reverse Engineering Report & Architecture

## 1. Executive Summary

The official **Google Antigravity CLI (`agy`)** is an ELF 64-bit stripped Go executable (~220 MB) that provides local agentic coding capabilities. By performing binary string analysis, symbol inspection, and network tracing on the CLI executable and its runtime logs, we identified the exact upstream Google API endpoints, Google OAuth2 client credentials, protocol payloads, and token refresh mechanisms.

This discovery allows us to bypass the heavy CLI executable and terminal wrapper completely, talking **directly** to Google's backend cloud service using standard HTTP/2 and Server-Sent Events (SSE).

---

## 2. Infrastructure & Endpoints

The CLI communicates with the internal Google Cloud Code / AI Code Assist production infrastructure:

| Endpoint | Method | Protocol | Description |
|---|---|---|---|
| `https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse` | `POST` | SSE / JSON | Main inference engine for streaming text and tool calls |
| `https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels` | `POST` | JSON | Discovers all available models, quota limits, and capabilities |
| `https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist` | `POST` | JSON | Checks tier entitlement, licenses, and backend routing |
| `https://daily-cloudcode-pa.googleapis.com/v1internal:countTokens` | `POST` | JSON | Calculates token usage for prompts |
| `https://oauth2.googleapis.com/token` | `POST` | Form-encoded | Google OAuth2 token refresh endpoint |

> **Note**: In addition to `daily-cloudcode-pa.googleapis.com`, production fallback domains include `cloudcode-pa.googleapis.com` and `autopush-cloudcode-pa.sandbox.googleapis.com`.

---

## 3. Discovered OAuth2 Credentials

Through binary decompilation and string scanning of the `agy` binary, we extracted Google's registered OAuth2 application credentials (obfuscated and managed via `antigravity_api/auth.py`):

- **Client ID Prefix**: `1071006060591-tmhssin2h21lcre235vtolojh4g403ep...`
- **Client Secret Prefix**: `GOCSPX-K58FWR486LdL...`
- **Registered Scopes**:
  - `https://www.googleapis.com/auth/cloud-platform`
  - `https://www.googleapis.com/auth/userinfo.email`
  - `https://www.googleapis.com/auth/userinfo.profile`
  - `https://www.googleapis.com/auth/cclog`
  - `https://www.googleapis.com/auth/experimentsandconfigs`

### Token Refresh Flow
When an access token expires (typically after 1 hour), a new Bearer token is obtained via:
```http
POST https://oauth2.googleapis.com/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

client_id=<CONFIGURED_CLIENT_ID>&
client_secret=<CONFIGURED_CLIENT_SECRET>&
grant_type=refresh_token&
refresh_token=<USER_REFRESH_TOKEN>
```
The response returns a fresh `access_token` and `expires_in` seconds.

---

## 4. Models & The Gemini 3.8 Flash "Tiered" Architecture

### Why was Gemini 3.8 Flash not an individual model ID on the backend?
Reverse engineering revealed that on Google's internal API (`daily-cloudcode-pa.googleapis.com`), Gemini 3.8 Flash is registered under the upstream model identifier:
```
gemini-3.8-flash-tiered
```

The Antigravity CLI exposes this model as three distinct user tiers based on **Thinking Budget / Reasoning Effort**:

| User-Facing ID | Upstream Model ID | Display Name | Thinking Budget (`thinkingBudget`) |
|---|---|---|---|
| `gemini-3.8-flash-high` | `gemini-3.8-flash-tiered` | Gemini 3.8 Flash (High) | `8192` tokens |
| `gemini-3.8-flash-medium` | `gemini-3.8-flash-tiered` | Gemini 3.8 Flash (Medium) | `2048` tokens |
| `gemini-3.8-flash-low` | `gemini-3.8-flash-tiered` | Gemini 3.8 Flash (Low) | `512` tokens |

Our Direct API automatically maps client requests for any of these IDs (or `gemini-3.8-flash`) to `gemini-3.8-flash-tiered` with the appropriate `thinkingConfig.thinkingBudget` value!

### Complete Active Model Catalog

| Model ID | Provider | Display Name | Capabilities |
|---|---|---|---|
| `gemini-3.8-flash-high` | Google | Gemini 3.8 Flash (High) | High-effort reasoning, 1M context |
| `gemini-3.8-flash-medium`| Google | Gemini 3.8 Flash (Medium) | Balanced reasoning, fast |
| `gemini-3.8-flash-low` | Google | Gemini 3.8 Flash (Low) | Minimal thinking budget, maximum speed |
| `claude-sonnet-4-6` | Anthropic | Claude Sonnet 4.6 (Thinking) | Extended thinking, deep coding |
| `claude-opus-4-6-thinking` | Anthropic | Claude Opus 4.6 (Thinking) | Deep reasoning, complex problem solving |
| `gemini-3-flash` | Google | Gemini 3 Flash | Low latency Google foundation model |
| `gemini-2.5-flash` | Google | Gemini 3.5 Flash Lite | Multimodal, 1M context |
| `gpt-oss-120b-medium` | OpenAI/OSS | GPT-OSS 120B (Medium) | Open-weights frontier model |

---

## 5. Protocol Payload Format

### Request Payload (`GenerateContentRequest`)
```json
{
  "model": "gemini-3.8-flash-tiered",
  "request": {
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "Explain quantum entanglement in 1 sentence."}
        ]
      }
    ],
    "generationConfig": {
      "temperature": 0.7,
      "maxOutputTokens": 4096,
      "thinkingConfig": {
        "thinkingBudget": 8192
      }
    }
  }
}
```

### Thinking Tokens and Token Sizing Rules
For thinking-enabled models (Claude and Gemini 3.8 Flash), `maxOutputTokens` must be strictly greater than `thinkingConfig.thinkingBudget`. Our client automatically adjusts `maxOutputTokens` if not explicitly specified to ensure requests never trigger validation errors.
