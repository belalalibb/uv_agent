# ðï¸ UNIVERSAL PROVIDER SPECIFICATION & ARCHITECTURAL BLUEPRINT (v2.0)
## Master Standard for Autonomous Gateway Provider Onboarding & 10x Acceleration
**Authors & Authority:** Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)
**System:** AI Gateway Service (`__gateway-service/`)
**Target Audience:** Any AI Coding Agent (Flash / Claude Opus / Sonnet / Codex) & Human Engineers
**Compliance Standard:** Bolla Constitution v1.2 & ADR-0008 (Gateway Wire Contract v1)
**Target SLA:** **"Raw HAR In â¡ï¸ Tested Production Provider Out in < 60 Minutes"** (engineering target, not a hard runtime guarantee)
**Status:** Canonical Master Standard (Version 2.0 â Supersedes v1.0 while preserving backward compatibility)

> **Normative language:** The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are to be interpreted as described in RFC 2119. Any deviation from a MUST requires a written ADR exception approved by the Lead Architect.

---

## ð 1. The Core Philosophy & The 60-Minute SLA

This document establishes the definitive **Universal Engineering Blueprint** for onboarding ANY AI Provider (Syntx, NoteGPT, UseAI, Groq, Kimi, Genspark, etc.) into the AI Gateway Service.

> ### â¡ The Golden Operational Law:
> The engineer or AI agent receives **ONLY the `.har` file** (or raw network traffic captures) provided by Eng. Zizo, plus this specification.
> Everything else â the internal HTTP core, session persistence, account lifecycle management, metadata extraction, facade adapter, capability guards, audio transcription, stress suites, and hermetic tests â MUST be constructed **strictly according to this v2.0 specification**, without asking redundant questions, without trial-and-error sprawl, and without modifying Gateway core contracts.

### 1.1 The Three Non-Negotiable Invariants
1. **Contract Isolation:** No provider-internal exception, token, header, or stack trace ever crosses the Layer 2 (adapter) boundary. All output conforms to ADR-0008.
2. **Failover Over Blocking:** A depleted or dead account is never retried blindly. The pool self-heals; the caller experiences at most a bounded, retryable failure â never an infinite loop.
3. **No Fabrication:** When the HAR does not prove a behavior (registration flow, transcription endpoint, quota semantics), the implementation MUST declare it unsupported rather than simulate it. Simulated success is a critical defect.

### 1.2 Authorization Constraint
Automated account creation via disposable email flows is **provider-specific and optional**, not a universal obligation. It MUST be performed only on providers where Eng. Zizo has explicitly authorized automated signup. Where authorization is absent, `register()` MUST return the typed error `REGISTRATION_UNAVAILABLE` (see Â§7.2) and the pool MUST be seeded manually.

---

## ðï¸ 2. The Canonical Rule of Exactly 4 Clean Python Files (Zero Sprawl Standard)

A major post-mortem finding from v1.0 implementations is **Agent Sprawl** (generating 10+ fragmented scripts, duplicate account pools, and non-standard CLI wrappers).
In Blueprint v2.0, every provider inside `__gateway-service/providers/<provider_slug>/` is strictly restricted to **EXACTLY 4 Python source files**:

```
__gateway-service/providers/<provider_slug>/
âââ __init__.py           # Exports DEFINITION and HANDLERS only â no logic
âââ definition.py         # Declares display name, closed capabilities, operations, and declared models
âââ _core.py              # Layer 1: Autonomous engine implementing the 4 Universal Core Functions
âââ adapter.py            # Layer 2: Facade Adapter mapping ProviderContext <-> FacadeResult (12 errors)
```

**"Exactly 4" means exactly 4 `.py` files.** Any additional Python file (utils, helpers, config, cli) is a **Zero Sprawl violation** and fails CI.

### 2.1 Permitted Local Asset Files (non-Python, data only)
| File | Purpose | Committed to VCS? |
|---|---|---|
| `models_metadata.json` | Raw full-fidelity upstream capability matrix (secret-redacted) | Yes |
| `accounts_<provider_slug>.json` | Persistent accounts pool (runtime state, managed under FileLock, schema Â§8) | **No** â runtime state, gitignored, resolved via the compatibility resolver at `PROVIDER_STATE_DIR` (default: legacy in-folder path for backward compatibility) |

### 2.2 `__init__.py` Contract
```python
from .definition import DEFINITION
from .adapter import HANDLERS

__all__ = ["DEFINITION", "HANDLERS"]
```
Nothing else may be exported. The Gateway loader imports ONLY these two symbols.

---

## ð§© 3. Layer 1: The Universal 4-Function Provider Core (`_core.py`)

Every provider core MUST be autonomous, resilient, and self-healing. It exposes **four universal functions** with these exact signatures (backward-compatible with v1.0):

### Function 1: `register(timeout: int = 120) -> dict`
- **Purpose:** Provisions a fresh, fully-verified account using disposable emails or automated signup flows â **only for providers where automated signup is authorized (Â§1.2)**.
- **Session Persistence Standard (MUST):**
  - Use a persistent HTTP session with browser TLS fingerprint impersonation. Default:
    ```python
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate=PROVIDER_TLS_PROFILE)  # default: "chrome124"
    ```
  - The impersonation profile MUST be a per-provider constant, not a global hardcode.
  - Stateless requests lose session cookies and CSRF tokens and cause upstream IP bans â this is a MUST, not a preference.
- **Livewire & Dynamic DOM Morphing Rule (when a Livewire temp-mail provider is used):**
  OTP extraction MUST inspect **both**:
  1. Direct JSON data arrays: `res.json()["serverMemo"]["data"]["messages"]`
  2. Rendered Livewire HTML morphing: `res.json()["effects"]["html"]` via regex `r"\b(\d{6})\b"`
  - OTP polling MUST be bounded (deadline = `timeout`, poll interval â¤ 3s) and MUST raise a typed timeout error â never poll forever.
- **Mandatory Best-Effort Cleanup (`deleteEmail`):**
  ```python
  try:
      # registration flow
  finally:
      # 1) First: close the mailbox/HTTP client (always succeeds or logs)
      # 2) Then: best-effort purge of the mailbox THIS code created (delete_email)
      # Cleanup failures are logged and MUST NOT mask or replace the primary exception.
      client.delete_email()
      client.close()
  ```
  Cleanup MUST be restricted to mailboxes this code created, and MUST never convert a failed registration into a success.
- **Return Contract (v1.0 keys preserved; new keys additive):**
  ```python
  {
      "email": str,
      "token": str,             # secret â never logged
      "chat_uuid": str | None,  # provider-specific session id; None when N/A
      "status": "active",
      "created_at": str,        # UTC ISO-8601
      "account_id": str         # v2.0: opaque internal id (token hash) for pool addressing
  }
  ```
- **Unsupported registration:** raise/return `REGISTRATION_UNAVAILABLE` (Â§7.2). Do not fake an account.

---

### Function 2: `refresh(account: dict) -> bool`
- **Purpose:** Tests token validity and available credits without crashing the caller.
- **Output:** Returns `True` if operational; `False` **only** for permanently invalid or definitively depleted accounts (triggering atomic eviction, Â§9).
- **Precision Rule (v2.0 hardening):** A `False` MUST mean "evict this account." Transient conditions (network blip, upstream 5xx, ambiguous response) MUST NOT return `False`; they either raise a retryable typed error or return `True` with a `degraded` note in the internal status. Internally the core SHOULD use a typed status enum (`ACTIVE | DEPLETED | REVOKED | TRANSIENT`) and map it to the legacy boolean at the boundary.

---

### Function 3: `ask(model: str, prompt: str, image_b64: str = None, image_format: str = None, timeout: int = 120) -> dict`
- **Purpose:** Primary inference engine for text generation and multi-modal vision.
- **The 4 Non-Negotiable Pillars of `ask()` in v2.0:**

  **1. Non-Vision Protection Gate (local, before any network I/O):**
  Intercept text-only models in < 10 ms with zero network traffic (see Â§5) and raise the typed `UNSUPPORTED_CAPABILITY` error.

  **2. Capability-Gated Feature Injection (v2.0 correction of v1.0):**
  Feature flags are injected **only when the provider's capability map (from `models_metadata.json` / `definition.py`) declares support**. Injection is default-on per supported feature, but never force-injects unsupported fields (upstream would 400):
  ```python
  payload: dict = {
      "chat_uuid": chat_uuid,
      "text": prompt,
      "model": model,
  }
  if caps.get("reasoning"):
      payload["thinking"] = True          # Deep reasoning mode
  if caps.get("planning"):
      payload["plan"] = True              # Planning mode
  if caps.get("web_search"):
      payload["deep_research"] = True     # Deep web search
  if caps.get("tool_use"):
      payload["tools"] = ["search", "code", "shell", "files", "charts"]
  ```
  `caps` is the provider capability map declared in `definition.py`. (Note: this corrects the v1.0 example, which force-injected all fields unconditionally and contained an indentation defect.)

  **3. Threshold-Based Background Replenishment (`trigger_background_refill`):**
  Do NOT wait until the pool is empty (20s queue during traffic spikes) â and do NOT spawn registration on *every* request either (v1.0 defect: signup storms, thread explosion, rate-limit amplification). Replenishment is threshold-triggered and single-flight:
  ```python
  _REFILL_LOCK = threading.Lock()          # single-flight guard

  def trigger_background_refill(count: int = 5) -> None:
      """Idempotent, bounded, non-blocking. Safe to call on every ask()."""
      if not AUTOMATED_SIGNUP_AUTHORIZED:  # Â§1.2
          return
      with _REFILL_LOCK:
          pool = load_pool_snapshot()                  # cheap read
          if pool.active_count() > POOL_LOW_WATER_MARK:  # e.g. 3
              return                                   # threshold not hit
          if _refill_in_flight:                        # another worker running
              return
          _refill_in_flight = True
      threading.Thread(
          target=_background_refill_worker,
          args=(min(count, POOL_MAX_SIZE - pool.active_count()),),
          daemon=True,
      ).start()
  ```
  The refill worker MUST: respect `POOL_MAX_SIZE`, be idempotent (dedupe by `account_id`), record success/failure metrics, and never affect the outcome of the calling `ask()`.

  **4. Classified Quota Eviction & Fast Failover:**
  - When upstream returns `429`, **classify before acting** (Â§7, Â§9):
    - `QUOTA_EXHAUSTED` (e.g. `429 rateLimitExceeded` with `window_violated: "7d"`) â atomically evict via `evict_account(token)` (FileLock + temp-file + `os.replace`, Â§8) and immediately retry with the next active account. No pause on the dead account.
    - `RATE_LIMITED` (transient) â bounded backoff on the SAME account; never evict.
  - Failover is best-effort: if the pool is empty, return `ACCOUNT_POOL_EXHAUSTED` (retryable, Â§7). **Zero-downtime is an objective, not a guarantee.** Never loop indefinitely.

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
- **Purpose:** High-fidelity speech-to-text audio transcription (for providers declaring `audio_input: True`).
- **Implementation Pattern:**
  - Validates format, MIME type, and size against provider limits **locally before network I/O**; unsupported formats â `INVALID_REQUEST`.
  - Dispatches multipart form data to the provider's native transcription endpoint (e.g. `POST /api/v1/audio/transcribe`).
  - Passes audio bytes with the correct MIME type (`audio/webm;codecs=opus`, `audio/mp3`, `audio/wav`).
  - Authenticates using the provider's declared auth mode (Â§6.3) â Bearer token from the active pool account where applicable.
  - Providers without a transcription endpoint MUST declare `audio_input: False`; the adapter then rejects with `UNSUPPORTED_CAPABILITY` before network I/O.
- **Return Contract (v2.0 correction: the transcription model is the provider's actual model, never a universal hardcode):**
  ```python
  {
      "text": str,
      "language": str | None,
      "model": str | None   # actual upstream model, e.g. "whisper-1" where that is the true model name
  }
  ```

---

## ð§  4. The Dual Capabilities Strategy & Metadata Preservation

Upstream providers expose rich, granular features that must never be lost.

### A. Raw Metadata Preservation (`models_metadata.json`)
Store the exact, untruncated JSON structure returned by the provider's `/models` or `/settings` endpoints, with these hardening rules (v2.0):
- **Secret & PII scan before commit:** no tokens, cookies, keys, emails, or internal URLs with credentials. Fails CI otherwise.
- Stamp `{"_captured_at": "<UTC ISO-8601>", "_source": "<endpoint>", "_schema_version": 1}` at the top level. Never mutate the captured payload itself.

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

- Projection is **explicit per key** â upstream booleans are never copied blindly into gateway semantics; each mapping above is the normative rule, and unmapped upstream features stay in raw metadata only.
- The projected set MUST be a subset of the 14 keys; any foreign key fails CI.

---

## ð¡ï¸ 5. Non-Vision Model Protection Gate (Zero-Leak Pattern)

To prevent upstream crashes and unhandled 400 errors:
- Implement **one pure shared predicate** `is_vision_model(model) -> bool`, derived from `definition.py` declared capabilities / `models_metadata.json` â **never from model-name string heuristics** (hardcoded names like `grok-4.6` or `deepseek-r1` age badly and are forbidden as the source of truth).
- Call the predicate at **both** boundaries (`_core.py` before network, `adapter.py` before delegation) for defense in depth.
- If an image is passed to a text-only model, reject immediately with the typed error:
  ```python
  ProviderError(category=ErrorCategory.UNSUPPORTED_CAPABILITY,
                message=f"Model {model!r} does not support vision/image inputs")
  ```
- **Benchmark standard (single, normative):** MUST reject in **< 10 ms** with zero network traffic. (This supersedes the v1.0 `< 5 ms` wording; CI enforces < 10 ms.)
- Unknown/undeclared models: policy is `deny` for vision unless the provider metadata declares `vision_input: True` for that model.

---

## ð 6. Layer 2: Facade Adapter Contract (`adapter.py`)

The adapter is the **only** boundary between Gateway contracts and provider internals. It MUST:
1. Validate the request and declared capabilities locally (including Â§5).
2. Translate `ProviderContext` into provider-specific core calls.
3. Normalize core results into `FacadeResult`.
4. Convert **every** exception into a canonical `ProviderError` (Â§7). No internal exception, token, or stack trace crosses this boundary â ever.
5. Preserve v1.0 public handler names and legacy response fields; new fields are additive only.

### 6.1 Canonical Error Envelope (wire format per ADR-0008)
```json
{
  "error": {
    "category": "unsupported_capability",
    "message": "Model 'deepseek-r1' does not support vision/image inputs",
    "retryable": false,
    "request_id": "opaque-request-id"
  }
}
```
- `message` is safe-for-public: no tokens, no raw upstream bodies, no internal hostnames.
- Wire field names and HTTP status codes are governed by **ADR-0008**; where this document and ADR-0008 disagree, ADR-0008 wins and this document MUST be amended.

### 6.2 The 12 Canonical Error Categories (Strict Mapping)

| # | Category | Typical HTTP | Retryable | Meaning |
|---|---|---|---|---|
| 1 | `INVALID_REQUEST` | 400 | No | Malformed input, invalid media/base64, unsupported audio format |
| 2 | `UNSUPPORTED_CAPABILITY` | 400 | No | Requested capability not declared by model/provider (e.g. vision on text-only) |
| 3 | `AUTHENTICATION_FAILED` | 401 | No â rotate account | Token/credential rejected upstream |
| 4 | `AUTHORIZATION_FAILED` | 403 | No | Valid credential, forbidden operation |
| 5 | `RATE_LIMITED` | 429 | Yes â bounded backoff | Transient throttling; same account stays in pool |
| 6 | `QUOTA_EXHAUSTED` | 429 | No â for that account | Confirmed quota depletion (e.g. 7-day window violated) â atomic eviction |
| 7 | `ACCOUNT_POOL_EXHAUSTED` | 503 | Yes | No active account available after failover |
| 8 | `UPSTREAM_TIMEOUT` | 504 | Usually yes | Upstream deadline exceeded |
| 9 | `UPSTREAM_UNAVAILABLE` | 502/503 | Yes | Upstream down / 5xx / connection refused |
| 10 | `UPSTREAM_PROTOCOL_ERROR` | 502 | Usually no | Unparseable/malformed upstream response (contract drift) |
| 11 | `CONTENT_FILTERED` | 422* | No | Upstream safety filter refused the content |
| 12 | `INTERNAL_ERROR` | 500 | No | Unexpected local failure (bug) â redacted |

\* or the ADR-0008-specified status. `finish_reason: "filter"` in a successful inference response is a **normal result**, not an error; `CONTENT_FILTERED` is only for outright refusal of the request.

Every `ProviderError` carries: stable enum name, string value, `retryable` flag, and safe public message. v1.0 aliases (e.g. raising `UpstreamFailure("unsupported_capability")` in Layer 1) MUST be mapped centrally in the adapter to the typed category â Layer 1 may keep legacy exception shims, but Layer 2 output is always the typed taxonomy.

### 6.3 Provider Authentication Modes
Each provider declares exactly one auth mode in `definition.py`: `bearer_token | cookie_session | api_key_header | custom_headers`. Nothing else may leak into the adapter.

---

## ðï¸ 7. (Reserve) â *numbering continued in Â§8âÂ§13 below*

---

## ðï¸ 8. Account Pool: Schema, FileLock & Atomic Persistence

`accounts_<provider_slug>.json` is versioned runtime state (never committed), written only under FileLock:

```json
{
  "schema_version": 1,
  "provider": "<provider_slug>",
  "updated_at": "2025-01-01T00:00:00Z",
  "accounts": [
    {
      "account_id": "opaque-id",           // token hash â never the raw token
      "email": "account@example.invalid",
      "token": "secret",                   // never logged
      "chat_uuid": null,
      "status": "active",                  // active | depleted | revoked | cooldown
      "created_at": "2025-01-01T00:00:00Z",
      "last_checked_at": null,
      "last_used_at": null,
      "failure_count": 0,
      "cooldown_until": null,
      "quota": { "window": "7d", "remaining": null, "reset_at": null }
    }
  ]
}
```

**Persistence rules (MUST):**
1. Every read-modify-write is performed under `FileLock`.
2. Write to a temp file â `flush()` â `os.fsync()` â `os.replace()` (atomic on POSIX & Windows).
3. Crash-safety: a reader encountering a corrupt/partial file MUST fail safe (keep last-known-good snapshot in memory, attempt recovery from `<file>.bak`), never silently reset the pool.
4. Concurrent workers MUST use account **leases** (in-process coordination) to prevent double-use and duplicate eviction.
5. v1.0 legacy list-format files are migrated to `schema_version: 1` on first write (backward compatibility).
6. File permissions restricted (no world/group read); raw tokens never logged â diagnostics use `account_id`.

---

## ð 9. Concurrency, Retry & Failover Policy

| Concern | Normative Rule |
|---|---|
| Deadlines | Per-request deadline propagation; no unbounded waits anywhere |
| Retries | Bounded (default â¤ 2), exponential backoff with jitter; **never** retry `INVALID_REQUEST`, `UNSUPPORTED_CAPABILITY`, `AUTHENTICATION_FAILED`, `AUTHORIZATION_FAILED`, `CONTENT_FILTERED` |
| Eviction | Only on `QUOTA_EXHAUSTED` (confirmed) or `AUTHENTICATION_FAILED` (confirmed revoked). Optional quarantine (`failure_count >= 3` â `cooldown`) before hard eviction for ambiguous signals |
| Refill | Threshold-triggered (Â§3, Pillar 3), single-flight, bounded by `POOL_MAX_SIZE`, fully idempotent |
| Failover | Immediate switch to next active account on confirmed eviction; `ACCOUNT_POOL_EXHAUSTED` (retryable) when pool is empty; no infinite loops |
| Circuit breaking | N consecutive `UPSTREAM_UNAVAILABLE`/`UPSTREAM_TIMEOUT` (default 5) â open circuit for cooldown window; half-open probes after |
| Observability | Request IDs, latency/refill/eviction/circuit metrics, structured logs with all secrets redacted |

---

## ð 10. Security & Privacy Model

- **HAR files:** treated as secrets. Redact tokens/cookies/PII before use in fixtures or docs. HAR-derived fixtures committed to the repo MUST be sanitized (CI check).
- **Credentials:** never in logs, metrics, error messages, or committed files. `accounts_*.json` gitignored with restrictive permissions.
- **Metadata:** secret-scanned before commit (Â§4A).
- **Cleanup:** mailbox purge is best-effort and scoped to self-created resources only (Â§3, Function 1).
- **Automated signup:** only where explicitly authorized (Â§1.2); signups and real-quota consumption NEVER run in normal CI.

---

## ð§ª 11. Testing & Verification (CI-Enforced)

A provider is mergeable only when ALL of the following pass:
1. **Layout check:** exactly 4 `.py` files; `__init__.py` exports only `DEFINITION` and `HANDLERS`.
2. **Capability tests:** projection is a subset of the 14 keys; each mapping follows Â§4B.
3. **Gate benchmark:** non-vision rejection < 10 ms, zero network calls (assert via socket guard).
4. **Contract tests:** `register`, `refresh`, `ask`, `transcribe_audio` â happy path + typed error paths.
5. **Hermetic tests:** sanitized HAR fixtures + mocked upstream: malformed JSON, Livewire HTML morphing, missing OTP, timeouts, retry paths, 429 classification (`RATE_LIMITED` vs `QUOTA_EXHAUSTED`), protocol drift.
6. **Concurrency tests:** refill single-flight, leases, simultaneous FileLock writes, crash-recovery of atomic persistence.
7. **Media tests:** MIME/format/size validation and `INVALID_REQUEST` mapping.
8. **Boundary tests:** prove no raw exception, token, or upstream body crosses `adapter.py`.
9. **Live smoke (optional, manual, authorized):** gated behind explicit approval, never in normal CI.

---

## â±ï¸ 12. The 60-Minute HAR â Production Runbook

| Window | Activity |
|---|---|
| **0â5 min** | Confirm authorization; redact HAR secrets; identify provider & scope |
| **5â15 min** | Extract hosts, auth mode (Â§6.3), endpoints, request/response shapes, model list, capability signals |
| **15â25 min** | Scaffold the 4 Python files; write `definition.py` (capabilities + models) and `models_metadata.json` |
| **25â40 min** | Implement `_core.py`: session/TLS profile, request translation, response parsing, account lifecycle (only what the HAR proves) |
| **40â48 min** | Implement `adapter.py`: `FacadeResult` normalization, typed errors (Â§6.2), local gates (Â§5) |
| **48â55 min** | Run the full suite (Â§11); fix only provider-layer defects â never core contracts |
| **55â60 min** | Authorized smoke test; verify log/metric redaction; document unsupported operations; prepare rollback |

**Stop-the-line rule:** if the HAR does not establish a behavior (registration, transcription, vision, quota semantics), the runbook stops and declares it unsupported (Â§1.2, Invariant 3). Fabrication is worse than incompleteness.

---

##  13. Definition of Done

A provider is production-ready only when:
- [ ] Exactly 4 Python files exist; zero sprawl; `__init__.py` exports only `DEFINITION` + `HANDLERS`.
- [ ] v1.0 public signatures and legacy response fields preserved; additions are additive only.
- [ ] Capabilities explicitly declared (Â§4) and locally enforced at both boundaries.
- [ ] Non-vision gate: < 10 ms, zero network I/O, metadata-derived (no name heuristics).
- [ ] All 4 core functions have deterministic timeout and typed-error behavior.
- [ ] Feature injection is capability-gated (Â§3, Pillar 2) â no force-injected unsupported fields.
- [ ] Pool persistence: versioned schema, FileLock, atomic replace, crash-safe, secret-safe (Â§8).
- [ ] Refill is threshold-based, single-flight, bounded (Â§3, Pillar 3).
- [ ] Quota eviction is classified, atomic, and concurrency-safe (Â§9).
- [ ] All errors map to the 12 categories (Â§6.2); wire format conforms to ADR-0008.
- [ ] Full Â§11 test suite passes in CI.
- [ ] Metadata preserved, secret-redacted, and stamped (Â§4A).
- [ ] Observability + rollback instructions documented.
- [ ] Any unsupported behavior is explicitly declared â never simulated.
- [ ] Human reviewer approval for any authorized live testing.

---

## ð Appendix A: v2.0 Changelog (Supersedes v1.0)

| Change | Rationale |
|---|---|
| Unified gate benchmark to `< 10 ms` | v1.0 contradicted itself (5 ms vs 10 ms) |
| Refill is threshold + single-flight | v1.0 spawned registration on every `ask()` â signup storms |
| 429 classification before eviction | v1.0 evicted on any 429, including transient throttling |
| Capability-gated feature injection | v1.0 force-injected `thinking/plan/deep_research` universally |
| `transcribe_audio` returns the actual model | v1.0 hardcoded `"whisper-1"` universally |
| "Zero downtime" â best-effort failover objective | Empty-pool case now returns retryable `ACCOUNT_POOL_EXHAUSTED` |
| Full 12-category error table + typed `ProviderError` | v1.0 Section 6 was truncated/unspecified |
| Versioned account pool schema + atomic persistence | v1.0 had no schema or crash-safety rules |
| Security & testing sections added | No secret-handling or CI policy existed in v1.0 |
| `register()` made conditional on authorization | Legal/operational risk of universal automated signup |

**Backward compatibility:** all v1.0 public function signatures, `__init__.py` exports, legacy file paths (via the state resolver), and legacy exception shims are preserved. Nothing in `gateway/contracts.py` changes.