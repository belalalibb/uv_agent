# Provider Resolution — pre-change review

> **Snapshot note:** the opening sections record the token-resolution baseline before the name-based resolver and model-support extension. They are historical; the current behavior and latest validation are summarized below and in `CONTRACT.md`/`ONBOARDING.md`.

## Reviewed execution path

1. `app.py` is composition only: `main()` loads `GatewayConfig`, builds a `ProviderRegistry`, calls `register_live_providers()`, verifies handlers, then wires `build_app()`.
2. `POST /v1/execute` in `gateway/routes.py` authenticates the gateway secret, reads `X-Route-Token`, resolves token → private slug through `RouteRegistry`, and resolves slug → `RegisteredProvider` through `ProviderRegistry`.
3. The request is validated as `RequestEnvelope`; the gateway checks the operation against that provider's `ProviderDefinition`, validates credential mode, lazily imports the facade and checks handler parity, then passes a `ProviderContext` that excludes the route token and private slug. The facade returns `FacadeResult`; the HTTP layer serializes `ResponseEnvelope`.
4. `/v1/describe`, `/v1/models`, and `/v1/health` use the same token-based resolution. `gateway/discovery.py` projects only declared public fields; `display_name` is the sole provider name currently authorized to cross the boundary.

## Registries, route tokens, and discovery today

- `ProviderRegistry` is populated by a manual 14-provider list in `app.register_live_providers()`. It validates definitions at registration, lazily imports adapters, and checks declared-operation/handler parity. Package discovery is not currently automatic in the running composition.
- `GatewayConfig.GW_ROUTE_MAP` is provisioned as `opaque token : private slug`. `RouteRegistry` owns the in-memory map, revoke/disable behavior, and hot reload; it currently resolves only an incoming token. The provider registry itself does not prove that a provider has an active route.
- The previous `client/ProviderManager` (present in `origin/main`, not this branch's working tree) keeps alias → token mappings in memory, environment, or a JSON file. Discovery starts from a token supplied by the consumer, calls `/v1/describe`, then derives/stores aliases. The legacy SDK sends the token in `X-Route-Token`.
- There is no Gateway-wide provider catalog or provider-name resolver in the restored service. Current `/v1/describe` is per-token.

## Contract and tests

- `gateway/contracts.py` is the wire-contract source of truth. `GatewayOperation` is a Gateway-owned closed set; `RequestEnvelope.payload` and response `output` are generic dictionaries. Provider definitions declare supported operations and models, but there are no per-operation input/output JSON schemas. The SDK must not infer such schemas.
- Gateway contract/discovery/dispatch/route/registry tests are hermetic. `tests/conftest.py` wires a mock provider and a token→slug route. Existing acceptance coverage includes successful dispatch, auth failures, malformed/undeclared operations, uniform 404s, discovery projections, and route revocation/disable/reload.
- The service declares Python `>=3.12`. The available test environment for this review was Python 3.11.2, so the declared Python 3.12 target itself was not validated here. The latest hermetic Gateway run passed (`400 passed, 26 deselected, 1 warning`); the root SDK suite passed (`10 passed`). Tests marked `external_provider` were not run.
- The selective restore brought in exactly the 262 files from `origin/main@c53a02c` (hash-verified); no existing path was overwritten. `gateway_sdk/` remains separate and unchanged by the restore.

## First functional slice and compatibility boundary

The first functional slice keeps the existing request envelope, execution result, and provider facade contracts intact. An authenticated caller selects a provider by its public `display_name` using `X-Provider-Name`; Gateway resolves that name against registered definitions and confirms the provider is enabled by both the existing route registry and the deployment's provider allowlist. Route tokens and private slugs remain server-side. Authenticated `GET /v1/providers` reports only allowlisted, enabled providers and their manifests, including effective operations/capabilities per declared model. Existing `X-Route-Token` callers remain supported without an immediate sunset.

The new name-based selector requires the Gateway secret and an explicit `GW_PROVIDER_ALLOWLIST` of Gateway-private slugs. The allowlist defaults to empty (deny all), and only allowlisted, registered, routed, enabled providers appear in the catalog or resolve by name. During compatibility, legacy `X-Route-Token` requests are intentionally not gated by this allowlist; they require the Gateway secret plus a valid active token-to-slug mapping. A Gateway secret is trusted backend authentication and must stay in a server-side secret store, never in browsers or end-user clients. Holders share the deployment's allowlist scope on the name path; applications needing different scopes must use isolated Gateway deployments until principal-scoped authorization exists. The name selector itself does not prove possession of a provider-specific token.

The SDK transition is additive: when an old `provider_routes`/`ROUTE_TOKEN_*` entry exists, it continues sending `X-Route-Token`; when no local route token is configured, it sends the provider name and uses the Gateway catalog. No provider or operation allowlists, operation-specific models, or guessed payload schemas are added to the SDK.

## Model support extension

Provider definitions may declare default `operations` and `capabilities`. A
model may optionally provide `support.operations`, `support.capabilities`, or
both; an omitted dimension inherits the Provider default and a present
dimension replaces it completely. Discovery flattens these into each model's
effective `operations` and `capabilities` fields. Startup Handler parity covers
the union of Provider-default and model-override operations. Runtime enforces
the effective operation list for declared models; an unlisted model keeps the
existing Provider-default behavior. Capability values remain descriptive
metadata in v1; there is no separate Capability registry or enforcement
engine.

The SDK's `list_models()` returns the raw model rows, while
`list_operations()` continues to return Provider defaults. The SDK does not
compute inheritance or add a Provider/Operation-specific API. The integration
test covers inherited and overridden support, successful execution, and
rejection of an operation not declared for the selected model.

## Acceptance checks

- A name-only request executes a declared operation without `X-Route-Token`; the operation and generic payload still pass through the existing Gateway contract.
- The catalog contains enabled registered providers and their declared operations, but never route tokens or private slugs; disabled/unrouted providers are absent.
- Unknown, disabled, unregistered, and unrouted names share the existing generic 404 body. Supplying both selector headers is rejected as a bad request.
- The legacy token header still executes and discovers a provider; auth and credential-mode enforcement are unchanged.
- SDK name-only discovery/describe/models/health/execute work with no local token mapping, while a configured mapping continues using the legacy header. SDK responses remain open-ended and do not encode provider or operation lists.

These checks are covered by `tests/test_dispatch.py`, `tests/test_discovery.py`, `tests/test_provider_registry.py`, `tests/test_route_registry.py`, `tests/test_sdk_gateway_integration.py`, and the root SDK suite `tests/test_gateway_sdk.py`. In the latest run, the default Gateway suite passed (`400 passed, 26 deselected`) and the SDK suite passed (`10 passed`) under the available Python 3.11.2 test environment; Python 3.12+ validation remains outstanding. External-provider tests were not run. No live provider calls or secrets were used by the integration test. Dynamic operation discovery and operation schemas remain out of scope.
