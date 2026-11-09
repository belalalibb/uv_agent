# Syntx Gateway Provider â Implementation Plan, Contract & Recovery Checkpoint

**Status:** Final â approved scope T01âT12, implementation complete and validated.
**Provider location:** `__gateway-service/providers/syntx/` (standalone provider).
**Baseline commit:** `d44a4f2`.
**Provenance:** Reconstructed from the approved conversation after a sandbox reset
removed the local-only commit `502d99f`. That Git object is not recoverable in this
checkout; this document is the durable recovery checkpoint and single source of
truth for the approved scope.
**Final validation:** 251 passing tests, 0 skipped, 2 dependency deprecation warnings.
**Draft PR:** https://github.com/Claude-Opus-5-code/Claude-Opus-5-code/pull/3
**Branch:** `feature/syntx-gateway-provider` â `main`.

---

## 1. Scope and non-goals

### In scope

- A standalone Syntx provider under `__gateway-service/providers/syntx/`,
  integrating with the gateway via `ProviderContext` â `FacadeResult`.
- Authorized-account management, transport, upstream chat orchestration, image
  upload, facade operations, canonical error normalization, maintenance, tests.
- The `filelock` dependency and ignore rules for runtime account state.

### Out of scope (explicitly not done)

- No changes to the gateway engine, canonical contracts, other providers
  (including Groq), `app.py` (beyond a real registration fix if ever required),
  or the original `ð¢_syntx_ai/` scripts.
- No automated trial account creation, quota bypass, or account rotation to
  evade service limits.
- No invented token/session refresh API: no documented official renewal
  endpoint was available.
- No merge, deployment, live smoke test, or use of production credentials.

---

## 2. Architectural boundaries

| Layer | Responsibility | Constraint |
|---|---|---|
| Layer 1 (internal) | Accounts, credentials, transport, sessions, images, maintenance | No runtime import or file dependency on the original `ð¢_syntx_ai/` project |
| Layer 2 (facade) | Accepts `ProviderContext`, returns exactly one canonical `FacadeResult` | Strict payload validation; no gateway-engine logic |

- Internal account management is provider logic, not gateway-engine logic.
- The gateway engine, canonical contracts, other providers, and original
  scripts remain unchanged.
- Operations: `generate_text`, `analyze_vision`; capability: `vision_input`.
- Credentials: platform credentials only. Four configured models.
- `health_supported=False`: the provider does not implement a health probe.

---

## 3. Model mapping and operation contract

Configured upstream model IDs and their canonical mapping:

| Upstream model ID | Canonical name |
|---|---|
| `gpt-5.6-terra` | `chatgpt` |
| `claude-opus-4-8` | `claude` |
| `claude-sonnet-5` | `claude` |
| `grok-4.6` | `grok` |

- The mapping is exact and immutable (central immutable configuration).
  Models are never silently substituted, and model identity is not claimed to
  be independently verified.

### `generate_text`

- Input: messages with nonempty role/content; history order and roles are
  preserved; the last message is never duplicated.
- Output: text plus a canonical `finish_reason`.
- `temperature` and `max_tokens` are validated for type; settings not supported
  upstream are validated locally but never sent.

### `analyze_vision`

- Input: `image_b64`, `image_format`, `instruction`.
- Output: text only.

### Token usage

- Token statistics come only from raw official upstream usage data. Unknown
  token counts are `None` â never estimated.

### Error normalization

The implementation defines the canonical set of 12 errors; their authoritative
names live in the provider code/contracts and are covered by tests. The
documented distinction matrix:

| Condition | Handling |
|---|---|
| Explicit `modelNotAvailableForPlan` | `MODEL_UNAVAILABLE`; the account is kept |
| Expired credentials | Distinguished from invalid credentials |
| Invalid credentials | Distinguished from expired credentials |
| Rate limit | Preserves `retry_after_ms`; Retry-After/cooldown evidence kept conservatively |
| Hard quota exhausted | Account state updated safely; credentials not damaged |
| Policy rejection | Canonical policy error |
| Bad input | Canonical input error |
| Network failure / timeout / any 5xx / other permanent failures | Each mapped to its canonical error via safe typed failures |

Additional binding rules:

- Plan-specific 403 does not damage stored credentials; expired credentials
  are excluded from the ready pool; 429 cooldown preserves records
  non-destructively.
- Public errors never expose raw exceptions, paths, tokens, identities, or URLs.
- No gateway retry behavior changes; no duplicate generation after an accepted
  submission.

---

## 4. Component design and task matrix

| Task | Component / deliverable | Acceptance criteria | Status |
|---|---|---|---|
| T01 | Baseline and dependency setup | Record actual existing failures, not assumed pass counts |  |
| T02 | `_config.py` | Immutable model mapping/settings; paths anchored inside the provider; no import-time I/O |  |
| T03 | `_accounts.py` | FileLock over the full read-modify-write; atomic private writes; safe merge/deduplication; no lost updates |  |
| T04 | Account states | Expired credentials excluded; 429 cooldown preserves records; plan-specific 403 does not damage credentials |  |
| T05 | `_transport.py` | Async injectable HTTP; monotonic total deadline; safe failures; no redirects leaking credentials |  |
| T06 | `_upstream.py` | Fresh server-created chat UUID per request; generate once; poll only completed current-session replies |  |
| T07 | `_images.py` | Validate base64/format/size; upload internally; no silent text-only fallback |  |
| T08 | `adapter.py` | Validate schemas; preserve message roles/order; exact operation outputs; no duplicate last message |  |
| T09 | Errors / deadline / usage | Canonical 12 errors; one total budget including locks; absent token statistics remain `None` |  |
| T10 | `_maintenance.py` | Authorized maintenance only; single worker; mockable; no network while holding the pool transaction lock |  |
| T11 | Definition / exports / registration / dependencies | Handler parity; existing app registration verified; filelock and ignore rules |  |
| T12 | Hermetic and regression tests | No real upstream, credentials, or background workers; exact results reported |  |

### Component details

- **`_config.py` (T02)** â Immutable central configuration: exact model mapping,
  settings, provider-local default paths anchored inside the provider directory,
  and independently copied generation options. No import-time I/O.
- **`_accounts.py` + account states (T03/T04)** â `FileLock` covers the full
  read-modify-write cycle; writes are atomic and private. Safe, idempotent
  merge and deduplication of staged accounts with no lost updates (validated
  under eight concurrent processes). Canceled/bounded lock waits; malformed-file
  and symlink protection.
- **`_transport.py` (T05)** â Injectable async HTTP with fixed internal paths,
  disabled redirects and proxy inheritance, bounded response bodies, a
  monotonic total deadline, and safe typed failures.
- **`_upstream.py` (T06)** â A fresh server-created chat UUID per request (no
  shared or reused chats); exactly one generation submission per request;
  polling only for completed replies of the current session; cross-session/job
  replies rejected; raw official usage only; cancellation propagation;
  deadline-bounded pool state updates.
- **`_images.py` (T07)** â Bounded, strict Base64 validation; PNG/JPEG/WebP
  format-framing validation; size limits; in-memory multipart upload; safe
  upload-result validation. Pixel decoding is performed upstream â local checks
  are not a full image codec. Upload failure can never fall back to a
  text-only success.
- **`adapter.py` (T08)** â Both canonical handlers, strict payload validation,
  ordered role-preserving history, exact operation outputs, no duplicated last
  message.
- **Errors / deadline / usage (T09)** â Canonical 12 errors; one shared
  multi-stage total deadline whose budget includes lock waits; absent token
  statistics remain `None`.
- **`_maintenance.py` (T10)** â Authorized maintenance only: merging staged
  authorized credentials and probing known read-only balance/limits endpoints
  when the ready pool is below threshold. Runs as a bounded request-triggered
  async worker â not a trial-provisioning subprocess or a permanent daemon.
  A nonblocking `FileLock` is held for the worker's entire lifetime across
  processes; a done callback releases it even if the worker is cancelled before
  first execution (crash-safe release). Fully mockable; no network operations
  while holding the pool transaction lock. Unknown evidence preserves accounts;
  quota/cooldown/credential evidence updates status safely.
- **Definition / exports / registration (T11)** â Static definition and
  side-effect-free exports with handler parity (both operations exported and
  registered identically); the existing app registration was verified to work
  unchanged; the `filelock` dependency and `.gitignore` rules were added.
- **Tests (T12)** â Hermetic: no real upstream, no real credentials, no
  background workers. Maintenance is disabled in chat fixtures and mocks are
  injected for worker tests.

---

## 5. Account, security, concurrency, and maintenance rules (binding)

1. Maintain authorized accounts only. No automated trial account creation,
   quota bypass, or rotation to evade service limits.
2. Official session renewal requires a documented authorized endpoint; none
   was available, so no refresh implementation was invented.
3. Maintenance is nonblocking and single-worker across processes, with
   ownership held for the worker's entire lifetime and released on exit or crash.
4. Network operations never run while holding the pool transaction lock.
5. Runtime account JSON, temporary state, and lock files are never committed
   (ignored via `.gitignore`). Existing tracked original account data requires
   separate remediation if it holds secrets.
6. Authorized credentials are supplied privately at runtime via
   `AccountPool.add_authorized` or `AccountPool.stage_authorized`. No real
   pool was copied into the repository or tests.
7. Private diagnostics (T12 security fix): the audit reproduced a third-party
   leak â httpx emitted upstream URLs when application logging was enabled.
   The fix is lazy, task-local filtering of private HTTP/filelock diagnostics,
   without changing logger levels/handlers and without suppressing unrelated
   concurrent requests. Cancellation restores logging. Regression checks cover
   cancellation restoring logging, import-time side-effect isolation, and the
   shared multi-stage deadline.

---

## 6. Authorized file scope

| Path | Change |
|---|---|
| `__gateway-service/providers/syntx/` | Provider implementation |
| `__gateway-service/tests/providers/test_syntx.py` | Existing facade tests; obsolete shared-chat fixtures replaced with real orchestration over synthetic accounts and mock HTTP |
| `__gateway-service/tests/providers/` | Focused hermetic tests for intermediate provider layers, so unfinished facade imports never hide validation of completed chunks |
| `__gateway-service/pyproject.toml` | `filelock` dependency |
| `.gitignore` | Account state, temporary files, locks |
| `__gateway-service/app.py` | Only if the existing registration required a real fix â verified: works unchanged |
| `docs/SYNTX_IMPLEMENTATION_PLAN.md` | This document (user-requested) |

---

## 7. Git and PR workflow

- Development/PR work is performed via `genspark_ai_developer` as mandated by
  the environment; the branch `feature/syntx-gateway-provider` is also created
  as requested. Target: `main`.
- Each chunk is tested, committed, fetched/rebased against `main`, and pushed
  to the Draft PR.
- When squashing is required, a single cumulative PR commit is kept.
- Force-push only with `--force-with-lease`; never an unconditional force push.
- This document preserves checkpoint status so a sandbox reset can resume from
  the remote branch.
- The GitHub access token is never persisted in files or remotes;
  authentication is process-memory only. The credential exposed in chat was
  flagged for revoke/rotation.

---

## 8. Verification evidence

### Test progression (all hermetic)

| Milestone | Result |
|---|---|
| T02 focused config tests | 3 passed |
| T03/T04 focused account tests (incl. eight concurrent processes) | 26 passed |
| T05 transport + config + accounts | 53 passed |
| T06 chat orchestration (incl. concurrent requests, incomplete polling) | 63 passed |
| T07 image upload | 75 passed |
| T10/T11 canonical integration checkpoint | 235 passed |
| T10/T11 complete full suite | 247 passed |
| **T12 final full suite** | **251 passed, 0 skipped**, 2 dependency deprecation warnings |

### Baseline (T01)

- The full baseline failed collection while Syntx was absent (missing
  `providers.syntx`, missing `fastapi`, asyncio pytest plugin unavailable).
- Diagnostic run excluding old Syntx tests: **121 passed, 1 failed** â the
  existing app registration imported the missing provider. Resolved by facade
  integration (T08).

### Security and isolation validation (final handoff)

- The entire suite passed with socket `connect`/`connect_ex`,
  `create_connection`, and DNS `getaddrinfo` blocked in the pytest process:
  **zero connection attempts**.
- Filesystem-only concurrency subprocesses and a separately guarded import
  test also passed. No live upstream and no real credentials were used.
- Ruff lint/format and `git diff --check` passed.
- Verified unchanged: gateway engine, canonical docs, Groq provider, `app.py`,
  and the original Syntx project.
- The final suite was restored and revalidated after an interrupted handoff.

---

## 9. Known limitations and required follow-ups

| Item | Status / required follow-up |
|---|---|
| Tracked original account data in the original project | Separate remediation required if it holds secrets |
| Live model availability | Not established â hermetic tests make no live claims; model identity is not independently verified |
| Dependency deprecation warnings (2) | Accepted; upstream dependency updates |
| Draft PR #3 | Retained for user review; no merge, deployment, or live smoke test performed |
| New features, production credential use, deployment, original-secret cleanup | Each requires a separately scoped follow-up |

---

## 10. Appendix â historical checkpoints (2026-09-12)

Condensed milestones from the implementation session. Superseded by Sections 8
and 9 for current status; retained for provenance.

- **Initial recovery** â Plan reconstructed after the sandbox reset lost
  `502d99f`. Baseline collection failed until dependencies were installed in
  the workspace `.venv` (no system environment changes). GitHub write
  permission was verified in memory; the user was advised to revoke/rotate the
  chat-exposed credential.
- **T01/T02** â Diagnostic baseline excluding old Syntx tests: 121 passed,
  1 failed. Immutable central config landed; 3 focused tests.
- **T03/T04 (recovered)** â The previous account chunk had not reached GitHub
  before the reset; it was reimplemented and retested from the approved design:
  26 focused tests. `filelock` and ignore rules were pulled forward from T11.
- **T05** â Injectable async HTTP, disabled redirects/proxy inheritance,
  bounded bodies, total deadline enforcement; 53 tests in cumulative scope.
- **T06** â Fresh chat per request, single submission, completed-session
  polling, cross-session rejection, raw usage, cancellation propagation;
  63 tests.
- **T07** â Strict Base64/format-framing validation, in-memory multipart
  upload, no text-only fallback; 75 tests.
- **T08/T09** â Both canonical handlers, strict validation, ordered history,
  all 12 normalized errors, static side-effect-free exports; existing app
  registration unchanged.
- **T10/T11** â Bounded request-triggered maintenance worker with lifetime
  `FileLock` ownership and done-callback release; probes only known read-only
  balance/limits endpoints below threshold; no refresh API invented;
  235 â 247 tests.
- **T12** â Reproduced and fixed the httpx URL-diagnostic leak with lazy
  task-local filtering; 251 tests; final handoff restored and revalidated.

---

## 11. Recovery procedure after sandbox reset

1. `git fetch origin` and restore the clean `genspark_ai_developer`
   remote-tracking branch.
2. Read this document first. **T01âT12 must not be reimplemented.**
3. Recreate the workspace-local `.venv` if needed; install the dependencies
   declared in `__gateway-service/pyproject.toml` (including dev extras), plus
   Ruff for linting.
4. Run the recorded validation command from `__gateway-service/`. The exact
   command below was executed in the Linux development sandbox; the
   platform-neutral intent is: run the full pytest suite from
   `__gateway-service/` using the workspace virtualenv, with bytecode writing
   and the pytest cache disabled and an isolated `--basetemp`:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest -p no:cacheprovider --basetemp=/home/user/webapp/.venv/test-final
   ```

5. Review Draft PR #3. Do not merge, deploy, or run live smoke tests without a
   separately scoped follow-up.