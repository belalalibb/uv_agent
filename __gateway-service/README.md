# Provider Gateway Service

The Gateway is a server-side data plane that exposes a common HTTP contract
for registered Provider adapters. Its code contract is
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
- Provider registration is explicit in `app.register_live_providers()`;
  process startup verifies Definition/`HANDLERS` parity. Routing still
  requires deployment configuration. There is no assumption of automatic
  plugin discovery or registration.
- Name-based catalog/selection uses the Gateway's `GW_PROVIDER_ALLOWLIST`
  and active route map. The allowlist is empty by default. The legacy
  `X-Route-Token` selector remains available during the compatibility period,
  requires the trusted Gateway secret and an active route mapping, and is not
  gated by the name-based allowlist. A request must not send both selectors.
- `/v1/health` currently reports `UNKNOWN`; no independent upstream health
  probe is performed. Streaming, Jobs, Assets, video, and Agent Core are not
  implemented by this Gateway v1 scope.

The Gateway secret is for a trusted backend service only. Do not place it in
browser code or an end-user application.

## Repository layout

```text
__gateway-service/
├── app.py                       # composition and explicit live registrations
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

For a new Provider, follow `docs/ONBOARDING.md`: declare only support that has
a real handler, register it explicitly, configure both routing and the
name-based allowlist as needed, and test its Discovery and Runtime behavior.
A new Provider for an existing Operation does not need an SDK-specific
operation enum or schema. A genuinely new Operation is a Gateway contract
change and requires shared implementation, tests, and documentation while the
SDK remains generic.
