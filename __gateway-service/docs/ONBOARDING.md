# Provider Onboarding Runbook (v1)

This runbook covers adding a Gateway Provider that implements operations
already in the Gateway contract. The code authority is
[`gateway/contracts.py`](../gateway/contracts.py); the human-readable wire
contract is [`CONTRACT.md`](CONTRACT.md), and the reference facade is
[`providers/_template/`](../providers/_template/).

Adding a Provider for an existing operation is Gateway work: it does not
require a provider-specific SDK or Agent Core change. Production registration
is explicit; do not assume that a new package is discovered or enabled
automatically.

## The three-layer rule

- **Provider internals:** free to use private modules, SDKs, auth flows,
  account pools, and internal orchestration.
- **Facade:** `adapter.py` translates the internal result to the canonical
  success output or one of the 12 Gateway error categories.
- **Shared contract:** `gateway.contracts` defines the stable boundary all
  providers must follow. A Provider must not extend it for its own needs.
  Adding a new global Operation or contract Capability is a separate Gateway
  contract change, not part of ordinary Provider onboarding; see
  [Adding a new Operation](#adding-a-new-operation).

## Gateway-side steps

1. **Create the Provider package.** Copy `providers/_example/` as a working
   reference or `providers/_template/` as a blank facade into
   `providers/<your_provider>/`. Do not use a leading underscore; reference
   packages with that prefix are not live Providers.

2. **Declare honest Provider defaults and models** in `definition.py`.
   `operations` and `capabilities` are defaults shared by models that do not
   override that dimension. Use only the existing eight Gateway operations,
   and only keys from the closed `CAPABILITY_KEYS` set. `definition_version`
   must be semver `X.Y.Z`; bump it when the declaration changes.

   Add model `support` only when a model differs from the defaults. For
   example, the actual definition format is a Python mapping:

   ```python
   DEFINITION = {
       "display_name": "Example Public Provider",
       "definition_version": "1.0.0",
       "credential_mode": "platform",
       "operations": ["generate_text"],
       "capabilities": {"chat": True},
       "models": [
           {"name": "text-model", "context_window": 32_000},
           {
               "name": "vision-model",
               "context_window": 64_000,
               "support": {
                   "operations": ["generate_text", "analyze_vision"],
                   "capabilities": {"chat": True, "vision_input": True},
               },
           },
       ],
   }
   ```

   The dimensions inherit independently: omit `support.operations` to inherit
   Provider operations, or provide it to replace that model's full operation
   list (including an intentional empty list). Omit
   `support.capabilities` to inherit the full Provider capability map, or
   provide it to replace that map in full. There is no implicit merge. A
   declared model's effective `operations` and `capabilities` are returned
   directly by `/v1/describe`, `/v1/models`, and `/v1/providers`; Discovery
   does not return the internal `support` override object.

3. **Implement the facade.** Every operation in Provider defaults or any
   model-specific operation override must have a real handler in
   `adapter.py`. The `HANDLERS` mapping must exactly match the union of those
   declarations: missing handlers and undeclared extra handlers fail parity
   verification. In normal process startup, `register_live_providers()` is
   followed by `eager_verify_all()` to validate that parity.

4. **Handle credentials safely.** For `user_key`, the request credential is
   transient and must not be stored or logged. For `platform`, resolve the
   credential inside the Provider from its server-side configuration; never
   accept it from the request. Never return credentials, route tokens, slugs,
   upstream identities, or exception class names.

5. **Register and route the Provider explicitly.** Add its Definition and
   Adapter to `app.register_live_providers()`. Configure the deployment's
   `GW_ROUTE_MAP` and `GW_PROVIDER_ALLOWLIST` for the internal Provider slug.
   The name-based catalog and `X-Provider-Name` path require both an active
   route and allowlist entry; the allowlist is empty by default. This is
   explicit registration and configuration, not dynamic plugin discovery.
   `X-Provider-Name` and `X-Route-Token` are mutually exclusive selectors.
   The legacy token path still requires the trusted Gateway secret and an
   active route mapping, and is not gated by the allowlist during the current
   compatibility period. The Gateway secret belongs only in a trusted backend,
   never in a browser or end-user application.

6. **Add hermetic tests.** Cover the facade's canonical success and error
   mapping, credential/no-leak behavior, exact Definition-to-handler parity,
   Discovery output, model override inheritance/replacement when applicable,
   and Runtime rejection of an operation not supported by a declared model.
   Mock upstream calls; do not require a live provider for normal CI.

7. **Run the service suite.** From `__gateway-service/`, run
   `python -m pytest`. The project configuration excludes tests marked
   `external_provider` by default; run those separately only when their
   credentials and external dependencies are intentionally available.

## Runtime and Discovery semantics

- A model with no `support` inherits Provider defaults for both dimensions.
  A model override may replace `operations`, `capabilities`, or both.
- For a declared model, `/v1/execute` checks the effective operation list;
  an unsupported operation returns an HTTP 200 execution-failure envelope
  with `unsupported_capability`. The Gateway currently uses `capabilities`
  as Discovery metadata; Runtime's model gate is the operation list.
- An unlisted model name preserves existing behavior and uses Provider-level
  operation defaults. The Adapter/upstream may still report
  `model_unavailable`.
- Model names are scoped to their Provider. Identical strings under different
  Providers remain separate `(provider, model)` choices; no alias or global
  model identifier is needed.
- `health_supported` does not trigger an independent upstream probe. The
  current `/v1/health` implementation reports `UNKNOWN`; ordinary execute
  results are the initial evidence of actual Provider connectivity.

## Adding a new Operation

An existing Provider can declare only operations already in the closed
`GatewayOperation` contract. A genuinely new global Operation requires an
intentional Gateway contract and implementation change before any Provider
can advertise it. That work includes its shared semantics and error/output
contract, Gateway operation type and dispatch/validation, contract and
Runtime/Discovery tests, service documentation, and at least one real Adapter
handler before it is advertised. An Operation's addition does **not** make it
supported by every Provider or Model. Keep the SDK generic: it accepts an
operation string and opaque JSON payload and does not need an operation enum
or provider-specific branch. Do not add a dynamic Operation Registry,
Capability Registry, or parallel SDK schemas as part of this work.

## Hard rules

- Provider code imports `gateway.contracts`, never `app`.
- One Gateway request produces one canonical response; internal upstream call
  count is not exposed.
- Gateway-level retries remain disabled in v1 for usage/billing integrity.
- A routine Provider addition uses existing contract fields; do not modify
  shared contract code or unrelated Provider packages for it. Contract-level
  changes, such as a new Operation or Capability key, require separate review,
  implementation, tests, and documentation.
- Keep `GW_PROVIDER_ALLOWLIST` and route mapping configuration explicit; do
  not infer registration from an SDK catalog or local package presence.
