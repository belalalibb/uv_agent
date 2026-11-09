"""Syntx AI Provider Package — Gateway v1 Integration.

Three-Layer Architecture:
    Layer 1 (Internal Engine) -> _core.py (Autonomous 3-function capsule: register, refresh, ask)
    Layer 2 (Facade Adapter)  -> adapter.py (Canonical ProviderContext -> FacadeResult)
    Layer 3 (Fixed Contracts) -> gateway.contracts (Wire models, 12 error categories)

Credential mode: platform (internal account pool management).
Operations supported: generate_text, analyze_vision.
Non-vision model protection: enforced at Layer 2 before touching upstream network.
"""

from __future__ import annotations

from providers.syntx.adapter import HANDLERS
from providers.syntx.definition import DEFINITION

__all__ = ["DEFINITION", "HANDLERS"]
