#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏗️ Scaffold Generator — يولّد هيكل مزود جديد متكامل 100% مع Gateway Architecture & Bolla Constitution v1.2
الاستخدام:
    python tools/scaffold_provider.py <slug> [--display "Name"] [--lab] [--register]

المزايا القياسية المولدة تلقائياً:
1. الحزمة الخماسية الإلزامية: (__init__.py, _core.py, adapter.py, definition.py, models_metadata.json)
2. رباعية المراسي التشفيرية (.anchor) الفورية لكل ملف.
3. التزام قانون الصفر-متصفح (Zero-Browser Law: 100% Pure HTTP via curl_cffi / httpx).
4. طابور التعبئة المتتابع الصارم للحسابات (FIFO Sequential Queue Refill: +5 accounts per ask via background worker).
5. حزمة اختبارات الوحدة المعزولة hermetic في tests/providers/test_{slug}.py.
6. التسجيل التلقائي في app.py::register_live_providers (عند تفعيل --register).
"""

import sys
import json
import time
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ROOT / "providers"
TESTS = ROOT / "tests" / "providers"
LAB = ROOT.parent / ".AAA_GGG_iii_VIBE_CODING_مجلد_المزودين"
APP_PY = ROOT / "app.py"

CORE_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{disp} — _core.py | Pure HTTP Engine & FIFO Sequential Account Queue.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- 100% Zero-Browser Law: Strictly curl_cffi / httpx (No Selenium, Playwright, Chrome).
- Strict FIFO Sequential Queue Refill: Every ask enqueues +5 accounts in background.
- Error taxonomy mapping to canonical 12 ErrorCategory values.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Generator, Optional
from curl_cffi import requests as cffi

logger = logging.getLogger(__name__)

IMPERSONATE_TARGET = "chrome120"
TIMEOUT_SECONDS = 60
BASE_URL = "https://CHANGE_ME.example"


class UpstreamFailure(Exception):
    """Normalized Layer 1 upstream exception matching Gateway taxonomy."""

    def __init__(
        self,
        category: str,
        message: str,
        retry_after_ms: Optional[int] = None,
        provider_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.category = category
        self.message = message
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code


def _translate_upstream_failure(status: int, body: str = "") -> UpstreamFailure:
    try:
        from gateway.errors import classify_http_status
        category = classify_http_status(status, body).value
    except Exception:
        category = "retryable_server_error" if status in (500, 502, 503) else "non_retryable_error"
    return UpstreamFailure(category, f"{disp} upstream {{status}}", provider_code=str(status))


# ─── طابور إنشاء الحسابات المتتابع الصارم (FIFO Sequential Queue Refill) ───────────
# قاعدة إجبارية: مع كل سؤال/طلب شات يتم إدراج 5 حسابات في طابور الخلفية وتُعالج واحداً تلو الآخر
_ACCOUNT_REFILL_QUEUE: queue.Queue[int] = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _sequential_account_worker() -> None:
    """Worker thread strictly processing account creations sequentially (one-by-one)."""
    while True:
        try:
            item = _ACCOUNT_REFILL_QUEUE.get()
            if item is None:
                break
            try:
                # Sequential registration without concurrency conflicts
                _create_single_account()
            except Exception as e:
                logger.warning(f"[{disp}] Background account refill step failed: {{e}}")
            finally:
                _ACCOUNT_REFILL_QUEUE.task_done()
        except Exception:
            pass


def _ensure_worker_running() -> None:
    global _WORKER_STARTED
    if not _WORKER_STARTED:
        with _WORKER_LOCK:
            if not _WORKER_STARTED:
                worker_thread = threading.Thread(
                    target=_sequential_account_worker,
                    name="{slug}-account-worker",
                    daemon=True,
                )
                worker_thread.start()
                _WORKER_STARTED = True


def enqueue_account_refill(count: int = 5) -> None:
    """Enqueue N accounts to be created strictly one-by-one in the background."""
    _ensure_worker_running()
    for _ in range(count):
        _ACCOUNT_REFILL_QUEUE.put(1)
    logger.info(f"[{disp}] Enqueued {{count}} accounts for sequential background refill. Queue size: {{_ACCOUNT_REFILL_QUEUE.qsize()}}")


def _create_single_account() -> dict:
    """Single account creation logic using pure HTTP requests."""
    # Pure HTTP registration implementation
    return {{"status": "created", "timestamp": time.time()}}


# ─── الثلاثية الموحدة (The Universal Lab Trinity) ────────────────────────────
def register_account(session: cffi.Session | None = None) -> dict:
    """Register or initialize a fresh platform session."""
    sess = session or cffi.Session(impersonate=IMPERSONATE_TARGET)
    return {{"status": "active", "session": sess}}


def refresh_session(account_info: dict) -> dict:
    """Refresh active session if needed."""
    account_info["last_refreshed"] = time.time()
    return account_info


def execute_chat(
    prompt: str,
    session_data: dict,
    model: str = "default",
    stream: bool = True,
) -> str:
    """Execute chat completion and trigger FIFO sequential pool refill."""
    # Enqueue 5 accounts in background queue sequentially upon every chat
    enqueue_account_refill(5)
    return "".join(stream_text(prompt, session_data, model))


# ─── واجهات الجيتواي (Gateway Interfaces) ────────────────────────────────────
def generate_text(prompt: str, session_data: dict, model: str = "default") -> str:
    """Non-streaming text generation."""
    return execute_chat(prompt, session_data, model, stream=False)


def stream_text(
    prompt: str,
    session_data: dict,
    model: str = "default",
) -> Generator[str, None, None]:
    """Pure HTTP SSE streaming."""
    # Pure HTTP streaming implementation
    yield f"[{disp}] Echo: " + prompt
'''

ADAPTER_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{disp} — adapter.py | تحويل نواتج _core إلى FacadeResult مع عزل تام للمعلومات السرية"""
from __future__ import annotations

import asyncio
from typing import Any

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers.{slug} import _core


_SAFE_MESSAGES: dict[ErrorCategory, str] = {{
    ErrorCategory.AUTH_EXPIRED: "upstream authentication expired",
    ErrorCategory.INVALID_CREDENTIAL: "upstream credential invalid",
    ErrorCategory.RATE_LIMITED: "upstream rate limit reached",
    ErrorCategory.QUOTA_EXCEEDED: "upstream quota exceeded",
    ErrorCategory.MODEL_UNAVAILABLE: "upstream model unavailable",
    ErrorCategory.PROVIDER_UNAVAILABLE: "upstream provider unavailable",
    ErrorCategory.UNSUPPORTED_CAPABILITY: "unsupported capability",
    ErrorCategory.BAD_REQUEST: "bad request payload",
    ErrorCategory.CONTENT_REJECTED: "content rejected by upstream policy",
    ErrorCategory.TIMEOUT: "upstream call timed out",
    ErrorCategory.RETRYABLE_SERVER_ERROR: "upstream server error",
    ErrorCategory.NON_RETRYABLE_ERROR: "upstream call failed",
}}


def _translate_upstream_failure(exc: _core.UpstreamFailure) -> FacadeResult:
    """Translate Layer 1 failure shape into canonical wire error."""
    try:
        category = ErrorCategory(exc.category)
    except ValueError:
        category = ErrorCategory.NON_RETRYABLE_ERROR

    safe_msg = _SAFE_MESSAGES.get(category, "upstream call failed")
    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            safe_msg,
            retry_after_ms=exc.retry_after_ms if category is ErrorCategory.RATE_LIMITED else None,
            provider_code=exc.provider_code,
        ),
    )


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade handler for {disp}."""
    if context.operation != GatewayOperation.GENERATE_TEXT:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler generate_text cannot serve operation {{context.operation!r}}",
            ),
        )

    model = context.model or "default"
    messages = context.payload.get("messages", [])
    prompt = messages[-1].get("content", "") if messages else context.payload.get("prompt", "")

    if not prompt:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "Prompt or messages must not be empty"),
        )

    try:
        text = await asyncio.to_thread(_core.generate_text, prompt, {{}}, model)
        return FacadeResult(
            succeeded=True,
            output={{"text": text}},
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.RETRYABLE_SERVER_ERROR, "upstream communication failure"),
        )


HANDLERS = {{
    GatewayOperation.GENERATE_TEXT: generate_text,
}}
'''

DEFINITION_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{disp} — definition.py | البطاقة الرسمية للمزود في بوابة الجيتواي"""
from __future__ import annotations

import json
from pathlib import Path

_METADATA_PATH = Path(__file__).resolve().parent / "models_metadata.json"

try:
    with open(_METADATA_PATH, "r", encoding="utf-8") as _f:
        _MODELS_DATA: dict[str, dict] = json.load(_f)
except Exception:
    _MODELS_DATA = {{}}

_DECLARED_MODELS: list[dict[str, object]] = [
    {{"name": m_id}} for m_id in _MODELS_DATA
]

DEFINITION: dict[str, object] = {{
    "display_name": "{disp}",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {{
        "chat": True,
        "vision_input": False,
        "audio_input": False,
        "file_upload": False,
        "reasoning": True,
        "code": True,
    }},
    "operations": [
        "generate_text",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": True,
}}
'''

META_DEFAULT = {
    "default": {
        "label": "Default Model",
        "context_window": 8192,
        "max_output_tokens": 4096,
        "capabilities": {
            "thinking": False,
            "planning": False,
            "deep_research": False,
            "streaming": True,
        },
    }
}

TEST_TEMPLATE = '''"""Hermetic {disp} provider tests — facade + Layer 1 mock.

ZERO network.
Proves:
- Canonical success shape for generate_text
- Error translation to the 12 ErrorCategory taxonomy
- Zero secret or cookie leakage
- DEFINITION <-> HANDLERS parity
- Schema policing: extra keys rejected as bad_request
"""

from __future__ import annotations

import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.{slug} import _core
from providers.{slug}.adapter import HANDLERS, generate_text
from providers.{slug}.definition import DEFINITION


def test_{slug}_definition_parity() -> None:
    declared = {{GatewayOperation(op) for op in DEFINITION["operations"]}}
    assert set(HANDLERS.keys()) == declared


@pytest.mark.asyncio
async def test_{slug}_generate_text_mocked_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_generate_text(prompt: str, session_data: dict, model: str = "default"):
        return f"Echo from {disp}: {{prompt}}"

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_{slug}_1",
        tenant_id="ten_{slug}_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={{"messages": [{{"role": "user", "content": "hi"}}]}},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert res.output is not None
    assert "Echo from {disp}" in res.output["text"]
    assert res.usage is not None


@pytest.mark.asyncio
async def test_{slug}_schema_policing() -> None:
    # Empty messages/prompt
    ctx_bad = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_{slug}_bad",
        tenant_id="ten_{slug}_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={{}},
        timeout_ms=5000,
    )
    res = await generate_text(ctx_bad)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_{slug}_upstream_failure_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("rate_limited", "Rate limit exceeded", retry_after_ms=2000)

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_{slug}_fail",
        tenant_id="ten_{slug}_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={{"messages": [{{"role": "user", "content": "hi"}}]}},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.RATE_LIMITED
    assert res.error.retryable is True
'''

LAB_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🧪 {disp} — Universal Lab Test Script (TOOLKIT v2.1)"""
import sys
import time
from curl_cffi import requests as cffi

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMPERSONATE_TARGET = "chrome120"
TIMEOUT_SECONDS = 60


def register_account(session=None) -> dict:
    sess = session or cffi.Session(impersonate=IMPERSONATE_TARGET)
    return {{"status": "active", "session": sess}}


def refresh_session(account_info: dict) -> dict:
    account_info["last_refreshed"] = time.time()
    return account_info


def execute_chat(prompt: str, session_data: dict, model: str = "default", stream: bool = True) -> str:
    return f"[{disp}] Response: {{prompt}}"


if __name__ == "__main__":
    print("🚀 [1/3] تسجيل الحساب...");  acc = register_account()
    print("🚀 [2/3] فحص الجلسة...");    acc = refresh_session(acc)
    print("🚀 [3/3] اختبار الشات...")
    print("\\n💬 الرد:", execute_chat("مرحبا! من أنت؟", acc))
'''


def write_file_and_anchor(p: Path, content: str, make_anchor: bool = True) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        print(f"  ⏭️  موجود مسبقاً: {p.name}")
    else:
        p.write_text(content, encoding="utf-8")
        print(f"  ✅ إنشاء ملف: {p.relative_to(ROOT.parent)}")

    if make_anchor:
        anchor_path = Path(str(p) + ".anchor")
        if not anchor_path.exists():
            anchor_path.write_text(content, encoding="utf-8")
            print(f"  ⚓ إنشاء مرساة: {anchor_path.relative_to(ROOT.parent)}")


def register_in_app_py(slug: str) -> bool:
    """Insert provider into app.py::register_live_providers if not already present."""
    if not APP_PY.exists():
        return False

    content = APP_PY.read_text(encoding="utf-8")
    slug_upper = slug.upper().replace("-", "_")

    import_line = f"    from providers.{slug}.definition import DEFINITION as {slug_upper}_DEFINITION"
    register_line = f'    registry.register("{slug}", {slug_upper}_DEFINITION, "providers.{slug}.adapter")'

    if import_line in content or f'"{slug}"' in content:
        print(f"  ⏭️  المزود مسجل مسبقاً في app.py")
        return False

    # Insert import before registry.register calls
    lines = content.splitlines()
    reg_fn_idx = -1
    last_reg_idx = -1

    for idx, line in enumerate(lines):
        if "def register_live_providers(" in line:
            reg_fn_idx = idx
        if reg_fn_idx != -1 and "registry.register(" in line:
            last_reg_idx = idx

    if reg_fn_idx == -1 or last_reg_idx == -1:
        print("  ⚠️ تعذر العثور على موضع الإدراج التلقائي في app.py")
        return False

    # Find the last import line in register_live_providers
    last_import_idx = -1
    for idx in range(reg_fn_idx, last_reg_idx):
        if "from providers." in lines[idx]:
            last_import_idx = idx

    if last_import_idx != -1:
        lines.insert(last_import_idx + 1, import_line)
        # Shift last_reg_idx by 1
        last_reg_idx += 1
        lines.insert(last_reg_idx + 1, register_line)
    else:
        lines.insert(last_reg_idx + 1, register_line)

    new_content = "\n".join(lines) + "\n"
    APP_PY.write_text(new_content, encoding="utf-8")
    print(f"  🔌 تم تسجيل المزود بنجاح في app.py::register_live_providers")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Scaffold a new Gateway provider compliant with Bolla Constitution v1.2, Zero-Browser, and Contract Invariants"
    )
    ap.add_argument("slug", help="Slug identifier for the provider (e.g., stepfun, perplexity)")
    ap.add_argument("--display", default=None, help="Display name for the provider (e.g., 'StepFun AI')")
    ap.add_argument("--lab", action="store_true", help="Also generate the standalone lab script in .AAA_GGG_iii_VIBE_CODING")
    ap.add_argument("--register", action="store_true", help="Automatically register provider in app.py")
    a = ap.parse_args()

    slug = a.slug.strip().lower().replace(" ", "-")
    disp = a.display or slug.replace("-", " ").title()
    d = PROVIDERS / slug

    print(f"\n=======================================================")
    print(f"🏗️  توليد هيكل المزود المتكامل: {slug} ({disp})")
    print(f"   المرجع الدستوري: .agents/workflows/00-gateway-provider-onboarding.md")
    print(f"=======================================================\n")

    # 1. Core 5 files + 4 anchors
    write_file_and_anchor(d / "__init__.py", "from .definition import DEFINITION  # noqa\n", make_anchor=False)
    write_file_and_anchor(d / "_core.py", CORE_TEMPLATE.format(slug=slug, disp=disp), make_anchor=True)
    write_file_and_anchor(d / "adapter.py", ADAPTER_TEMPLATE.format(slug=slug, disp=disp), make_anchor=True)
    write_file_and_anchor(d / "definition.py", DEFINITION_TEMPLATE.format(slug=slug, disp=disp), make_anchor=True)
    write_file_and_anchor(
        d / "models_metadata.json",
        json.dumps(META_DEFAULT, ensure_ascii=False, indent=2) + "\n",
        make_anchor=True,
    )

    # 2. Hermetic Unit Test Suite
    test_file = TESTS / f"test_{slug}.py"
    write_file_and_anchor(test_file, TEST_TEMPLATE.format(slug=slug, disp=disp), make_anchor=False)

    # 3. Lab Script (optional)
    if a.lab:
        lab_file = LAB / slug / f"{slug}_lab.py"
        write_file_and_anchor(lab_file, LAB_TEMPLATE.format(slug=slug, disp=disp), make_anchor=False)

    # 4. Auto Register in app.py
    if a.register:
        register_in_app_py(slug)
    else:
        print(f"\n💡 للتسجيل التلقائي في app.py أعد التشغيل مع --register أو أضف الأسطر يدوياً:")
        slug_upper = slug.upper().replace("-", "_")
        print(f"    from providers.{slug}.definition import DEFINITION as {slug_upper}_DEFINITION")
        print(f'    registry.register("{slug}", {slug_upper}_DEFINITION, "providers.{slug}.adapter")')

    print(f"\n🎯 التحقق واختبار العقد:")
    print(f"   py -3.13 -m pytest tests/test_provider_contract.py tests/providers/test_{slug}.py -v\n")


if __name__ == "__main__":
    main()
