# 🌐 Gateway Service — Remote Provider Gateway (Data Plane)

> **Authority:** ADR-0008 & Bolla Constitution v1.2  
> **Status:** Production-Ready Multi-Provider Architecture (Hermetic & Live)  
> **Supported Operations:** `generate_text`, `analyze_vision`, `transcribe_audio`, `image_generation`, etc.

---

## 🏗️ Architecture & Philosophy

The **Gateway Service** acts as the high-performance, resilient data plane orchestrating external AI providers without browser bloat (Zero-Browser philosophy). It exposes a unified, hermetic facade to clients and upstream consumers while enforcing strict contract boundaries, automated model fallbacks, credential isolation, and 12-category wire-safe error translations.

```
                      ┌──────────────────────────────────────────────┐
                      │            Client / Consumer                 │
                      └──────────────────────┬───────────────────────┘
                                             │ HTTP (POST /v1/execute)
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Gateway Core Routing & Protection                                                          │
│ - Route Registry & Hot-Reload (X-Gateway-Secret, Token -> Slug translation)                │
│ - Provider Registry (Eager Definition Validation & Lazy Facade Loading)                   │
│ - Context Builder & Credential Mode Enforcement (user_key vs platform)                     │
│ - Safe Error Sanitizer (Maps exceptions to 12 closed ErrorCategories; Zero Secret Leak)    │
└────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                             │ ProviderContext
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Providers (Three-Layer Mandatory Model)                                                    │
│                                                                                            │
│   Layer 3: DEFINITION (definition.py)                                                      │
│     * Closed capability declarations & dynamic model registry                              │
│     * Operations catalog matching HANDLERS strictly                                        │
│                                                                                            │
│   Layer 2: FACADE ADAPTER (adapter.py)                                                     │
│     * Schema validation (payload & options)                                                │
│     * Invokes Layer 1 engine                                                               │
│     * Wraps result into FacadeResult(succeeded, output, usage, error)                      │
│                                                                                            │
│   Layer 1: ENGINE INTERNALS (_core.py)                                                     │
│     * Zero-browser HTTP / SSE streaming                                                    │
│     * Ephemeral device identities & anonymous auth rotation                                │
│     * S3 media uploads, Whisper transcriptions, and upstream recovery                      │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Layout

```
__gateway-service/
├── app.py                      # FastAPI entrypoint (build_app + uvicorn); zero business logic
├── pyproject.toml              # Project dependencies and pytest configuration
├── test_live_overchat.py       # Live E2E verification test for Overchat (Text, Vision, Audio)
├── gateway/                    # Gateway Core Engine
│   ├── contracts.py            # ★ Layer 3: Canonical contract types (Single Source of Truth)
│   ├── config.py               # Central environment configuration (fails loud on misconfig)
│   ├── auth.py                 # Secret authentication & dual-accept token rotation
│   ├── routes.py               # REST API surface (POST /v1/execute, /describe, /models)
│   ├── route_registry.py       # Route token registry with hot-reload and revoke capabilities
│   ├── provider_registry.py    # Eager DEFINITION validation and lazy facade import
│   ├── context.py              # Canonical ProviderContext builder
│   ├── credentials.py          # Credential mode enforcement (platform vs user_key)
│   ├── errors.py               # 12-category error taxonomy & sanitized error factories
│   ├── discovery.py            # Route discovery projections without internal slug leakage
│   └── observability.py        # Structured logging with strict allowed-field whitelist
├── providers/                  # Active & Reference Providers
│   ├── overchat/               # ★ Overchat AI Multi-Model & Multimodal Provider
│   │   ├── _core.py            # Layer 1: OkHttp emulation, SSE, S3 upload, Whisper STT
│   │   ├── adapter.py          # Layer 2: Facade translating ProviderContext <-> FacadeResult
│   │   ├── definition.py       # Layer 3: Closed capabilities, 8 free models, 3 operations
│   │   ├── models_metadata.json# Dynamic catalog of 8 verified free models
│   │   ├── README.md           # Internal provider technical documentation
│   │   └── *.anchor            # Cryptographic SHA anchors satisfying Gateway Invariant #6
│   ├── tinyfish/               # ★ TinyFish AI Autonomous Web Agent & Vision Provider
│   │   ├── _core.py            # Layer 1: Pure HTTP, FileLock pool, Clerk signup via Gmail aliases
│   │   ├── adapter.py          # Layer 2: Facade translating ProviderContext <-> FacadeResult
│   │   ├── definition.py       # Layer 3: Closed capabilities (chat, reasoning, browser, vision)
│   │   ├── models_metadata.json# Dynamic catalog (mako, gemini-2.5-flash, browser-agent)
│   │   ├── accounts_tinyfish.json # Active credential pool
│   │   ├── README.md           # Internal provider technical documentation
│   │   └── *.anchor            # Cryptographic SHA anchors
│   ├── groq/                   # Groq ultra-fast LPU provider
│   ├── deepai/                 # DeepAI provider
│   ├── llamacoder/             # Together AI / LlamaCoder coding engine
│   ├── ivycraft/               # Ivycraft provider
│   ├── freebuff/               # Freebuff provider
│   ├── notegpt/                # NoteGPT AI provider
│   ├── parallel/               # Parallel AI provider
│   ├── upstage/                # Upstage AI provider
│   ├── voyage/                 # Voyage AI provider
│   ├── youmind/                # YouMind AI provider
│   ├── runpod_console/         # RunPod Console Assistant provider
│   ├── _example/               # Hermetic reference provider vs mock
│   └── _template/              # Standard facade boilerplate for all 8 operations
├── tests/                      # Hermetic Test Suite (Zero Network)
│   ├── providers/              # Provider-specific unit and parity tests
│   │   └── test_overchat.py    # Overchat facade, validation, fallback, and multimodal tests
│   ├── test_provider_contract.py# Contract parity verification across all registered providers
│   └── ...                     # Core gateway unit and integration tests
└── docs/                       # Architectural Governance
    ├── CONTRACT.md             # Canonical wire specification & invariants
    └── ONBOARDING.md           # Step-by-step guide for onboarding new providers
```

---

## 🌟 Overchat AI Provider Integration

The **Overchat AI** provider has been upgraded to a flagship multimodal provider supporting:
- **8 Verified Free Models:**
  1. `gpt-6-luna` (Flagship reasoning & vision)
  2. `gpt-5.6-luna` (Deep reasoning & intelligence)
  3. `gemini-3.8-flash` (Google Gemini 3.8 Flash high-speed multimodal)
  4. `claude-4.5-haiku` (Anthropic Claude 4.5 Haiku)
  5. `deepseek-v3.2` (DeepSeek v3.2 Non-Thinking code engine)
  6. `gpt-5-mini` (OpenAI GPT-5 Mini)
  7. `gpt-5-nano` (Overchat instant chat engine)
  8. `gpt-4.1-nano` (OpenAI GPT-4.1 Nano text engine)
- **Multimodal Capabilities:**
  * **Text Generation & Reasoning (`generate_text`)**: Full streaming SSE with automatic model fallback and live web search.
  * **Computer Vision (`analyze_vision`)**: Direct S3 media attachment upload and visual inspection with GPT-6 Luna.
  * **Speech-to-Text Transcription (`transcribe_audio`)**: High-accuracy Arabic & multilingual Whisper audio transcription.

---

## 🌟 TinyFish AI Provider Integration (Provider #14)

The **TinyFish AI** provider integrates autonomous web agents, live reasoning, and vision:
- **3 Models:**
  1. `mako` (TinyFish flagship autonomous web navigation & extraction agent)
  2. `gemini-2.5-flash` (Google Gemini 2.5 Flash multimodal reasoning engine)
  3. `browser-agent` (Cloud browser agent for complex multi-step tasks)
- **Supported Operations:**
  * **Text Generation & Web Reasoning (`generate_text`)**: Autonomous search and answer synthesis.
  * **Computer Vision (`analyze_vision`)**: Deep visual inspection of images and web page assets.
- **Auto-Refill Pool (Zero-Browser):**
  * Automated account factory using Clerk OTP and temporary Gmail aliases from `__دومينات مؤقته`.
  * Pure HTTP requests only — zero Playwright/Selenium overhead.

---

## 🧪 Testing & Quality Assurance

### 1. Hermetic Unit Tests (Zero External Network):
All provider facades, schemas, error mappings, and contracts are verified in complete network isolation:
```bash
# Test Overchat provider specifically:
pytest tests/providers/test_overchat.py -v

# Test Gateway Provider Contract compliance:
pytest tests/test_provider_contract.py -k overchat -v

# Run entire hermetic test suite:
pytest tests/ -v
```

### 2. Live Verification Script (Real End-to-End Inference):
Verify real-time live capabilities (Text, Vision, Audio) against actual upstream APIs:
```bash
python test_live_overchat.py
```
Outputs:
- `generate_text` (GPT-6 Luna & Gemini 3.8 Flash) -> Verified
- `analyze_vision` (Image Base64 -> S3 -> Luna Vision) -> Verified
- `transcribe_audio` (Audio Base64 -> Whisper Transcription) -> Verified

---

## 🔒 Security & Invariants Compliance

- **Invariant #1 (Hermetic Boundary):** Mock transports supported in all engines for 100% offline CI testing.
- **Invariant #2 (Zero Leakage):** No raw upstream errors, auth headers, internal tokens, or device IDs are exposed.
- **Invariant #5 (Safe Errors):** Only 12 canonical `ErrorCategory` values are returned on wire.
- **Invariant #6 (Anchors):** Cryptographic `.anchor` files ensure unapproved modifications to contracts are detected immediately.
