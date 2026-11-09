# Provider Onboarding Runbook (v1)

| | |
|---|---|
| **Status** | Active â v1 |
| **Audience** | Provider developers (gateway side); platform operators/admins (activation side) |
| **Scope** | Turning `providers/_example/` or `providers/_template/` into a real, registered provider |
| **Contract (normative prose)** | `docs/CONTRACT.md` |
| **Contract (code authority)** | `gateway/contracts.py` |
| **Templates** | `providers/_example/` (working mock reference), `providers/_template/` (line-by-line documented facade) |

> If `docs/CONTRACT.md` and `gateway/contracts.py` ever disagree, `gateway/contracts.py` is
> executable authority; file a documentation issue â do not resolve the gap inside your provider.

**Contents:** [1. The three-layer rule](#1-the-three-layer-rule) Â·
[2. Lifecycle overview](#2-lifecycle-overview) Â·
[3. Gateway-side steps](#3-gateway-side-steps) Â·
[4. `definition.py` requirements](#4-definitionpy-requirements) Â·
[5. `adapter.py` (facade) requirements](#5-adapterpy-facade-requirements) Â·
[6. Provider Development Form](#6-provider-development-form) Â·
[7. Credentials](#7-credentials) Â·
[8. Testing and acceptance criteria](#8-testing-and-acceptance-criteria) Â·
[9. Hard rules](#9-hard-rules) Â·
[10. Platform-side steps](#10-platform-side-steps) Â·
[11. Troubleshooting](#11-troubleshooting) Â·
[12. Change management](#12-change-management) Â·
[13. Final acceptance checklist](#13-final-acceptance-checklist) Â·
[14. Glossary](#14-glossary)

---

## 1. The three-layer rule

Read once, apply always. Every provider is built and evaluated against these layers:

- **Layer 1 â yours, free:** any files, any SDK, any auth (OAuth / sessions / cookies),
  account pools, chained upstream calls, internal fallbacks. Entirely invisible outside
  your provider package.
- **Layer 2 â the facade (mandatory):** `adapter.py` translates your internal result into
  the canonical contract â either a success payload matching the canonical output schema,
  or exactly one of the **12 error categories**. There is no third shape.
- **Layer 3 â fixed:** `gateway.contracts`. Import it. Never change it.

Consequence: the gateway sees only Layer 2's canonical boundary. Upstream call counts,
retries, fallbacks, and account switching inside Layer 1 are invisible by design â
**but** they never authorize gateway-level behavior (see [Â§9](#9-hard-rules)).

## 2. Lifecycle overview