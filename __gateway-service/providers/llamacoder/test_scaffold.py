#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification & Pre-Lab Test Scaffold for LlamaCoder Together AI.

Conforms to Bolla Constitution v1.2 (Law #3 Sandboxing & Verifiable Execution).
"""

import sys
import unittest
from pathlib import Path

# Add gateway root to sys.path
GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.contracts import ProviderDefinition
from providers.llamacoder import DEFINITION, HANDLERS, _core


class TestLlamaCoderScaffold(unittest.TestCase):
    def test_01_definition_integrity(self):
        parsed = ProviderDefinition.model_validate(DEFINITION)
        self.assertEqual(parsed.display_name, "LlamaCoder Together AI")
        self.assertIn("generate_text", [op.value for op in parsed.operations])
        self.assertIn("analyze_vision", [op.value for op in parsed.operations])
        self.assertTrue(len(parsed.models) >= 8)
        print(f"[+] Verified {len(parsed.models)} declared models for llamacoder")

    def test_02_handlers_registered(self):
        for op in DEFINITION["operations"]:
            from gateway.contracts import GatewayOperation
            op_enum = GatewayOperation(op)
            self.assertIn(op_enum, HANDLERS)
        print("[+] Verified Gateway Handlers registration")

    def test_03_model_resolution(self):
        m1 = _core.resolve_model_name("deepseek-v4.1")
        self.assertEqual(m1, "deepseek-ai/DeepSeek-V4.1-Flash")
        m2 = _core.resolve_model_name("glm-5.3-flash")
        self.assertEqual(m2, "zai-org/GLM-5.3-Flash")
        print("[+] Verified canonical model resolution")


if __name__ == "__main__":
    unittest.main(verbosity=2)
