# ðï¸ UNIVERSAL PROVIDER SPECIFICATION & ARCHITECTURAL BLUEPRINT (v1.1)
## Single Source of Truth for Gateway Provider Onboarding & Execution
**Author & Authority:** Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)  
**System:** AI Gateway Service (`__gateway-service/`)  
**Target Audience:** Any AI Coding Agent (Flash / Claude Opus / Sonnet / Codex) or Human Engineer  
**Compliance Standard:** Bolla Constitution v1.2 & ADR-0008 (Gateway Wire Contract v1)  
**Status:** Canonical & Self-Contained (Zero dependency on past chat sessions)  
**Supersedes:** v1.0 â all defects resolved in this revision are enumerated in Appendix A.

---

## ð Table of Contents

1. [Document Control & Normative Language](#-1-document-control--normative-language)
2. [The Core Philosophy: "HAR In â Production Provider Out"](#-2-the-core-philosophy-har-in--production-provider-out)
3. [Terminology & Architectural Invariants](#-3-terminology--architectural-invariants)
4. [The Three-Layer Architectural Model (Mandatory)](#-4-the-three-layer-architectural-model-mandatory)
5. [Canonical Package Layout](#-5-canonical-package-layout)
6. [Layer 1: The Universal 3-Function Provider Core](#-6-layer-1-the-universal-3-function-provider-core)
7. [Account Lifecycle, Persistence & the FileLock Protocol](#-7-account-lifecycle-persistence--the-filelock-protocol)
8. [The Dual Capabilities Strategy (Zero Data Loss + v1/v2 Bridge)](#-8-the-dual-capabilities-strategy-zero-data-loss--v1v2-bridge)
9. [Non-Vision Model Protection (The Anti-Explosion Pattern)](#-9-non-vision-model-protection-the-anti-explosion-pattern)
10. [The Provider Manifest: `definition.py`](#-10-the-provider-manifest-definitionpy)
11. [Layer 2: The Facade Adapter Contract (`adapter.py`)](#-11-layer-2-the-facade-adapter-contract-adapterpy)
12. [Error Taxonomy, Precedence & the Canonical Error Path](#-12-error-taxonomy-precedence--the-canonical-error-path)
13. [Retry, Failover, Timeout & Backoff Policy](#-13-retry-failover-timeout--backoff-policy)
14. [Security, Redaction & Secret Handling](#-14-security-redaction--secret-handling)
15. [Quality Gate & Hermetic Test Suite](#-15-quality-gate--hermetic-test-suite)
16. [HAR â Production Onboarding Runbook](#-16-har--production-onboarding-runbook)
17. [Definition of Done (Acceptance Checklist)](#-17-definition-of-done-acceptance-checklist)
18. [Summary Blueprint Table](#-18-summary-blueprint-table)
19. [Changelog](#-19-changelog)
- [Appendix A: Defects Resolved Since v1.0](#appendix-a-defects-resolved-since-v10)

---

## ð 1. Document Control & Normative Language

This document is the **single source of truth** for onboarding any AI provider into the Gateway. Where this document and any past chat session, memory, or assistant recollection disagree, **this document wins**.

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are to be interpreted as follows when used in this specification:

| Keyword | Meaning |
|---|---|
| **MUST / MUST NOT** | Absolute requirement. Violation = the provider is rejected at review or load time. |
| **SHOULD** | Strong default. Deviation requires a written justification in the provider's PR description. |
| **MAY** | Genuinely optional; left to the implementer's judgment. |

**In scope:** everything inside `__gateway-service/providers/<provider_slug>/`, its test suite, and its interaction with `gateway/contracts.py`.
**Out of scope:** modifying `gateway/contracts.py`, `gateway` routing code, or any shared infrastructure. Providers **MUST NOT** edit the canonical contract; only Eng. Bolla may extend it (see Â§8.C, the v2 Bridge).

---

## ð 2. The Core Philosophy: "HAR In â Production Provider Out"

This document establishes the **Universal Engineering Standard** for onboarding any AI Provider (Syntx, NoteGPT, UseAI, Groq, Kimi, etc.) into the Gateway.

> **The Golden Operational Rule (Zero-Questions Rule):**  
> The developer or AI agent receives **ONLY the `.har` file** (or raw network endpoints) captured by Eng. Zizo.  
> Everything else â the internal engine, the three core functions, the metadata extraction, the facade adapter, the manifest, the test suite, and the definition â MUST be constructed **strictly according to this specification** without asking questions, making assumptions, or guessing.  
> If the `.har` genuinely lacks information required by a **MUST** rule (e.g., no account-creation flow exists), the implementer documents the gap in the PR description and implements the closest compliant behavior â it MUST NOT invent upstream endpoints or fabricate credentials.

---

## ð§¾ 3. Terminology & Architectural Invariants

### 3.1 Terminology

| Term | Definition |
|---|---|
| **Provider** | An upstream AI service wrapped by one package under `providers/<provider_slug>/`. |
| **HAR** | HTTP Archive file: a browser network capture containing endpoints, headers, cookies, and payload shapes for the upstream service. Treated as a **secret artifact** (see Â§14). |
| **Account** | One upstream credential set (email, token, optional password, metadata) usable to call the upstream API. |
| **Account Pool** | The local, lock-protected JSON file of accounts owned by one provider package. |
| **Eviction** | Atomically removing a dead/depleted account from the pool under the shared lock. |
| **Failover** | Transparently switching to a different account after an account-specific upstream failure, within bounded limits (Â§13). |
| **`ProviderContext`** | The canonical typed input object defined in `gateway/contracts.py` (operation, payload, model, timeout budget, correlation metadata). Referenced by symbol; providers MUST NOT redefine it. |
| **`FacadeResult`** | The canonical typed output object defined in `gateway/contracts.py`. It is EITHER a success payload (per Â§11 table) OR an error (per Â§12). No third shape exists. |
| **`DEFINITION` / `HANDLERS`** | The manifest objects exported by each provider's `definition.py` (Â§10). |
| **`UpstreamFailure`** | The provider-internal exception type raised by Layer 1. It never crosses Layer 2's boundary as an exception (Â§12). |
| **Hermetic** | A test environment with zero real network access; every upstream call is mocked. |
| **CAPABILITY_KEYS** | The closed 14-key set defined in `gateway/contracts.py` (Â§8.B). |

### 3.2 Architectural Invariants (Non-Negotiable)

1. **I1 â Two shapes only.** Every adapter call returns exactly one `FacadeResult`: canonical success OR one of the 12 error categories. No exceptions escape `adapter.py`.
2. **I2 â Contract immutability.** `gateway/contracts.py` is fixed for all providers. Providers consume it; they never extend it.
3. **I3 â Manifest/Handler parity.** `DEFINITION` and `HANDLERS` MUST declare exactly the same operation set, validated at load time (Â§10.3).
4. **I4 â Atomic state.** All reads/writes of the account pool happen inside a single FileLock-protected transaction (Â§7). No unlocked fallbacks exist.
5. **I5 â Hermetic tests.** The provider test suite performs zero real network I/O (Â§15).
6. **I6 â Deny-by-default capabilities.** A capability not supported by a model is **omitted**, never declared `key: False` (Â§8.B).
7. **I7 â Zero secret leakage.** No token, cookie, password, route token, or internal file path ever appears in a `FacadeResult`, a log line, or a committed file (Â§14).

---

## ðï¸ 4. The Three-Layer Architectural Model (Mandatory)

Every provider package inside `__gateway-service/providers/<provider_slug>/` strictly implements three layers:

```
âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â Layer 1: Internal Provider Core (100% Autonomous & Free)                â
â Files: _core.py, _config.py, _accounts.py, models_metadata.json         â
â - Implements: register(), refresh(), ask()                              â
â - Contains: session handling, token rotation, account pool, raw payloads â
â - Convention: private/internal modules are prefixed with '_'            â
â - Free to use any internal design, as long as it honors Â§6, Â§7, Â§13, Â§14 â
ââââââââââââââââââââââââââââââââââââââ¬âââââââââââââââââââââââââââââââââââââ
                                     â Direct Python call (Internal)
ââââââââââââââââââââââââââââââââââââââ¼âââââââââââââââââââââââââââââââââââââ
â Layer 2: The Mandatory Facade Adapter (adapter.py)                      â
â - Translates ProviderContext â calls Layer 1 â returns FacadeResult     â
â - Output MUST be: canonical success OR 1 of the 12 error categories     â
â - NO third shape exists. NO exceptions escape this layer.               â
ââââââââââââââââââââââââââââââââââââââ¬âââââââââââââââââââââââââââââââââââââ
                                     â Enforces Wire Shapes
ââââââââââââââââââââââââââââââââââââââ¼âââââââââââââââââââââââââââââââââââââ
â Layer 3: The Canonical Gateway Contract (gateway/contracts.py)           â
â - Fixed for all providers. Never extended by a provider.                â
â - Defines: ProviderContext, FacadeResult, RequestEnvelope,               â
â   ResponseEnvelope, the 12 ErrorCategory values, GatewayOperation,       â
â   and the closed CAPABILITY_KEYS set.                                    â
âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
```

> **Clarification (resolves the v1.0 ambiguity):** `definition.py` is **NOT a layer**. It is the provider-owned **manifest/discovery component** consumed by the Gateway's provider registry (Â§10). Layer 3 is exclusively `gateway/contracts.py`.

---

## ð 5. Canonical Package Layout

Every provider package MUST follow this exact layout (files may grow internally, but this skeleton is mandatory):

```
__gateway-service/
âââ gateway/
â   âââ contracts.py                     # Layer 3 â canonical, provider-READ-ONLY
âââ providers/
â   âââ <provider_slug>/                 # e.g. providers/syntx/
â       âââ __init__.py                  # re-exports DEFINITION and HANDLERS
â       âââ adapter.py                   # Layer 2 â facade (Â§11)
â       âââ definition.py                # Manifest: DEFINITION + HANDLERS (Â§10)
â       âââ _core.py                     # Layer 1 â register(), refresh(), ask() (Â§6)
â       âââ _accounts.py                 # Pool load/claim/evict under FileLock (Â§7)
â       âââ _config.py                   # Endpoints, headers, static constants â NO secrets
â       âââ models_metadata.json         # RAW upstream capability matrix, verbatim (Â§8.A)
âââ data/
â   âââ accounts_<provider_slug>.json    # Runtime pool state (gitignored, 0600 perms)
â   âââ accounts_<provider_slug>.json.lock  # Shared lock file (Â§7)
âââ tests/
    âââ providers/
        âââ test_<provider_slug>.py      # Hermetic suite (Â§15)
```

**Rules:**
- Runtime state (`data/accounts_*.json*`) MUST be gitignored and MUST NOT live inside the package directory.
- `models_metadata.json` is committed; `accounts_*.json` is never committed.
- Any additional private helpers live as `_*.py` modules inside the package.

---

## ð§© 6. Layer 1: The Universal 3-Function Provider Core (`_core.py`)

Every provider MUST expose a clean, decoupled core containing **three primary functions**. No sprawling multi-process micro-architectures; clean, direct, robust Python functions. Layer 2 builds all eight Gateway operations on top of these three functions (see Â§11 mapping table).

### Function 1: `register(timeout: int = 120) -> dict`

- **Purpose:** Creates a fresh upstream account using temporary email / automated signup, per the flow observed in the HAR.
- **Input:** Optional `timeout` in **seconds** (default 120).
- **Success output â exactly this shape:**
  ```python
  {
      "email": str,            # working upstream account identifier
      "token": str,            # session/API token extracted from the HAR-observed flow
      "password": str | None,  # None for flows without a password
      "created_at": str        # ISO-8601 UTC timestamp, e.g. "2025-01-01T12:00:00Z"
  }
  ```
- **Failure behavior (single, mandatory):** On ANY failure â OTP timeout, captcha block, signup flow mismatch, network error â the function **MUST raise `UpstreamFailure`** with reason `"provider_unavailable"` (or a more specific internal reason string for logging). 
  - It MUST **never** return `None`, a partial dict, or a sentinel value.
  - It MUST **never** hang past its timeout: an internal deadline cancels the attempt and raises.
- **Persistence:** The newly created account is appended to the pool **only** via the atomic transaction of Â§7 â never written directly by `_core.py`.

### Function 2: `refresh(account: dict) -> bool`

- **Purpose:** Verifies token validity and remaining quota against the upstream API, using the HAR-observed verification endpoint.
- **Input:** Account dictionary containing at least `token` and metadata.
- **Output:**
  - `True` â account is active with remaining credits.
  - `False` â upstream **confirmed** the account is expired, revoked, or depleted. The caller (pool layer) then performs **atomic eviction** (Â§7).
- **Transient failure:** If verification itself fails due to network/5xx flakiness, the function MUST raise `UpstreamFailure("provider_unavailable")` rather than return `False`. Returning `False` on a flaky network would wrongly evict healthy accounts.
- **Purity:** `refresh()` is a **read-only** upstream check. It MUST NOT mutate the pool file itself; eviction is performed by the pool layer inside the lock.

### Function 3: `ask(model: str, prompt: str, image_b64: str | None = None, image_format: str | None = None, timeout: int = 120) -> dict`

- **Purpose:** The central execution engine for chat and vision.
- **Mandatory workflow (bounded, no recursion):**
  1. Grabs an active account from the local pool (Â§7 claim operation).
  2. If the pool is empty or below the low-water mark, triggers **at most one** `register()` call to replenish. If registration fails, the failure propagates as `UpstreamFailure` â it MUST NOT loop.
  3. Validates model capabilities **locally, before any network call**: if `image_b64` is provided and the model has no vision capability in `models_metadata.json`, raise `UpstreamFailure` with reason `"unsupported_capability"` immediately.
  4. Dispatches the request to the upstream API exactly as captured in the HAR (handling streaming, SSE, or polling internally).
  5. On account-specific upstream failure (`401` recoverable session, `429` per-account throttle, or confirmed credit depletion), **evicts or suspends the offending account** under the lock and retries with a different account â bounded by `MAX_ACCOUNT_ATTEMPTS = 3` total account attempts per `ask()` call (Â§13). No recursion; a flat loop.
  6. If all bounded attempts fail, raises `UpstreamFailure` with the most specific reason from the last attempt (classified by the adapter into the Â§12 taxonomy).
- **Success output â exactly this shape:**
  ```python
  {
      "text": str,
      "finish_reason": "stop" | "length" | "filter",
      "input_tokens": int | None,
      "output_tokens": int | None
  }
  ```
- **Timeout:** `timeout` is in **seconds**. The adapter converts the Gateway budget `context.timeout_ms` (milliseconds) using `core_timeout = max(1, context.timeout_ms // 1000)` (Â§13.4).

---

## ð 7. Account Lifecycle, Persistence & the FileLock Protocol

When multiple processes (e.g. Uvicorn multi-worker, Gunicorn, or parallel requests) access local accounts:

1. **Single Shared Lock File:** All processes reading or writing the account pool MUST use the **SAME lock file**: `data/accounts_<provider_slug>.json.lock`. Lock timeout: **15 seconds**.
2. **Atomic Read-Modify-Write Transaction:**
   ```python
   # CORRECT: a single transaction covering read â mutate â write
   with FileLock(lock_file, timeout=15):
       accounts = load_json(accounts_file)
       accounts.append(new_account)          # or: claim / evict / mark-depleted
       save_json_atomic(accounts_file, accounts)
   ```
   - **Never** separate the read-lock from the write-lock â that causes lost updates.
   - `save_json_atomic` MUST write to a temporary file in the same directory and `os.replace()` it onto the target, so readers never observe a half-written file.
3. **No Unlocked Fallbacks:** If `FileLock` times out, raise `UpstreamFailure("provider_unavailable")`. It is **forbidden** to read or write the pool without holding the lock, even "just this once".
4. **Claim semantics:** Claiming an account selects the least-recently-used active account and updates its `last_used_at` **inside the same lock transaction** as any eviction/replenishment performed in step 5 of `ask()`.
5. **Eviction semantics:** An account is evicted only when the upstream **confirmed** death (refresh returned `False`, or upstream returned a definitive 401/402/403-quota response). Transient 5xx/network errors never evict.
6. **Corruption recovery:** If the pool JSON fails to parse, the pool layer MUST quarantine the corrupt file (rename with a `.corrupt-<timestamp>` suffix), log a redacted warning (Â§14), and treat the pool as empty. It MUST NOT crash the process.

---

## ð§  8. The Dual Capabilities Strategy (Zero Data Loss + v1/v2 Bridge)

Upstream platforms provide rich model capabilities (e.g., `planning`, `deep_research`, `web_explorer`, `files`, `images`, `thinking`).

### A. Inside Provider (Raw Metadata Preservation)

- Every provider MUST store the **raw, full capability matrix** extracted from the upstream API in `models_metadata.json` (or an equivalent `_*.py` mapping), verbatim and untruncated:
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
- Each entry SHOULD also record `"source": "har|api|docs"` and, when known, `"captured_at"`, so future audits can trace provenance.
- **Rule:** **NEVER throw away or truncate upstream metadata.** It is the foundation for future capabilities.

### B. At Gateway Boundary (v1 Closed Key Set Projection)

- `CAPABILITY_KEYS` in `gateway/contracts.py` enforces a **CLOSED SET of 14 capability keys** in v1:
  `{"chat", "reasoning", "code", "vision_input", "image_generation", "audio_input", "audio_output", "file_upload", "browser", "agent_module", "embeddings", "rerank", "moderation", "tool_use"}`
- In `definition.py`, the provider projects **ONLY** the subset recognized by Gateway v1:

  | Upstream raw flag (models_metadata.json) | Gateway v1 declaration |
  |---|---|
  | `images == True` (understanding/accepting images) | `"vision_input": true` |
  | `thinking == True` | `"reasoning": true` |
  | `chat == True` | `"chat": true` |
  | `code == True` | `"code": true` |
  | `web_explorer == True` | `"browser": true` |

- **Deny-by-default:** Any key not supported is simply **omitted** â never declare `key: False`.
- **Distinction:** Upstream *image input* maps to `vision_input`. Upstream *image generation* (a generation endpoint in the HAR) maps to `image_generation`. These are independent flags; never infer one from the other.

### C. The v2 Bridge (Eng. Bolla's Extension Protocol)

- When Eng. Bolla adds new keys (e.g., `"planning"`, `"deep_research"`) to `CAPABILITY_KEYS` in `gateway/contracts.py`, the provider can immediately expose them in `definition.py` with **zero internal code changes**, because the raw metadata was already preserved in Â§8.A. The only edit is a one-line projection addition in `definition.py`.

---

## ð« 9. Non-Vision Model Protection (The Anti-Explosion Pattern)

> **Constitutional Rule (`docs/CONTRACT.md`, Â§ Errors):**  
> `non-vision model â unsupported_capability`

When a provider supports both text models (e.g. `deepseek-r1`, `qwen3-max`) and vision models (e.g. `claude-opus-4-8`, `gpt-5.6-terra`):

- The provider declares `"capabilities": {"chat": true, "vision_input": true}` and `"operations": ["generate_text", "analyze_vision"]` **only on the models that actually support vision**.
- In `adapter.py::analyze_vision`, the code **MUST check** whether the requested model supports images **before touching the upstream network**:
  ```python
  if not model_supports_vision(context.model):
      return make_error(
          ErrorCategory.UNSUPPORTED_CAPABILITY,
          f"Model {context.model!r} does not support vision/image inputs"
      )
  ```
- The check reads from the **projected** model-level capabilities in `DEFINITION` (or the raw matrix) â never from a hardcoded list of "known vision models".
- **Violation consequence:** Sending an image to a text-only model causes upstream crashes or unhandled 400s, violating the Gateway contract and producing a misleading error category.

---

## ðï¸ 10. The Provider Manifest: `definition.py`

`definition.py` is the provider-owned manifest and discovery surface. It exports exactly two module-level symbols:

### 10.1 `DEFINITION`

A manifest object constructed with the helpers provided by `gateway/contracts.py` (never hand-rolled dicts), declaring:

- `provider_slug`: unique, lowercase, URL-safe identifier (matches the package directory name).
- `display_name`: human-readable provider name.
- `models`: a list where each entry declares:
  - `id`: the model identifier as exposed to Gateway callers,
  - `display_name`,
  - `capabilities`: a **subset** of the 14 closed v1 keys (Â§8.B, deny-by-default),
  - `operations`: the list of supported `GatewayOperation` values for this model, drawn **only** from the 8 supported operations (Â§11).

### 10.2 `HANDLERS`

A mapping of `GatewayOperation â adapter function` exported from `adapter.py`:

```python
HANDLERS = {
    GatewayOperation.GENERATE_TEXT: adapter.generate_text,
    GatewayOperation.ANALYZE_VISION: adapter.analyze_vision,
    # ... only operations this provider actually implements
}
```

### 10.3 Load-Time Validation Rules (executed at import)

The package MUST fail fast â raising at import time â if any of the following is violated:

| # | Rule | Violation behavior |
|---|---|---|
| V1 | Every capability key used anywhere is a member of `CAPABILITY_KEYS` | `ImportError` |
| V2 | Every operation key in `HANDLERS` is one of the 8 supported v1 operations | `ImportError` |
| V3 | Declaring any excluded operation (`run_provider_agent`, `upload_asset`, `download_asset`) | **Load-time rejection** (ADR-0008 OPEN-2) |
| V4 | `DEFINITION` â `HANDLERS` **exact parity**: every operation referenced by any model in `DEFINITION` has a handler, and every handler is referenced by at least one model | `ImportError` |
| V5 | Model IDs are unique within the provider; `provider_slug` matches the package directory | `ImportError` |
| V6 | No import-time network calls, threads, subprocesses, or file writes (imports must be side-effect-free) | `ImportError` / review rejection |
| V7 | Every capability value is `True` (deny-by-default; `False` declarations are rejected) | `ImportError` |

---

## ð§± 11. Layer 2: The Facade Adapter Contract (`adapter.py`)

### 11.1 Structural Contract

- Each handler is a function `async def <operation>(context: ProviderContext) -> FacadeResult`.
- Every handler follows the same canonical skeleton:
  ```python
  async def generate_text(context: ProviderContext) -> FacadeResult:
      try:
          _validate_local(context)                 # Â§12 step 1 â no network
          core_result = await _dispatch_to_core(context)
          return make_success(core_result)         # canonical success payload
      except UpstreamFailure as exc:
          return make_error(_classify(exc), exc.reason)   # Â§12 mapping
      except Exception:
          return make_error(
              ErrorCategory.NON_RETRYABLE_ERROR,
              "unexpected internal failure"
          )
  ```
  (`make_success`, `make_error`, `ErrorCategory` are canonical symbols from `gateway/contracts.py`.)
- The bare `except Exception` is the **last line of defense**, guaranteeing invariant I1. It MUST NOT be used as a substitute for proper classification.

### 11.2 The 8 Supported Operations (v1) and Their Mapping to the Core

| GatewayOperation | Input Payload Requirements | Canonical Success Payload | Built on Layer 1 via |
|---|---|---|---|
| `generate_text` | `messages: list[{role, content}]`, `temperature?`, `max_tokens?` | `{"text": str, "finish_reason": "stop"\|"length"\|"filter", "input_tokens": int\|null, "output_tokens": int\|null}` | `ask()` |
| `analyze_vision` | `image_b64: str`, `image_format: str`, `instruction: str` | `{"text": str}` | `ask()` (with image, after Â§9 gate) |
| `generate_image` | `prompt: str`, `size?`, `count?` | `{"images": [{"b64": str, "format": str}]}` | provider-specific core extension of `ask()`/upstream generation endpoint |
| `transcribe_audio` | `audio_b64: str`, `audio_format: str`, `language?` | `{"text": str, "language": str\|null}` | provider-specific core extension |
| `synthesize_speech` | `text: str`, `voice?`, `audio_format?` | `{"audio_b64": str, "format": str}` | provider-specific core extension |
| `create_embeddings` | `texts: list[str]`, `dimensions?` | `{"embeddings": list[list[float]]}` | provider-specific core extension |
| `rerank_documents` | `query: str`, `documents: list[str]`, `top_n?` | `{"results": [{"index": int, "score": float}]}` | provider-specific core extension |
| `moderate_content` | `content: str` | `{"flagged": bool, "categories": dict[str, bool]}` | provider-specific core extension |

- **Operations the provider does not support are simply absent** from `HANDLERS` and from every model's `operations` list â never stubbed, never faked.
- Provider-specific extensions beyond the three core functions MUST live in private `_*.py` modules and MUST honor the same error-raising (`UpstreamFailure`), locking, timeout, and redaction rules as the core.

> **Excluded in v1 (ADR-0008 OPEN-2):** `run_provider_agent`, `upload_asset`, `download_asset`. Declaring any of these triggers load-time rejection (rule V3).

### 11.3 Local Validation Before Network (mandatory in every handler)

Before any upstream call, the handler MUST validate locally, in order: declared operation on the model â model exists in `DEFINITION` â payload shape (required fields, base64 decodability, format allowlist) â capability gate (Â§9). Local failures map to `bad_request`, `model_unavailable`, or `unsupported_capability` per Â§12 â with **zero** network cost.

---

## â ï¸ 12. Error Taxonomy, Precedence & the Canonical Error Path

### 12.1 The 12 Error Categories

Every single failure in `adapter.py` MUST be caught and mapped to exactly ONE of these 12 categories. **Failover** means "may trigger switching to another account within the bounded retry of Â§13".

| ErrorCategory | HTTP Context | Failover? | Retryable by Gateway? | When to use |
|---|---|---|---|---|
| `auth_expired` | 401 (session recoverable) | Yes | Yes | Session expired; refresh/re-login fixes it |
| `invalid_credential` | 401/403 (revoked/wrong) | Yes (evict) | No | Revoked or permanently wrong token |
| `rate_limited` | 429 | Yes (per-account) | Yes | Throttling; set `retry_after_ms` |
| `quota_exceeded` | 402 / 403-quota | Yes (evict) | No | Credits exhausted on this account; account-level failover only |
| `model_unavailable` | 404 | No | No | Model name missing or disabled upstream |
| `provider_unavailable` | 503 / conn refused / DNS / pool-lock timeout | No | No | Upstream infrastructure completely down |
| `unsupported_capability` | â (local gate) | No | No | Feature/vision not supported on this model |
| `bad_request` | 400/422 (payload-shape causes) | No | No | Invalid image base64, missing payload fields |
| `content_rejected` | 400/policy markers | No | No | Content policy / safety filter refusal |
| `timeout` | 408/504 / local deadline hit | Yes | Yes | Upstream exceeded the timeout budget |
| `retryable_server_error` | 500/502 | No | Yes | Transient upstream server glitch |
| `non_retryable_error` | Anything else | No | No | Fallback for unexpected permanent bugs |

### 12.2 Error Precedence (deterministic classification order)

Classification MUST follow this exact order, stopping at the first match:

1. **Local gate failures (no network touched):** undeclared operation or unknown model â `model_unavailable`; shape/format/base64 problems â `bad_request`; capability gate â `unsupported_capability`.
2. **Pool lock timeout** â `provider_unavailable`.
3. **Upstream response classification** (inspect status first, then body markers):
   - `401` â try account `refresh()`: refresh succeeds â transparent failover (Â§13); refresh confirms revocation â `invalid_credential`; refresh itself failed transiently â `auth_expired`.
   - `402`, or `403` whose body indicates credits/plan exhaustion â `quota_exceeded`.
   - `403` otherwise (revoked/banned) â `invalid_credential`.
   - `404` â `model_unavailable`.
   - `408` or `504`, or local deadline exceeded â `timeout`.
   - `400`/`422` â body contains a policy/safety marker â `content_rejected`; otherwise â `bad_request`.
   - `429` â `rate_limited` (set `retry_after_ms`, Â§12.3).
   - `500`/`502` â `retryable_server_error`.
   - `503`, connection refused/reset, DNS failure â `provider_unavailable`.
   - Any other status â `non_retryable_error`.
4. **Unexpected exception** (anything not raised as `UpstreamFailure`) â `non_retryable_error`.

### 12.3 `retry_after_ms` Rule

- `retry_after_ms` is set **only** on `rate_limited` errors.
- Value: honor the upstream `Retry-After` header when present (seconds â milliseconds); otherwise default to `1000` ms.
- No other category ever carries `retry_after_ms`.

### 12.4 Error Message Discipline

- Error `reason` strings MUST be stable, lowercase, snake_case, and human-actionable (e.g. `"model deepseek-r1 does not support vision/image inputs"`).
- Error messages MUST pass the Â§14 redaction filter: no tokens, cookies, emails, or raw URLs with credentials.

---

## â±ï¸ 13. Retry, Failover, Timeout & Backoff Policy

All retry logic is **bounded and flat** (no recursion), executed inside Layer 1/2:

1. **`MAX_ACCOUNT_ATTEMPTS = 3`.** Within one `ask()` call, at most **3 account attempts** total. After the last failed attempt, the final `UpstreamFailure` propagates and the adapter maps it per Â§12.
2. **Failover-eligible errors only:** `auth_expired` (recoverable), per-account `rate_limited`, per-account `quota_exceeded`, `invalid_credential`, `timeout`. 
   **Never failover on:** `unsupported_capability`, `bad_request`, `content_rejected`, `model_unavailable`, `provider_unavailable`, `non_retryable_error`, `retryable_server_error` â these are request-level or provider-level, and switching accounts cannot fix them.
3. **Replenishment bound:** at most **one** `register()` call per `ask()` invocation. Registration failure ends the call immediately.
4. **Timeout budget:** the Gateway provides `context.timeout_ms` (milliseconds). The adapter converts once: `core_timeout_seconds = max(1, context.timeout_ms // 1000)` and passes it down. Deadlines are enforced locally (cancel the in-flight attempt) â the adapter never waits indefinitely on the core.
5. **Backoff ownership:** the adapter reports `retry_after_ms` (Â§12.3); the **Gateway** owns actual retry scheduling and exponential backoff. The adapter MUST NOT sleep-and-retry whole operations on its own beyond the bounded account failover above.
6. **No infinite loops, anywhere.** Any loop touching the network or the pool MUST have a compile-time-visible bound.

---

## ð¡ï¸ 14. Security, Redaction & Secret Handling

1. **HAR files are secrets.** They contain live cookies, tokens, and session identifiers. They MUST be stored outside version control (gitignored), shared only through the team's secret channel, and deleted after onboarding.
2. **Committed files are secret-free.** `_config.py`, `definition.py`, `models_metadata.json`, and tests MUST NOT contain tokens, cookies, passwords, or real account emails. Endpoint URLs and static header names are fine; credential values are not.
3. **Runtime state permissions.** `data/accounts_<slug>.json` (and its lock file) MUST be gitignored and created with owner-only permissions (`0600` / `0700` directory where supported).
4. **Logging redaction.** Every log line MUST pass through a redaction filter removing: `token`, `authorization`, `cookie`, `route_token`, session IDs, passwords, and account emails. Log account identity by **pool index/id**, never by email or token.
5. **Zero-leak facade (invariant I7).** `FacadeResult` MUST contain only the canonical payload fields. Before returning success or error, the adapter MUST NOT include: upstream tokens/cookies, internal file paths (`data/accounts_*.json`), pool emails, or raw upstream URLs containing query-string credentials.
6. **No secrets in exceptions.** `UpstreamFailure.reason` carries a category and short reason string â never a dump of the upstream response body. Upstream bodies may be logged only after redaction, at DEBUG level, and only when a debug flag is explicitly enabled.

---

## ð§ª 15. Quality Gate & Hermetic Test Suite

Before any provider is considered production-ready:

1. **Location:** `tests/providers/test_<provider_slug>.py`.
2. **Hermetic by construction:**
   - All upstream HTTP calls MUST be mocked (using `respx` or a custom `AsyncBaseTransport`).
   - **ZERO real network calls permitted during `pytest`** â a test session that opens a socket to the internet fails the quality gate.
3. **Mandatory assertions:**
   -  Canonical success payload shape for every declared operation.
   -  Error mapping: simulate `401`, `429` (assert `retry_after_ms` present), `timeout`, `404` â `model_unavailable`, and `503` â `provider_unavailable`.
   -  Non-vision rejection: sending an image to a text-only model returns `unsupported_capability` **with zero upstream calls made**.
   -  `DEFINITION` â `HANDLERS` exact parity (re-run rule V4 in tests, independent of import time).
   -  Zero-leak: no token, secret, route_token, email, or internal path appears in any returned `FacadeResult` (assert against a known sentinel account).
   -  `register()` failure path **raises** `UpstreamFailure` â the test proves `None` is never returned.
   -  Bounded retry: with a permanently failing upstream (per-account 429/depletion), `ask()` makes at most 3 account attempts and then surfaces a canonical error.
   -  Pool lock contention: two concurrent claims/evictions never corrupt the pool file (atomicity smoke test).
4. **Verification command:**
   ```bash
   python -m pytest tests/providers/test_<provider_slug>.py -v
   ```
   A production-ready provider requires a **100% green pass rate** on this suite.

---

## ð 16. HAR â Production Onboarding Runbook

Execute strictly in order. Do not skip steps; do not ask questions covered by this spec.

| Step | Action | Spec reference |
|---|---|---|
| 1 | Receive the `.har` file (or endpoints) from Eng. Zizo. Store it **outside** version control. | Â§14.1 |
| 2 | Extract from the HAR: base URL, auth/session headers, signup flow, chat/vision endpoint(s), request/response payload shapes, error response shapes, model list, capability signals. | Â§2, Â§8.A |
| 3 | Write `models_metadata.json` with the **raw, full** capability matrix + provenance. | Â§8.A |
| 4 | Create the package skeleton exactly per the canonical layout. | Â§5 |
| 5 | Implement `_core.py` (`register`, `refresh`, `ask`) honoring single-behavior errors, bounded workflow, and timeouts. | Â§6 |
| 6 | Implement `_accounts.py` (claim/evict/replenish) with the shared FileLock and atomic replace. | Â§7 |
| 7 | Implement `adapter.py`: 8-operation mapping, local validation first, canonical skeleton, Â§12 classification. | Â§11, Â§12 |
| 8 | Write `definition.py`: `DEFINITION` (closed capabilities, deny-by-default) + `HANDLERS`; ensure import-time validation passes (V1âV7). | Â§8.B, Â§10 |
| 9 | Write the hermetic test suite and run it to 100% green. | Â§15 |
| 10 | Run the Definition of Done checklist; attach the green test output to the PR. | Â§17 |

---

##  17. Definition of Done (Acceptance Checklist)

A provider is production-ready **if and only if** every box is checked:

- [ ] Package layout matches Â§5 exactly; no runtime state inside the package directory.
- [ ] `register()` raises `UpstreamFailure` on failure and never returns `None` or hangs.
- [ ] `refresh()` returns `False` only on upstream-confirmed death; transient errors raise.
- [ ] `ask()` respects `MAX_ACCOUNT_ATTEMPTS = 3` and â¤ 1 replenishment per call; no recursion.
- [ ] All pool mutations occur inside the shared-lock atomic transaction; lock timeout â `provider_unavailable`; no unlocked fallbacks; atomic file replace in use.
- [ ] `models_metadata.json` preserves the full raw capability matrix with provenance.
- [ ] `definition.py` projects only keys from the closed 14-key set, deny-by-default, values `True` only.
- [ ] V1âV7 load-time validations pass; excluded v1 operations are absent.
- [ ] Every declared operation returns only canonical success payloads or Â§12 categories; no exception ever escapes `adapter.py`.
- [ ] Non-vision gate rejects with `unsupported_capability` before any network call.
- [ ] Error precedence table (Â§12.2) is implemented in the stated order; `retry_after_ms` only on `rate_limited`.
- [ ] Redaction filter covers all logs; `FacadeResult` passes the zero-leak assertion.
- [ ] Hermetic test suite: 100% green, zero real network sockets during `pytest`, all Â§15 assertions present.

---

## ð 18. Summary Blueprint Table

| Component | Standard |
|---|---|
| **Input** | `.har` file only (network recording) â treated as a secret artifact |
| **Layer 1** | Single engine (`register`, `refresh`, `ask`) in private `_*.py` modules |
| **Layer 2** | `adapter.py` mapping `ProviderContext` â canonical `FacadeResult`; no exceptions escape |
| **Layer 3** | `gateway/contracts.py` â canonical, immutable, provider-read-only |
| **Manifest** | `definition.py` exporting `DEFINITION` + `HANDLERS` with load-time parity validation |
| **Capabilities** | Preserve all raw metadata; project the closed 14-key set, deny-by-default |
| **Vision Gate** | Non-vision models rejected with `unsupported_capability`, pre-network |
| **Errors** | 12 categories, deterministic precedence, `retry_after_ms` on `rate_limited` only |
| **Retry** | Bounded: 3 account attempts max, â¤ 1 `register()` per call, flat loops only |
| **Concurrency** | Inter-process `FileLock` (15s timeout) on a shared `.lock` file; atomic read-modify-write; atomic file replace |
| **Security** | HAR handled as secret; redacted logging; 0600 runtime state; zero-leak facade |
| **Tests** | Hermetic pytest suite, zero network, 100% green pass rate |

---

## ðï¸ 19. Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | â | Eng. Bolla & Eng. Zizo | Initial canonical specification. |
| 1.1 | â | Eng. Bolla (Architectural Audit) | Hardened specification: single-behavior `register()` error contract; bounded retry/failover policy (`MAX_ACCOUNT_ATTEMPTS`); deterministic error-precedence table; `Failover` column replacing ambiguous retryability marks; `definition.py` reclassified as manifest (Layer 3 fixed to `contracts.py`); added package layout, manifest validation rules V1âV7, timeout unit conversion, pool corruption recovery, security/redaction section, onboarding runbook, and Definition-of-Done checklist; replaced line-number references with stable symbol references; added changelog and Appendix A. |

---

## Appendix A: Defects Resolved Since v1.0

1. **Layer-model contradiction** â Â§2 (contracts.py) vs Â§9 (definition.py). Resolved: Layer 3 is `gateway/contracts.py` only; `definition.py` is the provider manifest (Â§4, Â§10).
2. **`register()` dual behavior** â "raises or returns None". Resolved: failure always raises `UpstreamFailure`; `None` returns are forbidden (Â§6).
3. **Unbounded retry risk** â 429/depletion handling could loop forever. Resolved: `MAX_ACCOUNT_ATTEMPTS = 3`, â¤ 1 replenishment per call, recursion forbidden (Â§13).
4. **Retryability contradiction** â `quota_exceeded` marked non-retryable while `ask()` mandated retrying. Resolved: account-level failover separated from operation-level retry via the explicit `Failover` column (Â§12.1, Â§13.2).
5. **Dangling footnote marker** on `provider_unavailable`. Resolved: explicit failover/retryability semantics (Â§12.1).
6. **Brittle line-number references** (`contracts.py#L263`, `CONTRACT.md#L337`). Resolved: stable symbol/section references (`CAPABILITY_KEYS`, Â§ Errors).
7. **Undefined referenced symbols** (`ProviderContext`, `FacadeResult`, `DEFINITION`, `HANDLERS`, `UpstreamFailure`). Resolved: terminology section with by-symbol referencing â no invented fields for gateway-owned types (Â§3.1).
8. **Core/facade coverage mismatch** â 3 core functions vs 8 operations. Resolved: explicit per-operation mapping table and rules for provider-specific core extensions (Â§11.2).
9. **Missing error precedence** â overlapping 401/403/400/429 mappings. Resolved: deterministic 4-step precedence order (Â§12.2) and `retry_after_ms` rule (Â§12.3).
10. **Incomplete concurrency protocol** â no atomic replace, corruption handling, or claim semantics. Resolved (Â§7).
11. **Missing specification sections** â package layout, manifest validation, security/redaction, timeout units, runbook, acceptance checklist, changelog. Added as Â§5, Â§10.3, Â§13.4, Â§14, Â§16, Â§17, Â§19.

---

*End of Specification â UNIVERSAL PROVIDER SPECIFICATION & ARCHITECTURAL BLUEPRINT v1.1*
```

---

**ÙØ§Ø­Ø¸Ø§Øª Ø³Ø±ÙØ¹Ø©:**
-ÙÙ Ø¬Ø§ÙØ² ÙÙÙØµÙ ÙÙ ÙÙ `docs/UNIVERSAL_PROVIDER_SPEC_AND_BLUEPRINT.md` â ÙØ Ø¨ÙØ§ PlaceholdersØ ÙÙÙ Ø¬Ø¯ÙÙ ÙØ¬Ø¹ÙØª.
- Ø£Ø®ØªØ±Ø¹ Ø­ÙÙÙØ§Ù ÙÙ `RequestEnvelope` / `ResponseEnvelope` / `FacadeResult` â Ø£ÙØ´ÙØ± Ø¥ÙÙÙØ§ Ø¨Ø§ÙØ² ÙÙØ· ÙØ£ÙÙØ§ÙÙØ© ÙÙ `gateway/contracts.py`Ø ÙÙØ°Ø§ ÙÙ Ø§ÙÙØ«ÙÙØ© Ø§ÙØ§ÙØ­Ø±Ø§Ù Ø¹Ù Ø§ÙÙÙØ¯ Ø§ÙÙØ¹ÙÙ.
- Ø§ÙÙØ±Ø§Ø±Ø§Øª Ø§ÙØ¬Ø¯ÙØ¯Ø© Ø§ÙØµØ±ÙØ­Ø© (ÙØ§Ø¨ÙØ© ÙÙØ§Ø¬Ø¹Ø©Ù): `MAX_ACCOUNT_ATTEMPTS = 3`Ø ÙÙÙ 15sØ `retry_after_ms` Ø§ÙØ§ÙØªØ±Ø§Ø¶Ù 1000msØ ØµÙØºØ© ØªØ­ÙÙÙ `timeout_ms â seconds