# Gateway test groups

The default `pytest` command is the hermetic gate: it runs Unit, Contract, and
Local Integration tests, and excludes the `external_provider` group. Every test
is assigned to one group during collection. Tests marked `external` (live
upstream/network access) or `provider_env` (provider account state or optional
local-domain fixtures) are automatically included in `external_provider`;
unclassified hermetic tests default to `unit`.

Run Gateway commands from `__gateway-service/` with Python 3.12+.

## Unit

Hermetic Gateway primitives and provider adapter tests, without external
provider prerequisites or local end-to-end Gateway tests.

```bash
python -m pytest -o addopts='' -m unit
```

## Contract

Gateway wire/data contracts, provider conformance, and documentation/code
parity checks.

```bash
python -m pytest -o addopts='' -m contract
```

## Local Integration

In-process Gateway/SDK flows and full wire-envelope tests using local ASGI apps
and mocked providers only; no upstream provider calls are made.

```bash
python -m pytest -o addopts='' -m integration
```

## External Provider

Run only when the required upstream services, provider account pools, or
optional provider-domain fixtures are intentionally provisioned:

```bash
python -m pytest -o addopts='' -m external_provider
```

The top-level `test_live_*.py` scripts are operational smoke tests and are not
part of the default `testpaths = ["tests"]` suite. Invoke them explicitly in a
credentialed environment; never place their secrets in CI logs or source.

Run the SDK's isolated HTTP client tests from the repository root; they are
outside the Gateway groups:

```bash
python -m pytest -o addopts='' tests/test_gateway_sdk.py
```

The repository currently has no checked-in CI workflow. A future CI job can use
the default command as its required hermetic gate and run `external_provider`
as an explicitly provisioned/optional job. The markers classify prerequisites;
they do not imply that an external test has passed.
