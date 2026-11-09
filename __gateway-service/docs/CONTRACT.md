# Provider Gateway — Canonical Contract (v1)

Authority: ADR-0008 (ACCEPTED 2026-08-29). **Source-of-truth rule:**
`gateway/contracts.py` is the authoritative code contract; this document is
its human-readable mirror. When they disagree, the code wins and this file
must be fixed. Drift is blocked by `tests/test_contract_parity.py`.

---

## THE THREE-LAYER PROVIDER MODEL

```
          PROVIDER PACKAGE
   ┌──────────────────────────────┐
   │ any file count, any shape    │  ← Layer 1 (FREE)
   │ auth/session/accounts/engines│
   │ SDK/recovery/orchestration   │
   └──────────────┬───────────────┘
            Provider Facade          ← Layer 2 (MANDATORY: the translator)
                  │
                  ▼
        Canonical Gateway Contract   ← Layer 3 (FIXED)
                  │
                  ▼
               Platform
```

### INTERNAL IMPLEMENTATION FREEDOM (Layer 1)

A provider implementation is an **opaque internal subsystem**. This
contract imposes NONE of the following:

- the provider's internal file structure (one file or thirty — equal),
- the number of modules / classes / functions,
- the internal orchestration strategy,
- SDK choice,
- authentication mechanism (OAuth / session / cookies / anything),
- account management, pools, or internal rotation,
- caching or any internal state,
- internal call chaining — one gateway request may internally produce N
  upstream calls + internal fallback + renormalization, all invisible to
  the platform.

**The only binding boundary is the final Facade** (Layer 2), which
translates whatever happened internally into the canonical contract.
Note: any provider-internal "retry" is subject to the gateway's rules —
**v1 = ZERO gateway-level retries** (usage/billing integrity, ADR-0008).

### ONE REQUEST → ONE CANONICAL RESPONSE

One gateway request ⇒ a free internal workflow (possibly auth + account
selection + several upstream calls + internal fallback + normalization) ⇒
**exactly one canonical response**. The platform never sees the internal
call count.

### The Facade (Layer 2 — mandatory)

- Receives a `ProviderContext` (operation / model / request_id / tenant_id
  / credential_mode / credential_value / payload / timeout_ms) — and never
  sees the slug, the route_token, or the true caller.
- Returns **either** a success matching the canonical output schema **or**
  an error mapped to one of the 12 categories. **No third shape exists.**
- A provider never invents its own response format for the gateway to
  "figure out" — the facade translates BEFORE anything crosses a boundary.

### Layer 3 — fixed for all providers

Request Envelope · Response Envelope · 12-category error taxonomy · Usage
shape · Security rules (`X-Gateway-Secret`[+`-Version`],
`X-Provider-Name`, legacy `X-Route-Token`) · HTTP status map. Providers
conform; they never extend it.

---

## API SURFACE (v1)

| Method + Path | Auth | Purpose |
|---|---|---|
| `POST /v1/execute` | secret+version | Execute any declared operation (`operation` in the envelope — single source of truth; NO per-operation routes) |
| `GET /v1/providers` | secret+version | Catalog of enabled public provider names and their manifests, including effective model support |
| `GET /v1/describe` | secret+version | Manifest projection, selected by `X-Provider-Name` or legacy `X-Route-Token` |
| `GET /v1/models` | secret+version | Declared models with effective operations/capabilities (cheap subset) |
| `GET /v1/health` | secret+version | Provider health (`UNKNOWN` is a legal answer) |
| `GET /healthz` | none | Process liveness only — no provider info, no secrets |

## SECURITY HEADERS

- `X-Gateway-Secret: <value>` + `X-Gateway-Secret-Version: <int>` on every
  authed call. Dual-accept rotation window (current + previous version;
  operational default 10 min). Wrong secret ⇒ 401 `invalid_credential`;
  stale version ⇒ 401 `auth_expired` with `retryable: true` (the platform
  adapter re-reads its secret store and retries once — self-healing).
- Provider-addressed calls select exactly one provider using either
  `X-Provider-Name: <public display_name>` (preferred) or the legacy
  `X-Route-Token: <opaque>`. The route token NEVER appears in a URL path or
  query string (ADR-0008 OPEN-3). The catalog and `X-Provider-Name` selection
  include only registered, enabled providers with an active `GW_ROUTE_MAP`
  entry and a slug present in `GW_PROVIDER_ALLOWLIST`. The route token remains
  server-side; a name-based SDK caller does not send it. The allowlist is
  Gateway-private and defaults to empty (deny all) for the name-based path and
  catalog. During the compatibility period, `X-Route-Token` is authorized
  separately by the gateway secret and a valid active token-to-slug mapping;
  it is intentionally not gated by `GW_PROVIDER_ALLOWLIST`. Thus an empty
  allowlist hides the catalog and denies name selection, but does not revoke
  legacy route tokens. Provider display names are unique after trimming and
  case-folding; duplicates fail registration.
- Unknown, unregistered, unrouted, revoked, or disabled provider selections
  all return the same uniform 404 body (anti-enumeration):

```json
{"error": {"category": "provider_unavailable", "retryable": false, "message": "unknown route"}}
```

- A Gateway secret is trusted backend authentication, not an end-user or
  browser credential; keep it in a server-side secret store. Holders share the
  deployment's `GW_PROVIDER_ALLOWLIST` scope when using `X-Provider-Name`.
  Legacy `X-Route-Token` requests additionally require an active token-to-slug
  mapping and are not constrained by that allowlist during this compatibility
  period. Applications needing different name-based scopes must use isolated
  Gateway deployments until principal-scoped credentials exist. The name
  selector itself does not prove possession of a provider-specific token.
- Never logged / never returned anywhere: credential values, route_token,
  slug, upstream identity, exception class names.

## HTTP STATUS MAP

| HTTP | Meaning |
|---|---|
| 200 | Envelope delivered — success **and** execution failures (read `error.category`) |
| 400 | Malformed envelope or both provider selectors supplied → `bad_request` |
| 401 | Gateway auth failure (wrong secret = `invalid_credential`; stale version = `auth_expired`, retryable) |
| 404 | Unknown, unregistered, unrouted, revoked, or disabled provider selection → uniform "unknown route" |
| 500 | Gateway internal fault → `retryable_server_error`, sanitized `provider_code` |

## REQUEST ENVELOPE (`POST /v1/execute`)

| Field | Type | Required | Semantics |
|---|---|---|---|
| `operation` | str (closed set of 8) | yes | The single source of truth for what runs |
| `model` | str | yes | Exact upstream model name — the gateway NEVER substitutes |
| `request_id` | str | yes | Platform correlation id; passed upstream where supported |
| `tenant_id` | str | yes | Evidence/audit only — zero gateway decisions on it |
| `credential` | object | yes | `{mode: "user_key"\|"platform", value?}` — mode MUST match the DEFINITION |
| `payload` | object | yes | Operation-specific (schemas below) |
| `timeout_ms` | int 1..600000 | yes | Enforced toward upstream |

Provider selection is outside the body: use `X-Provider-Name` or the legacy
`X-Route-Token` header. Forbidden by construction: `provider_slug`,
`upstream_url`, any internal identifier. Unknown body fields are rejected
(`extra="forbid"`).

## RESPONSE ENVELOPE

```json
{"succeeded": true, "output": {...}, "usage": {"input_tokens": 431, "output_tokens": 208, "units": 1}, "latency_ms": 812, "error": null}
```

Failure (HTTP 200 — execution failure):

```json
{"succeeded": false, "output": null, "usage": null, "latency_ms": 240,
 "error": {"category": "rate_limited", "retryable": true, "retry_after_ms": 2000,
           "message": "upstream call failed", "provider_code": "429"}}
```

`usage` is raw evidence only — the **platform** bills (reserve→settle);
the gateway holds no plans, no ledger, no tenant records.

## PROVIDER DEFAULTS AND MODEL SUPPORT

`ProviderDefinition.operations` and `ProviderDefinition.capabilities` are
Provider-level defaults: they describe support shared by its models unless a
model overrides that dimension. Existing capability keys and their boolean
shape stay unchanged; this v1 extension does not add an operation registry,
capability registry, per-operation payload schemas, or SDK-local catalog.

A declared model may omit `support` entirely, or selectively override either
support dimension:

```yaml
display_name: "Example Provider"
definition_version: "1.0.0"
credential_mode: "platform"
operations: ["generate_text"]
capabilities: {"chat": true}
models:
  - name: "text-model" # inherits Provider operations and capabilities
    context_window: 32000
  - name: "vision-model"
    support:
      operations: ["generate_text", "analyze_vision"]
      capabilities: {"chat": true, "vision_input": true}
```

The current closed capability-key set is `chat`, `reasoning`, `code`,
`vision_input`, `image_generation`, `audio_input`, `audio_output`,
`file_upload`, `browser`, `agent_module`, `embeddings`, `rerank`,
`moderation`, and `tool_use`; values are booleans. Unknown keys and unknown
fields in the definition are rejected.

| Definition field | Type | Meaning |
|---|---|---|
| `operations` | list of Gateway v1 operation strings | Provider default; must not contain duplicates |
| `capabilities` | object mapping closed keys to booleans | Provider default capability map |
| `models[].support` | optional object | Override container; omit to inherit both dimensions |
| `models[].support.operations` | optional list of operation strings | When present, replaces the complete model operation list; `[]` is valid |
| `models[].support.capabilities` | optional map of closed keys to booleans | When present, replaces the complete model capability map; `{}` is valid |

The public Discovery row is flattened and contains `name`, `context_window`,
effective `operations`, and effective `capabilities`; it does not contain
`support`. `context_window` is an integer or `null` when not declared.

- Missing `support.operations` inherits the Provider's operations; a present
  list replaces the full operation list for this model (including `[]`).
- Missing `support.capabilities` inherits the Provider's full capability map;
  a present map replaces that full map. The two dimensions inherit/replace
  independently; there is no implicit merge.
- Any operation in Provider defaults or in a model override must have a real
  facade handler. Normal process startup verifies parity across the union of
  defaults and all model operation overrides. Excluded v1 operations remain
  rejected.
- For an explicitly declared model, `POST /v1/execute` checks the effective
  operation list and returns an HTTP 200 execution failure with
  `unsupported_capability` when that operation is not supported for it.
  `capabilities` remain descriptive Discovery metadata in v1; Runtime's
  model-level gate is the operation list. Unlisted model names retain the
  existing behavior and use Provider defaults; the adapter/upstream may still
  report `model_unavailable`.
- Discovery returns resolved `operations` and `capabilities` directly on
  each model row; it does not expose the internal `support` override object.
  The SDK forwards this JSON without computing inheritance or maintaining a
  second catalog.
- Model names remain scoped to their Provider. The same string under two
  public Provider names represents two independent choices; no global model
  ID, alias, or canonicalization is used.
- Adding a Provider for an existing Operation uses this contract as-is. A
  genuinely new Operation is a Gateway contract change: update the closed
  operation type, implementation/dispatch, documentation, and tests, then
  declare it only for Providers/Models with a real handler. The SDK stays
  generic and does not need an Operation enum or provider-specific schema.

## THE 12 ERROR CATEGORIES (verbatim, platform-led — never extended)

| Category | Retryable default | Use for |
|---|---|---|
| `auth_expired` | yes | valid credential/session that expired (refresh may fix) |
| `invalid_credential` | no | wrong/revoked key or session |
| `rate_limited` | yes | upstream 429/throttle — set `retry_after_ms` |
| `quota_exceeded` | no | hard quota / billing cap |
| `model_unavailable` | no | requested model missing upstream |
| `provider_unavailable` | no | upstream down/unreachable (platform decides failover) |
| `unsupported_capability` | no | operation/feature not declared/supported |
| `bad_request` | no | caller payload invalid |
| `content_rejected` | no | safety/policy refusal to process |
| `timeout` | yes | upstream exceeded `timeout_ms` |
| `retryable_server_error` | yes | upstream 5xx / transient |
| `non_retryable_error` | no | everything else, permanent |

`provider_code`: sanitized short token (e.g. `"429"`) — never exception
class names, never free text.

## OPERATIONS EXCLUDED FROM v1 (ADR-0008 OPEN-2)

`run_provider_agent`, `upload_asset`, `download_asset` — no implementation,
no API surface. A DEFINITION declaring any of them is **rejected at load
time**. An unsupported operation is never represented by an empty declared
stub — declaration IS the source of eligibility.

## THE 8 v1 OPERATIONS — payload in, canonical output out

For every operation: **input payload fields** (name / type / required),
the **exact successful output shape**, the error form (always a
`GatewayError` in one of the 12 categories), and a full example.

### 1. `generate_text`

| Payload field | Type | Required |
|---|---|---|
| `messages` | list[{role: str, content: str}] | yes (non-empty) |
| `temperature` | float | no |
| `max_tokens` | int | no |

Canonical success output: `{"text": str, "finish_reason": "stop"|"length"|"filter"}`

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
Error form example (upstream 429):
```json
{"succeeded": false, "output": null, "usage": null, "latency_ms": 200,
 "error": {"category": "rate_limited", "retryable": true, "retry_after_ms": 2000,
           "message": "upstream call failed", "provider_code": "429"}}
```

### 2. `generate_image`

| Payload field | Type | Required |
|---|---|---|
| `prompt` | str | yes |
| `size` | str (e.g. "1024x1024") | no |
| `count` | int | no (default 1) |

Canonical success output: `{"images": [{"b64": str, "format": str}]}` · Usage: `units` = images generated.

```json
{"payload": {"prompt": "a red cube", "count": 1}}
```
```json
{"succeeded": true, "output": {"images": [{"b64": "<base64>", "format": "png"}]},
 "usage": {"units": 1}, "latency_ms": 2100, "error": null}
```
Errors: policy refusal → `content_rejected`; quota cap → `quota_exceeded`.

### 3. `transcribe_audio`

| Payload field | Type | Required |
|---|---|---|
| `audio_b64` | str (base64) | yes |
| `audio_format` | str ("mp3"/"wav"/…) | yes |
| `language` | str (BCP-47) | no |

Canonical success output: `{"text": str, "language": str|null}`

```json
{"payload": {"audio_b64": "<base64>", "audio_format": "wav"}}
```
```json
{"succeeded": true, "output": {"text": "hello world", "language": "en"},
 "usage": {"units": 1}, "latency_ms": 900, "error": null}
```
Errors: undecodable/oversized audio → `bad_request`.

### 4. `synthesize_speech`

| Payload field | Type | Required |
|---|---|---|
| `text` | str | yes |
| `voice` | str | no |
| `audio_format` | str | no (default "mp3") |

Canonical success output: `{"audio_b64": str, "audio_format": str}`

```json
{"payload": {"text": "hello", "voice": "alloy"}}
```
```json
{"succeeded": true, "output": {"audio_b64": "<base64>", "audio_format": "mp3"},
 "usage": {"input_tokens": 5, "units": 1}, "latency_ms": 700, "error": null}
```
Errors: unknown voice → `bad_request`; refusal → `content_rejected`.

### 5. `create_embeddings`

| Payload field | Type | Required |
|---|---|---|
| `inputs` | list[str] | yes (non-empty) |

Canonical success output: `{"embeddings": [[float,...],...], "dimensions": int}` —
`embeddings[i]` corresponds to `inputs[i]`, order preserved. Usage: `units` = len(inputs).

```json
{"payload": {"inputs": ["hello"]}}
```
```json
{"succeeded": true, "output": {"embeddings": [[0.01, -0.02, 0.5]], "dimensions": 3},
 "usage": {"input_tokens": 1, "units": 1}, "latency_ms": 90, "error": null}
```
Errors: empty/oversized batch → `bad_request`.

### 6. `rerank_documents`

| Payload field | Type | Required |
|---|---|---|
| `query` | str | yes |
| `documents` | list[str] | yes (non-empty) |
| `top_n` | int | no (default all) |

Canonical success output: `{"results": [{"index": int, "relevance_score": float}]}` —
`index` refers to the caller's list; sorted by score descending; ≤ top_n rows.

```json
{"payload": {"query": "cats", "documents": ["dog", "cat"]}}
```
```json
{"succeeded": true,
 "output": {"results": [{"index": 1, "relevance_score": 0.97}, {"index": 0, "relevance_score": 0.12}]},
 "usage": {"units": 2}, "latency_ms": 120, "error": null}
```
Errors: empty documents → `bad_request`.

### 7. `moderate_content`

| Payload field | Type | Required |
|---|---|---|
| `content` | str | yes |

Canonical success output: `{"flagged": bool, "categories": {str: bool}}` —
a "flagged" verdict is a SUCCESS (the moderation ran); `content_rejected`
is only for the upstream REFUSING to process.

```json
{"payload": {"content": "some text"}}
```
```json
{"succeeded": true, "output": {"flagged": false, "categories": {"hate": false}},
 "usage": {"units": 1}, "latency_ms": 60, "error": null}
```

### 8. `analyze_vision`

| Payload field | Type | Required |
|---|---|---|
| `image_b64` | str (base64) | yes |
| `image_format` | str ("png"/"jpeg"/…) | yes |
| `instruction` | str | yes |

Canonical success output: `{"text": str}`

```json
{"payload": {"image_b64": "<base64>", "image_format": "png", "instruction": "what color is the cube?"}}
```
```json
{"succeeded": true, "output": {"text": "The cube is red."},
 "usage": {"input_tokens": 850, "output_tokens": 8, "units": 1}, "latency_ms": 1400, "error": null}
```
Errors: undecodable image → `bad_request`; non-vision model → `unsupported_capability`.

## DISCOVERY SHAPES

`GET /v1/providers` returns only enabled registrations; `name` is the public
`display_name` accepted by `X-Provider-Name`, and `description` is the same
manifest projection returned by `/v1/describe`:
```json
{"providers": [{"name": "Example Provider", "description":
  {"display_name": "Example Provider", "credential_mode": "user_key",
   "capabilities": {"chat": true}, "operations": ["generate_text"],
   "models": [{"name": "upstream-model", "context_window": 128000,
               "operations": ["generate_text"], "capabilities": {"chat": true}}],
   "definition_version": "1.2.0", "health_supported": true}}]}
```
`GET /v1/describe` selects by `X-Provider-Name` (or legacy `X-Route-Token`)
and never returns a slug or upstream identity. `GET /v1/models`:
`{"models": [...]}` · `GET /v1/health`:
`{"status": "OK"|"DEGRADED"|"DOWN"|"UNKNOWN", "checked_at": str|null}`

## CREDENTIAL MODES

- `user_key` (BYOK): resolved platform-side, crosses TLS inside the
  envelope, **memory-only** at the gateway — never persisted, never logged.
- `platform`: resolved internally by the provider facade (keyed by the
  gateway's own means) — never from the request; the platform never learns
  the credential kind.
- Envelope `credential.mode` MUST equal the DEFINITION's `credential_mode`
  or the request fails as `bad_request` (200 execution failure).
