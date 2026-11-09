# 🏛️ UNIVERSAL PROVIDER SPECIFICATION & ARCHITECTURAL BLUEPRINT (v2.0)
## Master Standard for Autonomous Gateway Provider Onboarding & 10x Acceleration
**Authors & Authority:** Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)  
**System:** AI Gateway Service (`__gateway-service/`)  
**Target Audience:** Any AI Coding Agent (Flash / Claude Opus / Sonnet / Codex) & Human Engineers  
**Compliance Standard:** Bolla Constitution v1.2 & ADR-0008 (Gateway Wire Contract v1)  
**Target SLA:** **"Raw HAR In ➡️ Tested Production Provider Out in < 60 Minutes"**  
**Status:** Canonical Master Standard (Version 2.0 — Supersedes v1.0 while preserving backward compatibility)

---

## 📖 1. The Core Philosophy & The 60-Minute SLA

This document establishes the definitive **Universal Engineering Blueprint** for onboarding ANY AI Provider (Syntx, NoteGPT, UseAI, Groq, Kimi, Genspark, etc.) into the AI Gateway Service.

> ### ⚡ The Golden Operational Law:
> The engineer or AI agent receives **ONLY the `.har` file** (or raw network traffic captures) provided by Eng. Zizo.  
> Everything else—the internal HTTP core, session persistence, automatic account replenishment, metadata extraction, facade adapter, non-vision guards, audio transcription, stress suites, and hermetic tests—must be constructed **strictly according to this v2.0 specification** without asking redundant questions, without trial-and-error sprawl, and without modifying Gateway core contracts.

---

## 🏗️ 2. The Canonical Rule of Exactly 4 Clean Files (Zero Sprawl Standard)

A major post-mortem finding from previous implementations is **Agent Sprawl** (generating 10+ fragmented scripts, duplicate account pools, and non-standard CLI wrappers).  
In Blueprint v2.0, every provider inside `__gateway-service/providers/<provider_slug>/` is strictly restricted to **EXACTLY 4 CLEAN FILES**:

```
__gateway-service/providers/<provider_slug>/
├── __init__.py           # Exports DEFINITION and HANDLERS only
├── definition.py         # Declares display name, closed capabilities, operations, and declared models
├── _core.py              # Layer 1: Autonomous engine implementing the 4 Universal Core Functions
└── adapter.py            # Layer 2: Facade Adapter mapping ProviderContext <-> FacadeResult (12 errors)
```

Additional local asset files permitted in the folder:
- `models_metadata.json`: Raw full-fidelity upstream capability matrix.
- `accounts_<provider_slug>.json`: The persistent accounts pool (managed under FileLock).

---

## 🧩 3. Layer 1: The Universal 4-Function Provider Core (`_core.py`)

Every provider core must be autonomous, resilient, and self-healing. It exposes **four universal functions**:

### Function 1: `register(timeout: int = 120) -> dict`
- **Purpose:** Automatically provisions a fresh, fully-verified account using disposable emails or automated signup flows.
- **Session Persistence Standard:**
  - Must use a persistent HTTP session with browser TLS fingerprint impersonation (`curl_cffi.requests.Session(impersonate="chrome124")`).
  - Stateless requests lose session cookies and CSRF tokens, causing upstream IP bans.
- **Livewire & Dynamic DOM Morphing Rule:**
  - If using Livewire-based temporary mail (e.g. Temp-Mail.club), OTP extraction MUST inspect both:
    1. Direct JSON data arrays: `res.json()["serverMemo"]["data"]["messages"]`
    2. Rendered Livewire HTML morphing: `res.json()["effects"]["html"]` via regex `r"\b(\d{6})\b"`.
- **Zero-Purge Mandatory Cleanup (`deleteEmail`):**
  - Always execute mailbox cleanup in a `finally:` block:
    ```python
    try:
        # registration flow
    finally:
        client.delete_email()  # Purges mailbox from upstream server to reset daily accumulation
        client.close()
    ```
- **Return Contract:**
  ```python
  {"email": str, "token": str, "chat_uuid": str, "status": "active", "created_at": str}
  ```

---

### Function 2: `refresh(account: dict) -> bool`
- **Purpose:** Tests token validity and available credits without crashing the caller.
- **Output:** Returns `True` if operational; `False` if revoked or depleted (triggering atomic eviction).

---

### Function 3: `ask(model: str, prompt: str, image_b64: str = None, image_format: str = None, timeout: int = 120) -> dict`
- **Purpose:** Primary inference engine for text generation and multi-modal vision.
- **The 4 Non-Negotiable Pillars of `ask()` in v2.0:**
  1. **Non-Vision Protection Gate:** Intercept text-only models before touching network (throws `UpstreamFailure("unsupported_capability")` in < 5ms).
  2. **Autonomic Feature Injection (Always Enabled by Default):**
     Every text request automatically and unconditionally injects:
     ```python
     payload = {
         "chat_uuid": chat_uuid,
         "text": prompt,
         "model": model,
         "thinking": True,          # Deep reasoning mode
         "plan": True,              # Planning mode
         "deep_research": True,      # Deep web search
         "tools": ["search", "code", "shell", "files", "charts"]
     }
     ```
  3. **Proactive Background Replenishment (`trigger_background_refill`):**
     - Do NOT wait until the pool is empty (which creates a 20s queue during traffic spikes).
     - On every `ask()` call, dispatch a non-blocking background daemon thread to provision 5 fresh accounts into the pool:
       ```python
       def trigger_background_refill(count: int = 5) -> None:
           threading.Thread(target=_background_refill_worker, args=(count,), daemon=True).start()
       ```
  4. **Atomic 7-Day Quota Eviction & Fast Failover:**
     - When upstream returns `429 rateLimitExceeded` with `window_violated: "7d"`, do NOT pause and retry the same exhausted account.
     - Atomically evict the depleted account from `accounts_<slug>.json` via `evict_account(token)`.
     - Immediately grab the next active account from the pool and resume (zero downtime for the caller).
- **Return Contract:**
  ```python
  {
      "text": str,
      "finish_reason": "stop" | "length" | "filter",
      "input_tokens": int | None,
      "output_tokens": int | None
  }
  ```

---

### Function 4: `transcribe_audio(audio_bytes: bytes, audio_format: str = "webm", timeout: int = 60) -> dict`
- **Purpose:** High-fidelity speech-to-text audio transcription.
- **Implementation Pattern:**
  - Dispatches multipart form data to native transcription endpoints (e.g. `POST /api/v1/audio/transcribe`).
  - Passes audio bytes with correct MIME type (`audio/webm;codecs=opus`, `audio/mp3`, `audio/wav`).
  - Injects `Authorization: Bearer <token>` from the active account pool.
  - Returns canonical structure:
    ```python
    {"text": str, "language": str | None, "model": "whisper-1"}
    ```

---

## 🧠 4. The Dual Capabilities Strategy & Metadata Preservation

Upstream providers expose rich, granular features that must never be lost:

### A. Raw Metadata Preservation (`models_metadata.json`)
Store the exact, untruncated JSON structure returned by the provider's `/models` or `/settings` endpoints.

### B. Gateway v1 Closed Capability Projection
In `definition.py`, project **ONLY** the 14 approved keys defined in `gateway/contracts.py`:
`{"chat", "reasoning", "code", "vision_input", "image_generation", "audio_input", "audio_output", "file_upload", "browser", "agent_module", "embeddings", "rerank", "moderation", "tool_use"}`

| Upstream Feature | Projected Gateway v1 Key |
|---|---|
| `images: true` | `"vision_input": True` |
| `thinking: true` / `reasoning: true` | `"reasoning": True` |
| `chat: true` | `"chat": True` |
| `code: true` | `"code": True` |
| `web_search: true` | `"browser": True` |
| `audio/transcribe` supported | `"audio_input": True` |

---

## 🛡️ 5. Non-Vision Model Protection Gate (Zero-Leak Pattern)

To prevent upstream crashes and unhandled 400 errors:
- In `_core.py` and `adapter.py`, check `is_vision_model(model)` before touching the network.
- If an image is passed to a text-only model (e.g. `grok-4.6`, `deepseek-r1`), immediately reject with:
  ```python
  ErrorCategory.UNSUPPORTED_CAPABILITY: f"Model {model!r} does not support vision/image inputs"
  ```
- **Benchmark standard:** Must reject in **< 10ms** with zero network traffic.

---

## 📋 6. Layer 2: Facade Adapter Contract (`adapter.py`)

### The 12 Canonical Error Categories (Strict Mapping)

No internal exception, token, or stack trace may ever cross the Layer 2 boundary. Every error is strictly mapped to one of the 12 platform categories:

| ErrorCategory | Upstream Trigger | Retryable? | Behavior |
|---|---|---|---|
| `auth_expired` | 401 Unauthorized | Yes | Evict account, request retry |
| `invalid_credential` | 401/403 Forbidden | No | Evict account permanently |
| `rate_limited` | 429 Too Many Requests | Yes | Evict 7-day exhausted account, failover |
| `quota_exceeded` | 402 Payment Required | No | Mark account depleted |
| `model_unavailable` | 404 Model Not Found | No | Return model unavailable |
| `provider_unavailable`| 503 / Connect Error | Yes | Retryable provider outage |
| `unsupported_capability`| Vision on text model | No | Non-vision guard interception |
| `bad_request` | 400 / 422 Invalid Payload| No | Malformed image/audio bytes |
| `content_rejected` | 400 Safety Policy Filter | No | Prompt flagged upstream |
| `timeout` | 408 / Deadline Exceeded | Yes | Upstream took too long |
| `retryable_server_error`| 500 / 502 Bad Gateway | Yes | Upstream server glitch |
| `non_retryable_error` | Unhandled / Unknown | No | Defensive fallback |

---

## 🔒 7. Inter-Process Concurrency & `FileLock` Protocol

When running under multi-worker servers (`uvicorn --workers 4`):
1. **Canonical Lock File:** All operations on `accounts_<slug>.json` MUST acquire `accounts_<slug>.json.lock` using `filelock.FileLock(timeout=15)`.
2. **Atomic Read-Modify-Write:**
   - Always read, modify, and write within the **same single lock context**.
   - Write to a temporary file (`accounts_<slug>.json.tmp`) and atomically rename (`replace()`) to prevent JSON corruption during sudden process termination.
3. **Daemon Thread Lifetimes:**
   - In short-lived CLI test scripts, daemon threads terminate when the main process exits.
   - In long-running servers (`app.py`), daemon threads execute continuously in the background to keep the pool primed.

---

## 🧪 8. The Universal Test Triangle (Mandatory Verification)

Every onboarded provider must achieve 100% pass across **three distinct test suites**:

```
                   ▲
                  / \
                 /   \
  Suite 1: Live /     \ Suite 2: Multi-Vector
  Diagnostic   /       \ Stress Suite
 (test_live)  /─────────\ (test_stress)
             /           \
            /  Suite 3:   \
           /   Hermetic    \
          /   Pytest Mocks  \
         ─────────────────────
```

1. **Suite 1: Interactive Live Diagnostic (`test_live_gateway.py`)**
   - Single-command verification of:
     - `▶ [1/5]` Gateway Discovery (`/v1/describe`).
     - `▶ [2/5]` Non-Vision Guard (`grok-4.6` vision call blocked in < 5ms).
     - `▶ [3/5]` Live Text Generation (`claude-opus-4-8` answering prompt).
     - `▶ [4/5]` Live Vision Analysis (Sentinel PNG processed in < 20s).
     - `▶ [5/5]` Live Audio Transcription (`whisper-1` WebM transcription).
2. **Suite 2: Aggressive Multi-Vector Stress Suite (`test_stress_gateway.py`)**
   - 7 stress vectors: model availability audit, flagship models pass, account eviction under 429, and concurrency lock safety.
3. **Suite 3: Hermetic Offline Unit Tests (`tests/providers/test_<slug>.py`)**
   - 100% mocked network calls with zero external network touch.
   - Verifies 12-error category mappings, payload validation, and definition parity.
   - Verification command: `python -m pytest tests/providers/test_<slug>.py`

---

## 🚀 9. Post-Mortem & The 10x Acceleration Formula (Retro)

### 🧐 What Delayed Us During Past Implementations?
1. **Agent Sprawl & Fragmented Architecture:** Spawning 11 different files and conflicting CLI test scripts created confusion and regressions.
2. **Stateless Session Loss:** Disposable email signups failed after 5 accounts because sessions were recreated on every request without cookie persistence.
3. **Livewire DOM Morphing Trap:** Looking only at JSON response data and missing OTP codes arriving inside Livewire HTML morph chunks.
4. **Windows CP1252 Encoding Trap:** Console crashes when printing Arabic characters or neon banners on Windows terminals without `sys.stdout.reconfigure(encoding="utf-8")`.
5. **The 7-Day Rate Limit Confusion:** Assuming 429 meant "wait 2 seconds" instead of recognizing that free tier accounts had their weekly quota depleted and needed immediate eviction.

---

### ⚡ The 10x Acceleration Recipe for Any New Provider (< 60 Minutes)

Follow this 3-step surgical recipe to onboard any new provider from a `.har` file in under one hour:

```
Step 1: The 15-Minute Pre-Lab Probe
├── Parse the .har file: extract auth flow, model list, chat endpoint, vision endpoint, voice endpoint.
└── Create scratch/probe_<slug>.py: verify 1 signup, 1 chat call, and 1 token refresh.

Step 2: The 25-Minute Canonical 4-File Assembly
├── Drop models_metadata.json into providers/<slug>/
├── Write __init__.py (exports DEFINITION, HANDLERS)
├── Write definition.py (projects 14 closed keys & models)
├── Write _core.py (implements register, refresh, ask, transcribe_audio with FileLock)
└── Write adapter.py (maps ProviderContext -> FacadeResult with 12 errors)

Step 3: The 15-Minute Verification & Sealing
├── Run py -3.13 test_live_gateway.py (Verify 5/5 live passes)
├── Run py -3.13 -m pytest tests/providers/test_<slug>.py (Verify 100% green mocks)
└── Git commit and push to remote repository. Done!
```

---

## 📊 10. Master Summary Matrix (v1.0 vs v2.0 Comparison)

| Dimension | Blueprint v1.0 (Baseline) | Blueprint v2.0 (Master Standard) |
|---|---|---|
| **File Architecture** | Loosely defined (3-5 files) | **Strictly Exactly 4 Files** (`__init__`, `definition`, `_core`, `adapter`) |
| **Account Refill** | Reactive (only when pool is 0) | **Proactive Background Daemon** (5 fresh accounts per request) |
| **Email Session** | Basic requests | **Persistent Chrome Impersonation Session + Mandatory Zero-Purge** |
| **OTP Parsing** | JSON data array only | **Dual Mode: JSON data + Livewire HTML DOM Morphing** |
| **Deep Reasoning** | Manual caller invocation | **Autonomic Default** (`thinking: True`, `plan: True`, `tools: [...]`) |
| **Audio Transcription** | Listed in table, unverified | **Fully Implemented & Verified** (`transcribe_audio` with `whisper-1`) |
| **7-Day Rate Limits** | Generic retry | **Atomic Account Eviction & Instant Pool Failover** |
| **Test Standard** | Hermetic pytest only | **The Test Triangle** (Live Diagnostic + Stress Suite + Hermetic Pytest) |
| **Onboarding SLA** | 2-3 days of iteration | **< 60 Minutes Guaranteed** via the 3-Step Lightning Recipe |

---
**Authority Approval:** Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)  
**Approved for Deployment:** Antigravity AI Engine (Flash / Claude Opus 5)
