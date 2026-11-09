"""Chat orchestration and multi-model execution tests for Syntx Layer 1 & 2."""

import json
from uuid import uuid4

import httpx
import pytest

from gateway.contracts import GatewayOperation, ProviderContext, CredentialMode
from providers.syntx import _core
from providers.syntx.adapter import generate_text

TEST_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-5",
    "gpt-5.6-terra",
    "grok-4.6",
]


@pytest.fixture(autouse=True)
def setup_chat(tmp_path, monkeypatch):
    test_accounts_file = tmp_path / "accounts_syntx.json"
    initial_accounts = [
        {
            "email": "chat_tester@example.com",
            "token": "token-syntx-chat-999",
            "chat_uuid": "chat-uuid-session-1234",
            "provider": "tempmailclub",
            "status": "active",
            "created_at": "2026-09-12 12:00:00",
        }
    ]
    test_accounts_file.write_text(json.dumps(initial_accounts), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_accounts_file))
    yield test_accounts_file
    _core.set_transport_override(None)


@pytest.mark.parametrize("model", TEST_MODELS)
async def test_models_payload_structure(model):
    """Verify each model correctly constructs upstream payload and ai_name."""
    calls = []
    call_counts = {"messages": 0}

    def mock_responder(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        calls.append(request)
        if request.url.path.endswith("/chats"):
            return httpx.Response(201, json={"uuid": "chat-uuid-session-1234"})
        if "/llm/generate" in url_str:
            data = json.loads(request.content.decode("utf-8"))
            assert data["model"] == model
            assert data["chat_uuid"] == "chat-uuid-session-1234"
            assert data["text"] == "hello"
            assert data["thinking"] is True
            assert data["plan"] is True
            assert data["deep_research"] is True
            expected_ai_name = _core.get_model_ai_name(model)
            assert request.url.params.get("ai_name") == expected_ai_name
            return httpx.Response(200, json={"job_id": "test-job-99"})
        if "/messages" in url_str:
            call_counts["messages"] += 1
            if call_counts["messages"] == 1:
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "id": 555,
                            "author_id": -1,
                            "usage": {"input_tokens": 10, "output_tokens": 20},
                            "message_object": [
                                {"object_type": "text", "object_text": f"Reply from {model}", "completed": True}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model=model,
        request_id="test-req",
        tenant_id="test-tenant",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )
    result = await generate_text(ctx)
    assert result.succeeded
    assert result.output["text"] == f"Reply from {model}"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20


async def test_multi_turn_conversation_formatting():
    """Verify multi-turn messages are correctly formatted into conversation history."""
    captured_texts = []
    call_counts = {"messages": 0}

    def mock_responder(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/llm/generate" in url_str:
            data = json.loads(request.content.decode("utf-8"))
            captured_texts.append(data["text"])
            return httpx.Response(200, json={"job_id": "test-job"})
        if "/messages" in url_str:
            call_counts["messages"] += 1
            if call_counts["messages"] == 1:
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "id": 777,
                            "author_id": -1,
                            "message_object": [
                                {"object_type": "text", "object_text": "Understood.", "completed": True}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="claude-opus-4-8",
        request_id="test-req",
        tenant_id="test-tenant",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={
            "messages": [
                {"role": "system", "content": "System prompt instructions"},
                {"role": "user", "content": "First turn"},
                {"role": "assistant", "content": "Assistant turn"},
                {"role": "user", "content": "Final question"},
            ]
        },
    )
    result = await generate_text(ctx)
    assert result.succeeded
    assert len(captured_texts) == 1
    assert "Previous conversation:\nsystem: System prompt instructions\n\nuser: First turn\n\nassistant: Assistant turn" in captured_texts[0]
    assert "Current request:\nuser: Final question" in captured_texts[0]
