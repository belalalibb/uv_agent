# Syntx implementation plan — approved T01–T12

Approved scope: standalone provider in `__gateway-service/providers/syntx/`.
Baseline: `d44a4f2`. Reconstructed from the approved conversation after a sandbox
reset removed the local-only `502d99f` commit; that Git object is not recoverable
in this checkout. This document is the durable recovery checkpoint.

**Current status: T01–T12 complete for the approved authorized-account scope.**
Final validation: 251 passing tests. Draft PR: https://github.com/Claude-Opus-5-code/Claude-Opus-5-code/pull/3

## Architectural boundaries

- Layer 1 owns accounts, credentials, transport, sessions, images and maintenance.
  No runtime import or file dependency on the original `🟢_syntx_ai/` project.
- Layer 2 accepts `ProviderContext` and returns one canonical `FacadeResult`.
- Gateway engine, canonical contracts, other providers and original scripts stay
  unchanged. Internal account management is not gateway-engine logic.
- Operations: `generate_text`, `analyze_vision`; capability `vision_input`.
- Platform credentials; four configured models; `health_supported=False`.
- Maintain authorized accounts only. No automated trial account creation, quota
  bypass, or rotation to evade service limits. Official session renewal requires
  a documented authorized endpoint; do not invent a refresh implementation.
- Maintenance must be nonblocking and single-worker across processes, with
  ownership held throughout the worker's lifetime and released on exit/crash.
- Runtime account JSON, temporary state and locks are never committed. Existing
  tracked original account data requires separate remediation if it holds secrets.

## Approved task matrix

| Task | Deliverable | Acceptance |
|---|---|---|
| T01 | Baseline and dependency setup | Record actual existing failures, not assumed pass counts |
| T02 | `_config.py` | Immutable model mapping/settings; paths anchored inside provider; no import-time I/O |
| T03 | `_accounts.py` | FileLock over full read-modify-write; atomic private writes; safe merge/deduplication; no lost updates |
| T04 | Account states | Expired credentials excluded; 429 cooldown preserves records; plan-specific 403 does not damage credentials |
| T05 | `_transport.py` | Async injectable HTTP; monotonic total deadline; safe failures; no redirects leaking credentials |
| T06 | `_upstream.py` | Fresh server-created chat UUID per request; generate once; poll only completed current-session replies |
| T07 | `_images.py` | Validate base64/format/size; upload internally; no silent text-only fallback |
| T08 | `adapter.py` | Validate schemas; preserve message roles/order; exact operation outputs; no duplicate last message |
| T09 | Errors/deadline/usage | Canonical 12 errors; one total budget including locks; absent token statistics remain None |
| T10 | `_maintenance.py` | Authorized maintenance only; single worker; mockable; no network while holding pool transaction lock |
| T11 | Definition/exports/registration/dependencies | Handler parity; verify existing app registration; filelock and ignore rules |
| T12 | Hermetic and regression tests | No real upstream, credentials or background workers; report exact results |

## Contract decisions

Configured upstream IDs: `gpt-5.6-terra`, `claude-opus-4-8`, `claude-sonnet-5`,
`grok-4.6`. Mapping respectively: `chatgpt`, `claude`, `claude`, `grok`. Do not
silently substitute models or claim independent verification of model identity.

`generate_text` takes nonempty role/content messages and produces text plus
canonical finish_reason. `analyze_vision` takes image_b64/image_format/instruction
and produces text only. Validate temperature/max_tokens types but do not send
unsupported settings upstream. Unknown token counts are None, never estimated.

Distinguish explicit modelNotAvailableForPlan (MODEL_UNAVAILABLE, account kept),
expired versus invalid credentials, rate limit with retry_after_ms, hard quota,
policy rejection, bad input, network failure, timeout, all 5xx and other permanent
failures. Never expose raw exceptions, paths, tokens, identities or URLs in errors.
No gateway retry changes, no duplicate generation after an accepted submission.

## Authorized file scope

- `__gateway-service/providers/syntx/`
- `__gateway-service/tests/providers/test_syntx.py` (existing facade tests)
- Focused hermetic tests for intermediate provider layers as needed, under
  `__gateway-service/tests/providers/`, so unfinished facade imports do not hide
  validation of completed chunks.
- `__gateway-service/pyproject.toml`: filelock dependency
- `.gitignore`: account state, temporary files, locks
- `__gateway-service/app.py` only if existing registration requires a real fix
- This user-requested `docs/SYNTX_IMPLEMENTATION_PLAN.md`

## Chunk and Git workflow

Use `genspark_ai_developer` for development/PR as mandated by the environment;
`feature/syntx-gateway-provider` is also created as requested. Target main.
Each chunk is tested and committed, fetched/rebased against main, and pushed to
the Draft PR. Keep a single cumulative PR commit when squashing is required;
use force-with-lease (never an unconditional force push). Preserve checkpoint
status here so a reset can resume from the remote branch. Never persist the
GitHub access token in files or remotes; authentication is process-memory only.

## Initial recovery checkpoint (historical)

- Recovery plan reconstructed; implementation not yet started.
- Last session's baseline attempt failed collection: providers.syntx missing,
  fastapi missing, and asyncio pytest plugin unavailable. T01 is NOT complete
  solely because the earlier plan commit existed.
- GitHub credential checked in memory: repository write permission available.
  User advised to revoke/rotate the credential exposed in chat.
- Next: publish recovery plan, install declared dependencies inside workspace,
  finish T01, then implement T02 followed by T03/T04 and T05/T06.

### Chunk T01/T02 (2026-09-12)

- Installed dependencies in workspace `.venv` (no system environment changes).
- Full baseline still fails collection because Syntx is absent. Diagnostic run
  excluding old Syntx tests: **121 passed, 1 failed** (existing app registration
  imports the missing provider). These failures remain until facade integration.
- T02 complete: immutable central config, exact model mapping, provider-local
  default paths and independently copied generation options.
- Focused config tests: **3 passed**. Ruff format/check passed.
- Next: T03/T04 transactional account storage and state handling. No facade yet.

### Recovered T03/T04 checkpoint (2026-09-12)

The previous account chunk did NOT reach GitHub before reset. Reimplemented and
retested it from the approved design. **26 focused tests pass**: private atomic
writes, eight concurrent processes, canceled/bounded lock waits, malformed and
symlink protection, idempotent staging/merge, expiry/invalid/quota state and
non-destructive cooldown. filelock and ignore rules pulled forward from T11.
No real credentials copied. T03/T04 complete; next T05/T06. Facade still pending.

### T05 checkpoint (2026-09-12)

Added injectable async HTTP with fixed internal paths, disabled redirects/proxy
inheritance, bounded response bodies, total deadline enforcement and safe typed
failures. Retry-After/structured cooldown evidence is preserved conservatively.
Transport plus account/config tests: **53 passed**. Next T06 chat orchestration.

### T06 checkpoint (2026-09-12)

Fresh server-created chat per request, exact model/ai_name mapping, one generation
submission, completed-message polling, cross-session/job rejection, raw official
usage only, cancellation propagation and deadline-bounded pool state updates.
**63 focused tests passed** including concurrent requests and incomplete polling.
T02–T06 are implemented. Next T07 image upload, T08/T09 facade and T10 maintenance.

### T07 checkpoint (2026-09-12)

Added bounded strict Base64/format-framing validation (PNG/JPEG/WebP), in-memory
multipart upload, safe upload-result validation and internal files construction.
Pixel decoding is performed upstream; local checks are not a full image codec.
Upload failure cannot fall back to text-only success. **75 focused tests passed**.

### T08/T09 and declaration checkpoint (2026-09-12)

Restored from published T07 after reset. Added both canonical handlers, strict
payload validation, ordered role-preserving history, unknown-usage handling and
all 12 normalized errors. Added static definition and side-effect-free exports.
Existing app registration works unchanged. Obsolete shared-chat test fixtures were
replaced with real orchestration over synthetic accounts and mock HTTP.
Full gateway suite now runs successfully; maintenance/T10 and final hardening
remain pending. Ruff passed. See PR chunk comment for the exact suite count.

### T10/T11 checkpoint (2026-09-12)

Canonical integration checkpoint passed **235 tests**. Maintenance now runs as a
bounded request-triggered async worker, not a trial-provisioning subprocess or
permanent daemon. A nonblocking FileLock is held for its entire lifetime across
processes; a done callback releases it even if cancelled before first execution.
It merges authorized staged credentials and probes only known read-only balance
and limits endpoints when the ready pool is below threshold. Unknown evidence
preserves accounts; quota/cooldown/credential evidence updates status safely.
No documented token-renewal endpoint was available: no refresh API was invented.
Network operations never hold the pool transaction lock. Tests explicitly disable
maintenance in chat fixtures and inject mocks for worker tests.
Full suite: **247 passed**, two dependency deprecation warnings. Ruff passed.
T02–T11 implementation complete; T12 final security/regression review remains.

### T12 security checkpoint (2026-09-12)

Audit reproduced a third-party diagnostic leak: httpx emitted upstream URLs when
application logging was enabled. Added lazy, task-local filtering for private
HTTP/filelock diagnostics without changing logger levels/handlers or suppressing
unrelated concurrent requests. Added regression checks for cancellation restoring
logging, import-time side-effect isolation and a shared multi-stage deadline.
**251 tests passed**, two dependency deprecation warnings; Ruff passed.
Final network-denied rerun and repository/PR verification remain before handoff.


## Final handoff — 2026-09-12

- Restored published code after the interrupted handoff and repeated validation:
  **251 passed, zero skipped, two dependency deprecation warnings**.
- Entire suite passed with socket connect/connect_ex, create_connection and DNS
  getaddrinfo blocked in the pytest process: **zero connection attempts**.
  Filesystem-only concurrency subprocesses and the separately guarded import test
  also passed. No live upstream or real credentials were used.
- Ruff lint/format and git diff --check passed. Gateway engine, canonical docs,
  Groq, app.py and the original Syntx project are unchanged.
- Provider runtime account files are ignored, not committed. Existing tracked
  account data in the original project requires separate remediation if sensitive.
- Authorized credentials must be supplied privately at runtime through
  AccountPool.add_authorized or stage_authorized. No real pool was copied.
- Maintenance is a bounded request-triggered async worker with exclusive lifetime
  ownership, not a permanent daemon or trial-registration subprocess. No official
  token-renewal endpoint was available; no refresh API was invented.
- Image checks validate Base64, size and format framing; upstream performs pixel
  decoding. Hermetic tests do not establish live model availability.
- Draft PR retained for user review. No merge, deployment or live smoke test.

### Resume after reset

Fetch origin, restore the clean `genspark_ai_developer` remote-tracking branch,
and read this final handoff before doing work. T01–T12 must not be reimplemented.
Recreate workspace-local `.venv` if needed and install the dependencies declared
in `__gateway-service/pyproject.toml` (including dev), plus Ruff for linting.
From `__gateway-service`, run:
`PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest -p no:cacheprovider --basetemp=/home/user/webapp/.venv/test-final`
Review Draft PR #3. Any new feature, production credential use, deployment or
original-secret cleanup requires a separately scoped follow-up.
