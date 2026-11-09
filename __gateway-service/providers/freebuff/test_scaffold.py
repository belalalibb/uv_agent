#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification & Pre-Lab Test Scaffold for FREEBUFF
Conforms to Bolla Constitution v1.2 (Law #3 Sandboxing & Verifiable Execution).
"""

import sys
import unittest
from pathlib import Path

# Add gateway root to sys.path
GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from providers.freebuff import DEFINITION, HANDLERS, _core


class TestFreebuffScaffold(unittest.TestCase):
    def test_01_definition_integrity(self):
        self.assertEqual(DEFINITION.name, "freebuff")
        self.assertIn("generate_text", DEFINITION.operations)
        self.assertTrue(len(DEFINITION.declared_models) > 0)
        print(f"[+] Verified {len(DEFINITION.declared_models)} declared models for freebuff")

    def test_02_handlers_registered(self):
        self.assertIn("generate_text", HANDLERS)
        self.assertIn("analyze_vision", HANDLERS)
        print("[+] Verified Gateway Handlers registration")

    def test_03_non_vision_guard(self):
        # Verify non-vision guard rejects image on text model
        text_models = [m for m, meta in _core.MODELS_METADATA.items() if not meta.get("vision", False)]
        if text_models:
            import asyncio
            m = text_models[0]
            with self.assertRaises(ValueError):
                asyncio.run(HANDLERS["analyze_vision"]({"model": m, "images": ["data:image/png;base64,..."]}, {}))
            print(f"[+] Verified Non-Vision Fast Guard on {m}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
