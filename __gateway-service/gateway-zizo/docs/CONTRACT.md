# Provider Gateway â Canonical Contract (v1)

| | |
|---|---|
| **Authority** | ADR-0008 (ACCEPTED 2026-08-29) |
| **Contract version** | v1 (closed; extensions require a new ADR) |
| **Source of truth** | `gateway/contracts.py` |
| **Drift control** | `tests/test_contract_parity.py` |
| **Normative language** | MUST / MUST NOT / MAY as in RFC 2119 |

**Source-of-truth rule:** `gateway/contracts.py` is the authoritative code
contract; this document is its human-readable mirror. When they disagree,
**the code wins and this file MUST be fixed**. Drift is blocked by
`tests/test_contract_parity.py`.

---

## 1. TERMINOLOGY

| Term | Definition |
|---|---|
| **Platform** | The calling system that holds tenants, billing (reserveâsettle), and failover policy. |
| **Platform adapter** | The platform-side client that speaks this contract to the gateway. |
| **Gateway** | This service. Routes, authenticates, enforces the canonical contract. |
| **Provider package** | The Layer-1 implementation of one provider (internal, opaque). |
| **Provider facade** | The mandatory Layer-2 translator implementing the canonical contract. |
| **Provider definition** | The load-time declaration of a provider: credential mode, declared operations, models, capabilities. |
| **Route token** | Opaque per-provider credential carried in `X-Route-Token`. |
| **Upstream** | The external service a provider wraps. |
| **Upstream identity** | Provider/account/host/credential identity. **Never exposed through this contract.** Declared model names are contract data, NOT upstream identity. |
| **Gateway secret** | The shared secret in `X-Gateway-Secret` (+ version header) authenticating the platform. |

---

## 2. THE THREE-LAYER PROVIDER MODEL

```
          PROVIDER PACKAGE
   ââââââââââââââââââââââââââââââââ
   â any file count, any shape    â  â Layer 1 (FREE)
   â auth/session/accounts/enginesâ
   â SDK/recovery/orchestration   â
   ââââââââââââââââ¬ââââââââââââââââ
            Provider Facade          â Layer 2 (MANDATORY: the translator)
                  â
                  â¼
        Canonical Gateway Contract   â Layer 3 (FIXED)
                  â
                  â¼
               Platform
```

### 2.1 Internal implementation freedom (Layer 1)

A provider implementation is an **opaque internal subsystem**. This contract
imposes NONE of the following:

- the provider's internal file structure (one file or thirty â equal),
- the number of modules / classes / functions,
- the internal orchestration strategy,
- SDK choice,
- authentication mechanism (OAuth / session / cookies / anything),
- account management, pools, or internal rotation,
- caching or any internal state,
- internal call chaining â one gateway request may internally produce N
  upstream calls + internal fallback + renormalization, all invisible to
  the platform.

**The only binding boundary is the final Facade (Layer 2)**, which translates
whatever happened internally into the canonical contract.

### 2.2 One request â one invocation â one canonical response

- One accepted, authenticated, routed `POST /v1/execute` invokes the facade
  **exactly once** and produces **exactly one** canonical response.
- A free internal workflow (possibly auth + account selection + several
  upstream calls + internal fallback + normalization) is permitted **inside
  that single invocation**, MUST honor the request deadline (Â§4), and is
  invisible to the platform: the platform never sees the internal call count.

### 2.3 The Facade (Layer 2 â mandatory)

- Receives a `ProviderContext` (operation / model / request_id / tenant_id /
  credential_mode / credential_value / payload / timeout_ms) â and never sees
  the slug, the route_token, or the calling tenant identity.
- Returns **either** a success matching the canonical output schema **or** an
  error mapped to one of the 12 categories. **No third shape exists.**
- A provider never invents its own response format for the gateway to
  "figure out" â the facade translates BEFORE anything crosses a boundary.

### 2.4 Layer 3 â fixed for all providers

Request Envelope Â· Response Envelope Â· 12-category error taxonomy Â· Usage
shape Â· Security rules (`X-Gateway-Secret`[+`-Version`], `X-Route-Token`) Â·
HTTP status map. Providers conform; they never extend it.

---

## 3. EXECUTION SEMANTICS

### 3.1 Zero gateway-level retries (billing integrity, ADR-0008)

- The gateway performs **NO** execution retry, replay, failover, or
  re-dispatch â ever. Any provider-internal "retry" is confined to the
  single facade invocation described in Â§2.2 and is subject to its deadline.
- **Sole exception (not a gateway retry):** on `401 auth_expired` the
  *platform adapter* re-reads its secret store and issues **one new request**
  with a fresh secret version. This is self-healing on the caller side; the
  gateway itself never retried anything.

### 3.2 Deadline and cancellation

- `timeout_ms` is the **absolute end-to-end deadline** for the facade
  invocation, measured with a monotonic clock from request acceptance.
- Every internal upstream call MUST receive only the **remaining** budget;
  work is cancelled at expiry and the result is the canonical `timeout`
  error (execution failure, HTTP 200).

---

## 4. HTTP SURFACE (v1)

| Method + Path | Auth | Route token | Purpose |
|---|---|---|---|
| `POST /v1/execute` | secret+version | yes | Execute any declared operation (`operation` in the envelope â single source of truth; NO per-operation routes) |
| `GET /v1/describe` | secret+version | yes | Manifest projection for the provider addressed by `X-Route-Token` |
| `GET /v1/models` | secret+version | yes | Lightweight projection of the declared model list |
| `GET /v1/health` | secret+version | yes | Provider health (`UNKNOWN` is a legal answer) |
| `GET /healthz` | none | no | Process liveness only â no provider info, no secrets |

Transport rules:

- Request and response bodies are `application/json`, UTF-8. A `POST` with a
  missing/wrong `Content-Type` or non-JSON body â `400`.
- Unknown paths and unsupported methods â `404` with the uniform
  anti-enumeration body (Â§6.2). They never reveal provider or route state.

---

## 5. SECURITY

### 5.1 Gateway secret

- `X-Gateway-Secret: <value>` + `X-Gateway-Secret-Version: <int>` on every
  authed call.
- Dual-accept rotation window (current + previous version; operational
  default 10 min).
- Wrong secret â `401 invalid_credential` (retryable: false).
- Stale version â `401 auth_expired` (retryable: true) â triggers the
  platform-adapter self-heal of Â§3.1.

### 5.2 Route token

- `X-Route-Token: <opaque>` on **all** provider-addressed surfaces
  **including GETs** â the token NEVER appears in a URL path or query string
  (ADR-0008 OPEN-3), and never in logs, traces, metrics labels, or upstream
  requests.
- A **missing** token is treated exactly like an **unknown** token.
- Unknown / revoked / disabled token â uniform `404` body (anti-enumeration
  â the three causes are indistinguishable):

```json
{"error": {"category": "provider_unavailable", "retryable": false, "message": "unknown route"}}
```

### 5.3 Verification precedence (normative order)

1. **Gateway authentication** â `401` on failure.
2. **Transport validation** (JSON parse, `Content-Type`) â `400` on failure.
3. **Route resolution** â uniform `404` on missing/unknown/revoked/disabled.
4. **Envelope semantic validation + execution** â HTTP 200 envelope.

Syntax errors are answered *before* route resolution so a malformed request
can never act as a token-validity oracle.

### 5.4 Never logged, never returned anywhere

Credential values Â· route_token Â· slug Â· upstream identity (account/host/
credential) Â· exception class names. `request_id` and `tenant_id` are
correlation/audit data and MAY appear in platform-side logs.

---

## 6. RESPONSE SHAPES AND HTTP STATUS MAP

There are exactly **two** response families:

- **Execution envelope** â HTTP 200 from `POST /v1/execute` only (Â§8).
- **Transport error body** `{"error": {...}}` â gateway-generated for
  400/401/404/500; never produced by a facade.

| HTTP | Meaning | Body |
|---|---|---|
| 200 | Envelope delivered â success **and** execution failures (read `error.category`) | Execution envelope |
| 400 | Malformed transport/envelope â `bad_request` | Transport error body |
| 401 | Gateway auth failure (wrong secret = `invalid_credential`; stale version = `auth_expired`, retryable) | Transport error body |
| 404 | Unknown/revoked/disabled route token â uniform "unknown route" | Transport error body (fixed, Â§5.2) |
| 500 | Gateway internal fault â `retryable_server_error`, sanitized `provider_code` | Transport error body |

Example â `400`:

```json
{"error": {"category": "bad_request", "retryable": false, "message": "malformed envelope"}}
```

Example â `401` (stale version; retryable):

```json
{"error": {"category": "auth_expired", "retryable": true, "message": "secret version no longer accepted"}}
```

---

## 7. REQUEST ENVELOPE (`POST /v1/execute`)

| Field | Type | Required | Semantics |
|---|---|---|---|
| `operation` | str (closed set of 8) | yes | The single source of truth for what runs |
| `model` | str | yes | Exact upstream model name â the gateway NEVER substitutes, aliases, or falls back |
| `request_id` | str (1â128 chars) | yes | Platform correlation id; passed upstream where supported; **not** an idempotency key in v1 (no dedup) |
| `tenant_id` | str | yes | Evidence/audit only â zero gateway decisions on it |
| `credential` | object | yes | `{mode: "user_key"\|"platform", value?}` â mode MUST match the DEFINITION |
| `payload` | object | yes | Operation-specific (schemas below) |
| `timeout_ms` | int 1..600000 | yes | End-to-end deadline toward upstream (Â§3.2) |

Credential validation (execution-level â HTTP 200 `bad_request` on breach):

- `mode: "user_key"` â `value` MUST be a non-empty string.
- `mode: "platform"` â `value` MUST be absent or null (resolved internally).
- `credential.mode` MUST equal the DEFINITION's `credential_mode`.

Forbidden by construction: `provider_slug`, `upstream_url`, any internal
identifier. Unknown fields are rejected (`extra="forbid"`), **applied
recursively** to the envelope, the credential object, every operation
payload, and every nested object.

---

## 8. RESPONSE ENVELOPE (HTTP 200)

Success:

```json
{"succeeded": true, "output": {...}, "usage": {"input_tokens": 431, "output_tokens": 208, "units": 1}, "latency_ms": 812, "error": null}
```

Execution failure (HTTP 200):

```json
{"succeeded": false, "output": null, "usage": null, "latency_ms": 240,
 "error": {"category": "rate_limited", "retryable": true, "retry_after_ms": 2000,
           "message": "upstream call failed", "provider_code": "429"}}
```

Rules:

- `output` â the exact schema of the operation (Â§10); no extra fields.
- `usage` â raw evidence only, never estimates; non-negative integers;
  fields present only when measured. In v1, `usage` is **null** whenever
  `succeeded=false`. Per-operation `units` semantics are defined in Â§10.
- `latency_ms` â gateway-measured wall time from acceptance to response.
- `usage` is raw evidence only â the **platform** bills (reserveâsettle);
  the gateway holds no plans, no ledger, no tenant records.

---

## 9. THE 12 ERROR CATEGORIES (verbatim, platform-led â never extended)

| Category | Retryable (normative) | Use for |
|---|---|---|
| `auth_expired` | yes | valid credential/session that expired (refresh may fix) |
| `invalid_credential` | no | wrong/revoked key or session |
| `rate_limited` | yes | upstream 429/throttle â set `retry_after_ms` |
| `quota_exceeded` | no | hard quota / billing cap |
| `model_unavailable` | no | requested model missing upstream |
| `provider_unavailable` | no | upstream down/unreachable (failover, if any, is a platform-side decision outside this contract) |
| `unsupported_capability` | no | operation/feature not declared/supported |
| `bad_request` | no | caller payload invalid |
| `content_rejected` | no | safety/policy refusal to process |
| `timeout` | yes | upstream exceeded `timeout_ms` |
| `retryable_server_error` | yes | upstream 5xx / transient |
| `non_retryable_error` | no | terminal fallback: every permanent failure that fits no category above |

Error-field constraints:

- `category` â one of exactly the 12 values above.
- `retryable` â determined **solely** by the category (column above); not a
  per-error choice.
- `retry_after_ms` â int 0..600000; permitted only on retryable categories;
  set from upstream hints when available (e.g. upstream `Retry-After`).
- `provider_code` â optional sanitized short token (`^[A-Za-z0-9_.:-]{1,64}$`,
  e.g. `"429"`) â never exception class names, never free text, never URLs,
  hosts, or credential fragments.
- `message` â generic, non-sensitive English, â¤ 512 chars.

Every provider exception, malformed upstream response, and unmapped upstream
status MUST be normalized into one of the 12 categories before crossing the
boundary. Mapping precedence for ambiguous upstreams: expired-but-valid
credential â `auth_expired`; wrong/revoked â `invalid_credential`;
quota/billing cap â `quota_exceeded`; throttle â `rate_limited`;
missing model â `model_unavailable`; policy refusal â `content_rejected`;
deadline expiry â `timeout`; upstream 5xx â `retryable_server_error`.

---

## 10. OPERATIONS

### 10.1 Excluded from v1 (ADR-0008 OPEN-2)

`run_provider_agent`, `upload_asset`, `download_asset` â no implementation,
no API surface. A DEFINITION declaring any of them is **rejected at load
time**. An unsupported operation is never represented by an empty declared
stub â declaration IS the source of eligibility.

A definition MUST declare a non-empty subset of the 8 v1 operations and a
`credential_mode` of `user_key` or `platform`; violations are load-time
rejections.

### 10.2 The 8 v1 operations â payload in, canonical output out

For every operation: input payload fields, the exact successful output shape,
the error form (always a `GatewayError` in one of the 12 categories), and a
full example.

#### 1. `generate_text`

| Payload field | Type | Required |
|---|---|---|
| `messages` | list[{role: str, content: str}], non-empty | yes |
| `temperature` | finite float | no |
| `max_tokens` | positive int | no |

Canonical success output: `{"text": str, "finish_reason": "stop"|"length"|"filter"}`
Â· `units` = 1.

Request:
```json
{"operation": "generate_text", "model": "upstream-model", "request_id": "req_01",
 "tenant_id": "ten_01", "credential": {"mode": "user_key", "value": "<key>"},
 "payload": {"messages": [{"role": "user", "content": "hi"}]}, "timeout_ms": 30000}
```
Success response:
```json
{"succeeded": true, "output": {"text": "Hello!", "finish_reason": "stop"},
 "usage": {"input_tokens": 2, "output_tokens": 3, "units": 1}, "latency_ms": 640, "error": null}
```
Failure (upstream 429):
```json
{"succeeded": false, "output": null, "usage": null, "latency_ms": 200,
 "error": {"category": "rate_limited", "retryable": true, "retry_after_ms": 2000,
           "message": "upstream call failed", "provider_code": "429"}}
```
Other errors: expired session â `auth_expired`; missing model â
`model_unavailable`; policy refusal â `content_rejected`; invalid messages â
`bad_request`.

#### 2. `generate_image`

| Payload field | Type | Required |
|---|---|---|
| `prompt` | str (non-empty) | yes |
| `size` | str `"WIDTHxHEIGHT"` (e.g. `"1024x1024"`) | no |
| `count` | positive int | no (default 1) |

Canonical success output: `{"images": [{"b64": str, "format": str}]}`
Â· `units` = number of images generated.

Request:
```json
{"operation": "generate_image", "model": "upstream-image-model", "request_id": "req_02",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"prompt": "a red cube", "count": 1}, "timeout_ms": 60000}
```
Success response:
```json
{"succeeded": true, "output": {"images": [{"b64": "<base64>", "format": "png"}]},
 "usage": {"units": 1}, "latency_ms": 2100, "error": null}
```
Errors: policy refusal â `content_rejected`; quota cap â `quota_exceeded`;
invalid size/count â `bad_request`.

#### 3. `transcribe_audio`

| Payload field | Type | Required |
|---|---|---|
| `audio_b64` | str (base64) | yes |
| `audio_format` | str (`"mp3"`/`"wav"`/â¦) | yes |
| `language` | str (BCP-47) | no |

Canonical success output: `{"text": str, "language": str|null}` Â· `units` = 1.

Request:
```json
{"operation": "transcribe_audio", "model": "upstream-audio-model", "request_id": "req_03",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"audio_b64": "<base64>", "audio_format": "wav"}, "timeout_ms": 60000}
```
Success response:
```json
{"succeeded": true, "output": {"text": "hello world", "language": "en"},
 "usage": {"units": 1}, "latency_ms": 900, "error": null}
```
Errors: undecodable/oversized audio â `bad_request`.

#### 4. `synthesize_speech`

| Payload field | Type | Required |
|---|---|---|
| `text` | str (non-empty) | yes |
| `voice` | str | no |
| `audio_format` | str | no (default `"mp3"`) |

Canonical success output: `{"audio_b64": str, "audio_format": str}` Â· `units` = 1.

Request:
```json
{"operation": "synthesize_speech", "model": "upstream-tts-model", "request_id": "req_04",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"text": "hello", "voice": "alloy"}, "timeout_ms": 30000}
```
Success response:
```json
{"succeeded": true, "output": {"audio_b64": "<base64>", "audio_format": "mp3"},
 "usage": {"input_tokens": 5, "units": 1}, "latency_ms": 700, "error": null}
```
Errors: unknown voice â `bad_request`; refusal â `content_rejected`.

#### 5. `create_embeddings`

| Payload field | Type | Required |
|---|---|---|
| `inputs` | list[str], non-empty | yes |

Canonical success output: `{"embeddings": [[float,...],...], "dimensions": int}` â
`embeddings[i]` corresponds to `inputs[i]`, order preserved, finite floats.
`units` = `len(inputs)`.

Request:
```json
{"operation": "create_embeddings", "model": "upstream-embedding-model", "request_id": "req_05",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"inputs": ["hello"]}, "timeout_ms": 30000}
```
Success response:
```json
{"succeeded": true, "output": {"embeddings": [[0.01, -0.02, 0.5]], "dimensions": 3},
 "usage": {"input_tokens": 1, "units": 1}, "latency_ms": 90, "error": null}
```
Errors: empty/oversized batch â `bad_request`.

#### 6. `rerank_documents`

| Payload field | Type | Required |
|---|---|---|
| `query` | str (non-empty) | yes |
| `documents` | list[str], non-empty | yes |
| `top_n` | positive int | no (default: all) |

Canonical success output: `{"results": [{"index": int, "relevance_score": float}]}` â
`index` refers to the caller's list; sorted by score descending; â¤ `top_n` rows.
`units` = `len(documents)`.

Request:
```json
{"operation": "rerank_documents", "model": "upstream-rerank-model", "request_id": "req_06",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"query": "cats", "documents": ["dog", "cat"]}, "timeout_ms": 30000}
```
Success response:
```json
{"succeeded": true,
 "output": {"results": [{"index": 1, "relevance_score": 0.97}, {"index": 0, "relevance_score": 0.12}]},
 "usage": {"units": 2}, "latency_ms": 120, "error": null}
```
Errors: empty documents â `bad_request`.

#### 7. `moderate_content`

| Payload field | Type | Required |
|---|---|---|
| `content` | str (non-empty) | yes |

Canonical success output: `{"flagged": bool, "categories": {str: bool}}` â
a "flagged" verdict is a SUCCESS (the moderation ran); `content_rejected` is
only for the upstream REFUSING to process. `units` = 1.

Request:
```json
{"operation": "moderate_content", "model": "upstream-moderation-model", "request_id": "req_07",
 "tenant_id": "ten_01", "credential": {"mode": "platform"},
 "payload": {"content": "some text"}, "timeout_ms": 30000}
```
Success response:
```json
{"succeeded": true, "output": {"flagged": false, "categories": {"hate": false}},
 "usage": {"units": 1}, "latency_ms": 60, "error": null}
```

#### 8. `analyze_vision`

| Payload field | Type | Required |
|---|---|---|
| `image_b64` | str (base64) | yes |
| `image_format` | str (`"png"`/`"jpeg"`/â¦) | yes |
| `instruction` | str (non-empty) | yes |

Canonical success output: `{"text": str}` Â· `units` = 1.

Request:
```json
{"operation": "analyze_vision", "model": "upstream-vision-model", "request_id": "req_08",
 "tenant_id": "ten_01", "credential": {"mode": "user_key", "value": "<key>"},
 "payload": {"image_b64": "<base64>", "image_format": "png",
             "instruction": "what color is the cube?"}, "timeout_ms": 60000}
```
Success response:
```json
{"succeeded": true, "output": {"text": "The cube is red."},
 "usage": {"input_tokens": 850, "output_tokens": 8, "units": 1}, "latency_ms": 1400, "error": null}
```
Errors: undecodable image â `bad_request`; non-vision model â
`unsupported_capability`.

---

## 11. DISCOVERY SHAPES

`GET /v1/describe` (no slug, no upstream identity â declared model names are
permitted contract data, Â§1):

```json
{"display_name": "Example Provider", "credential_mode": "user_key",
 "capabilities": {"chat": true}, "operations": ["generate_text"],
 "models": [{"name": "upstream-model", "context_window": 128000}],
 "definition_version": "1.2.0", "health_supported": true}
```

`GET /v1/models`:

```json
{"models": [{"name": "upstream-model", "context_window": 128000}]}
```

`GET /v1/health`:

```json
{"status": "OK"|"DEGRADED"|"DOWN"|"UNKNOWN", "checked_at": "2026-08-29T12:00:00Z"}
```

- `checked_at` â ISO-8601 UTC or `null`.
- When `health_supported` is false, `/v1/health` always answers
  `{"status": "UNKNOWN", "checked_at": null}`.
- The health check is bounded and never blocks execution; it exposes no
  credentials, route tokens, or upstream account identity.

`GET /healthz` â no auth, no route token; fixed liveness body with zero
provider information:

```json
{"status": "ok"}
```

---

## 12. CREDENTIAL MODES

- `user_key` (BYOK): resolved platform-side, crosses TLS inside the
  envelope, **memory-only** at the gateway â never persisted, never logged,
  never cached, never copied into provider metadata.
- `platform`: resolved internally by the provider facade (keyed by the
  gateway's own means) â never from the request; the platform never learns
  the credential kind; the facade receives a null `credential_value`.
- Envelope `credential.mode` MUST equal the DEFINITION's `credential_mode`
  or the request fails as `bad_request` (200 execution failure, Â§7).

---

## 13. GATEWAY FAULTS AND SANITIZATION

Any gateway-internal fault â facade exception, malformed facade output,
registry failure â is mapped to `500` with
`{"error": {"category": "retryable_server_error", "retryable": true,
"message": "gateway internal fault", "provider_code": "<sanitized token>"}}`.

Sanitization is absolute: no exception class names, no stack traces, no
upstream URLs/hosts, no credentials, no route tokens. The gateway performs
**no retry** on its own faults (Â§3.1).

---

## 14. VERSIONING, CONFORMANCE, AND PARITY

- This document describes contract **v1**. It is closed: new operations,
  categories, fields, or headers require a new ADR and a new contract
  version.
- Change process: change `gateway/contracts.py` first, update this mirror in
  the same change, and land only with `tests/test_contract_parity.py` green.
- The parity test verifies that this document and the code agree on: the
  enums (operations, categories, credential modes, health statuses), the
  envelope schemas, the status map, and the operation registry.

---

## 15. INVARIANTS (ABSOLUTE RULES)

1. One accepted request â exactly one facade invocation â exactly one
   canonical response. **Zero gateway-level retries** (ADR-0008).
2. The facade returns exactly two shapes: canonical success or one of the 12
   error categories. No third shape.
3. `gateway/contracts.py` is the source of truth; this file is its mirror;
   `tests/test_contract_parity.py` blocks drift.
4. Layer 3 is fixed: providers conform, never extend.
5. The route token never appears in URLs, logs, traces, metrics, or upstream
   requests; missing/unknown/revoked/disabled are indistinguishable (uniform 404).
6. Credentials are memory-only: never persisted, logged, or cached.
7. `model` passes through untouched; the gateway never substitutes.
8. `usage` is raw evidence; the platform bills (reserveâsettle); the gateway
   holds no plans, no ledger, no tenant records; `usage` is null on failure.
9. `tenant_id` never influences any gateway decision.
10. The excluded operations are rejected at load time; declaration IS the
    source of eligibility.
11. Unknown fields are forbidden everywhere, recursively.
12. Nothing sensitive â credentials, tokens, slugs, upstream identity,
    exception names â ever crosses a boundary or a log line.
``