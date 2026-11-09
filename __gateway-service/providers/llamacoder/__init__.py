"""LlamaCoder Together AI Provider Package for Gateway v1.

Autonomous guest/platform-mode provider with zero credentials/cookies,
supporting 1M token context models, live streaming, code attachments, and screenshot vision analysis.
"""

from __future__ import annotations

from providers.llamacoder.adapter import HANDLERS
from providers.llamacoder.definition import DEFINITION

__all__ = ["DEFINITION", "HANDLERS"]
