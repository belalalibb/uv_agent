# Provider Gateway Service

The Gateway is a server-side data plane that exposes a common HTTP contract
for auto-discovered Provider adapters. Its code contract is
[`gateway/contracts.py`](gateway/contracts.py); the wire-level specification
and Provider runbook are in [`docs/CONTRACT.md`](docs/CONTRACT.md) and
[`docs/ONBOARDING.md`](docs/ONBOARDING.md).

## Current behavior

- `POST /v1/execute` accepts the closed Gateway v1 operation set and dispatches
  through the selected Provider's facade. Execution success and failure use
  the common response envelope.
- `GET /v1/providers`, `/v1/describe`, and `/v1/models` expose the public
  catalog and Provider manifests without internal slugs or route tokens.
- Provider definitions declare default `operations` and `capabilities`.
  A model can optionally provide `support.operations` and/or
  `support.capabilities`; each present dimension replaces that Provider
  default in full, and each omitted dimension inherits it. Discovery returns
  the effective fields directly on each model row.
- Runtime checks the effective operation list for a declared model and
  returns `unsupported_capability` if the operation is not declared for that
  model. An unlisted model name retains the existing Provider-default
  behavior. Capability values are descriptive metadata; the v1 Runtime gate
  is operation support.
- Process startup automatically discovers complete, non-hidden packages under
  `providers/` from their `definition.py` and `adapter.py` files, validates
  definitions, and verifies Definition/`HANDLERS` parity. Adding a Provider
  requires no central list in `app.py`.
- Name-based catalog/selection uses the discovered package definitions and
  needs no per-Provider `GW_PROVIDER_ALLOWLIST` or route-map entry. The
  optional `GW_ROUTE_MAP` is only for legacy `X-Route-Token` clients and
  requires the shared Gateway secret plus a token-to-slug mapping. A non-empty
  `GW_PROVIDER_ALLOWLIST` is obsolete and rejected. A request must not send
  both selectors.
- `/v1/health` currently reports `UNKNOWN`; no independent upstream health
  probe is performed. Streaming, Jobs, Assets, video, and Agent Core are not
  implemented by this Gateway v1 scope.

The Gateway secret is for a trusted backend service only. Do not place it in
browser code or an end-user application.

## Service configuration

Set `GW_SECRET_CURRENT` and `GW_SECRET_CURRENT_VERSION` in the Gateway
process environment; the launcher has no built-in development secret. No
Provider-specific environment variables are needed for catalog discovery or
name-based routing. `GW_ROUTE_MAP` is optional and is read only when keeping
legacy `X-Route-Token` clients working. Remove any non-empty
`GW_PROVIDER_ALLOWLIST`; that retired setting is rejected at startup. On the
SDK side, `GATEWAY_URL` and `GATEWAY_API_KEY` remain the common connection
settings.

## Repository layout

```text
__gateway-service/
├── app.py                       # composition with automatic Provider discovery
├── run_server.py                # alternate server entrypoint
├── gateway/
│   ├── contracts.py             # wire types, operations, and Provider models
│   ├── config.py                # Gateway authentication/routing configuration
│   ├── routes.py                # HTTP routes and Runtime enforcement
│   ├── discovery.py             # effective Provider/Model projections
│   ├── provider_registry.py     # Definition validation and handler parity
│   └── route_registry.py        # active route resolution
├── providers/
│   ├── <provider>/definition.py # Provider defaults and declared models
│   ├── <provider>/adapter.py    # canonical facade handlers
│   ├── _example/                # hermetic reference Provider
│   └── _template/               # documented Provider template
├── tests/                       # contract, unit, provider, and integration tests
└── docs/
    ├── CONTRACT.md              # canonical v1 wire contract
    └── ONBOARDING.md            # Provider onboarding and support semantics
```

## Development and tests

The service project requires Python 3.12 or newer. Install the dependencies
listed in `pyproject.toml`, then run the hermetic/default test suite from this
directory:

```bash
python -m pytest
```

The pytest configuration excludes tests marked `external_provider` by
default. Those tests need their declared external credentials/services and
should be run separately when intentionally available. See
[`docs/TESTING.md`](docs/TESTING.md) for test groups and commands.

For a new Provider, follow `docs/ONBOARDING.md`: add a complete package under
`providers/<slug>/`, declare only support that has a real handler, and test its
Discovery and Runtime behavior. Gateway discovers it on startup; no app.py
registration or per-Provider routing configuration is needed for
`X-Provider-Name`. A new Provider for an existing Operation does not need an
SDK-specific operation enum or schema. A genuinely new Operation is a Gateway
contract change and requires shared implementation, tests, and documentation
while the SDK remains generic.
