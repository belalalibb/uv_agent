# 🏛️ UNIVERSAL PROVIDER SPECIFICATION & ARCHITECTURAL BLUEPRINT (v1.0)
## Single Source of Truth for Gateway Provider Onboarding & Execution
**Author & Authority:** Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)  
**System:** AI Gateway Service (`__gateway-service/`)  
**Target Audience:** Any AI Coding Agent (Flash / Claude Opus / Sonnet / Codex) or Human Engineer  
**Compliance Standard:** Bolla Constitution v1.2 & ADR-0008 (Gateway Wire Contract v1)  
**Status:** Canonical & Self-Contained (Zero dependency on past chat sessions)  

---

## 📖 1. The Core Philosophy: "HAR In → Production Provider Out"

This document establishes the **Universal Engineering Standard** for onboarding any AI Provider (Syntx, NoteGPT, UseAI, Groq, Kimi, etc.) into the Gateway.

> **The Golden Operational Rule:**  
> The developer or AI agent receives **ONLY the `.har` file** (or raw network endpoints) captured by Eng. Zizo.  
> Everything else—the internal engine, the three core functions, the metadata extraction, the facade adapter, the test suite, and the definition—must be constructed **strictly according to this specification** without asking questions, making assumptions, or guessing.

---

## 🏗️ 2. The Three-Layer Architectural Model (Mandatory)

Every provider package inside `__gateway-service/providers/<provider_slug>/` strictly implements three layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Internal Provider Core (100% Autonomous & Free)                │
│ - Implements: register(), refresh(), ask()                              │
│ - Contains: session handling, token rotation, account pool, raw payloads │
│ - Module prefix convention: private modules begin with '_' (_core.py)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Direct Python call (Internal)
┌────────────────────────────────────▼────────────────────────────────────┐
│ Layer 2: The Mandatory Facade Adapter (adapter.py)                      │
│ - Translates ProviderContext → calls Layer 1 → returns FacadeResult     │
│ - Output MUST be: EITHER canonical success OR 1 of the 12 error taxonomy│
│ - NO third shape exists. NO exceptions escape this layer.               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Enforces Wire Shapes
┌────────────────────────────────────▼────────────────────────────────────┐
│ Layer 3: The Canonical Gateway Contract (gateway/contracts.py)           │
│ - Fixed for all providers. Never extended by a provider.                │
│ - Enforces: RequestEnvelope, ResponseEnvelope, 12 Error Categories.     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 3. Layer 1: The Universal 3-Function Provider Core (`_engine.py` / `_core.py`)

Every provider MUST expose a clean, decoupled core containing **three primary functions**. No sprawling multi-process micro-architectures; clean, direct, robust Python functions.

### Function 1: `register(timeout: int = 120) -> dict`
- **Purpose:** Creates a fresh account using temporary email / automated signup.
- **Input:** Optional `timeout` (seconds).
- **Output:** Returns a dictionary containing valid credentials:
  ```python
  {"email": str, "token": str, "password": str, "created_at": str}
  ```
- **Error Handling:** On failure (e.g. OTP timeout, captcha block), raises a clean internal exception (`UpstreamFailure("provider_unavailable")` or returns `None`). Never hangs indefinitely.

### Function 2: `refresh(account: dict) -> bool`
- **Purpose:** Verifies token validity and available quota.
- **Input:** Account dictionary containing `token` and metadata.
- **Output:** Returns `True` if active with remaining credits; `False` if depleted or expired (triggering atomic eviction from pool).

### Function 3: `ask(model: str, prompt: str, image_b64: str = None, image_format: str = None, timeout: int = 120) -> dict`
- **Purpose:** The central execution engine for chat and vision.
- **Workflow:**
  1. Grabs an active account from the local pool.
  2. If the pool is empty or low, automatically triggers `register()` to replenish.
  3. Validates model capabilities (e.g. rejects images if model is text-only).
  4. Dispatches the request to upstream API (handling streaming, SSE, or polling internally).
  5. If upstream returns `429` or credit depletion, evicts the depleted account and retries with a fresh account.
  6. Returns canonical response dictionary:
     ```python
     {
         "text": str,
         "finish_reason": "stop" | "length" | "filter",
         "input_tokens": int | None,
         "output_tokens": int | None
     }
     ```

---

## 🧠 4. The Dual Capabilities Strategy (Zero Data Loss + v1/v2 Bridge)

Upstream platforms provide rich model capabilities (e.g., `planning`, `deep_research`, `web_explorer`, `files`, `images`, `thinking`).

### A. Inside Provider (Raw Metadata Preservation)
- Every provider MUST store the raw, full capability matrix extracted from the upstream API in an internal JSON/mapping (e.g., `models_metadata.json` or `_config.py`):
  ```json
  {
    "claude-opus-4-8": {
      "thinking": true, "planning": true, "deep_research": true,
      "web_explorer": true, "files": true, "images": true
    },
    "deepseek-r1": {
      "thinking": true, "planning": false, "deep_research": true,
      "web_explorer": false, "files": true, "images": false
    }
  }
  ```
- **Rule:** **NEVER throw away or truncate upstream metadata.** It is the foundation for future capabilities.

### B. At Gateway Boundary (v1 Closed Key Set Projection)
- `gateway/contracts.py` Line 263 enforces a **CLOSED SET** of 14 capability keys in v1:
  `{"chat", "reasoning", "code", "vision_input", "image_generation", "audio_input", "audio_output", "file_upload", "browser", "agent_module", "embeddings", "rerank", "moderation", "tool_use"}`
- In `definition.py`, the provider projects **ONLY** the subset recognized by Gateway v1:
  - Upstream `images == True` ➡️ Declare `"vision_input": True`
  - Upstream `thinking == True` ➡️ Declare `"reasoning": True`
  - Upstream `chat == True` ➡️ Declare `"chat": True`
  - Upstream `code == True` ➡️ Declare `"code": True`
  - Upstream `web_explorer == True` ➡️ Declare `"browser": True`
- **Deny-by-default:** Any key not supported is simply omitted (never declare `key: False`).

### C. The v2 Bridge (Eng. Bolla's Extension Protocol)
- When Eng. Bolla adds new keys (e.g., `"planning"`, `"deep_research"`) to `CAPABILITY_KEYS` in `gateway/contracts.py`:
- The provider can immediately expose them in `definition.py` with zero internal code changes because the raw metadata was already preserved!

---

## 🚫 5. Non-Vision Model Protection (The Anti-Explosion Pattern)

> **Constitutional Rule (`docs/CONTRACT.md#L337`):**  
> `Errors: non-vision model → unsupported_capability`

When a provider supports both text models (e.g. `deepseek-r1`, `qwen3-max`) and vision models (e.g. `claude-opus-4-8`, `gpt-5.6-terra`):
- The provider declares `"capabilities": {"chat": True, "vision_input": True}` and `"operations": ["generate_text", "analyze_vision"]`.
- In `adapter.py::analyze_vision`, the code **MUST check** if the requested model supports images before touching the upstream network:
  ```python
  if not model_supports_vision(context.model):
      return make_error(
          ErrorCategory.UNSUPPORTED_CAPABILITY,
          f"Model {context.model!r} does not support vision/image inputs"
      )
  ```
- **Violation consequence:** Sending an image to a text-only model causes upstream crashes or unhandled 400s, violating the Gateway contract.

---

## 📋 6. Layer 2: The Facade Adapter Contract (`adapter.py`)

### The 8 Supported Operations (v1)

| GatewayOperation | Input Payload Requirements | Canonical Output Schema |
|---|---|---|
| `generate_text` | `messages: list[{role, content}]`, `temperature?`, `max_tokens?` | `{"text": str, "finish_reason": "stop"\|"length"\|"filter"}` |
| `analyze_vision` | `image_b64: str`, `image_format: str`, `instruction: str` | `{"text": str}` |
| `generate_image` | `prompt: str`, `size?`, `count?` | `{"images": [{"b64": str, "format": str}]}` |
| `transcribe_audio` | `audio_b64: str`, `audio_format: str`, `language?` | `{"text": str, "language": str\|null}` |
| `synthesize_speech`| `text: str`, `voice?`, `audio_format?` | `{"audio_b64": str, "format": str}` |
| `create_embeddings`| `texts: list[str]`, `dimensions?` | `{"embeddings": list[list[float]]}` |
| `rerank_documents` | `query: str`, `documents: list[str]`, `top_n?` | `{"results": list[{"index": int, "score": float}]}` |
| `moderate_content` | `content: str` | `{"flagged": bool, "categories": dict[str, bool]}` |

> **Excluded in v1 (ADR-0008 OPEN-2):** `run_provider_agent`, `upload_asset`, `download_asset`. Declaring any of these triggers load-time rejection.

### The 12 Error Categories (Platform-Led)

Every single failure in `adapter.py` MUST be caught and mapped to exactly ONE of these 12 categories:

| ErrorCategory | HTTP Context | Retryable? | When to use |
|---|---|---|---|
| `auth_expired` | 401 | Yes | Session expired; refresh/re-login fixes it |
| `invalid_credential` | 401/403 | No | Revoked/wrong token; permanent |
| `rate_limited` | 429 | Yes | Throttling; set `retry_after_ms` |
| `quota_exceeded` | 402/403 | No | Credits exhausted; no more free tier |
| `model_unavailable` | 404 | No | Model name missing or disabled upstream |
| `provider_unavailable` | 503/Conn | No* | Upstream server completely down |
| `unsupported_capability`| - | No | Feature/vision not supported on this model |
| `bad_request` | 400/422 | No | Invalid image base64, missing payload fields |
| `content_rejected` | 400/Policy | No | Content policy / safety filter refusal |
| `timeout` | 408/504 | Yes | Upstream exceeded `context.timeout_ms` |
| `retryable_server_error`| 500/502 | Yes | Transient upstream server glitch |
| `non_retryable_error` | Other | No | Fallback for unexpected permanent bugs |

---

## 🔒 7. Concurrency & `FileLock` Protocol

When multiple processes (e.g. Uvicorn multi-worker, Gunicorn, or parallel requests) access local accounts:
1. **Single Shared Lock File:** All processes writing or reading the account pool MUST use the **SAME lock file** (`accounts_<provider>.json.lock`).
2. **Atomic Read-Modify-Write Transaction:**
   ```python
   # CORRECT: Single transaction
   with FileLock(lock_file, timeout=15):
       accounts = load_json(accounts_file)
       accounts.append(new_account)
       save_json(accounts_file, accounts)
   ```
   *Never separate read-lock from write-lock, as it causes lost updates.*
3. **No Unlocked Fallbacks:** If `FileLock` times out, raise `UpstreamFailure("provider_unavailable")`. NEVER fall back to reading or writing without a lock.

---

## 🧪 8. Quality Gate & Hermetic Test Suite

Before any provider is considered production-ready:
1. **Hermetic Tests (`tests/providers/test_<slug>.py`):**
   - Must mock all upstream HTTP calls (using `respx` or custom `AsyncBaseTransport`).
   - ZERO network calls permitted during `pytest`.
   - Must assert:
     * Canonical success payload shape.
     * Error mapping (test 401, 429, timeout, model_unavailable).
     * Non-vision rejection (`unsupported_capability`).
     * `DEFINITION` ↔ `HANDLERS` exact parity.
     * Zero-leak: No token, secret, route_token, or internal path appears in `FacadeResult`.
2. **Verification Command:**
   ```bash
   python -m pytest tests/providers/test_<slug>.py -v
   ```

---

## 🏁 9. Summary Blueprint Table

| Component | Standard |
|---|---|
| **Input** | `.har` file only (Network recording) |
| **Layer 1** | Single engine (`register`, `refresh`, `ask`) |
| **Layer 2** | `adapter.py` mapping to canonical `FacadeResult` |
| **Layer 3** | `definition.py` declaring display name, closed capabilities, models |
| **Capabilities** | Preserve all in raw metadata; project 14 keys to Gateway v1 |
| **Vision Gate** | Rejects non-vision models with `unsupported_capability` |
| **Concurrency** | Inter-process `FileLock` with 15s timeout on shared `.lock` |
| **Tests** | Hermetic pytest suite with 100% green pass rate |
