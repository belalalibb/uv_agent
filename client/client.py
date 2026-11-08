"""Core Gateway Client — Typed, Async & Sync, High-Availability."""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any, Sequence

import httpx

from .config import GatewayConfig
from .exceptions import (
    GatewayError,
    RouteNotFoundError,
    create_gateway_error,
)
from .models import (
    AudioOutput,
    ChatMessage,
    EmbeddingsOutput,
    ExecutionResult,
    GatewayOperation,
    HealthResponse,
    ImageOutput,
    ModelInfo,
    ModelsListResponse,
    ModerationOutput,
    ProviderManifest,
    RerankOutput,
    SpeechOutput,
    TextOutput,
    UsageInfo,
    VisionOutput,
)
from .routes import SmartRouter


class GatewayClient:
    """Async Client for communicating with the AI Gateway Service."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        router: SmartRouter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or GatewayConfig.from_env()
        self.router = router or SmartRouter(self.config.route_tokens)
        self._custom_http = http_client is not None
        self._http = http_client or httpx.AsyncClient(timeout=self.config.default_timeout)

    async def __aenter__(self) -> GatewayClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if not self._custom_http:
            await self._http.aclose()

    # ----------------------------------------------------------------------- #
    # Header Construction & Resolution                                        #
    # ----------------------------------------------------------------------- #

    def _build_headers(self, route_token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Gateway-Secret": self.config.gateway_secret,
            "X-Gateway-Secret-Version": str(self.config.secret_version),
            "Content-Type": "application/json",
        }
        if route_token:
            resolved = self.router.resolve_token(route_token)
            headers["X-Route-Token"] = resolved
        return headers

    def _resolve_tokens_list(self, route_token_or_group: str) -> list[str]:
        group = self.router.get_group(route_token_or_group)
        if group:
            return group.all_tokens
        return [self.router.resolve_token(route_token_or_group)]

    # ----------------------------------------------------------------------- #
    # Discovery Endpoints                                                     #
    # ----------------------------------------------------------------------- #

    async def healthz(self) -> bool:
        """Check gateway process liveness (no authentication needed)."""
        url = f"{self.config.base_url}/healthz"
        resp = await self._http.get(url)
        return resp.status_code == 200 and resp.json().get("status") == "ok"

    async def describe(self, route_token: str) -> ProviderManifest:
        """Retrieve manifest projection and capabilities for a specific provider."""
        url = f"{self.config.base_url}/v1/describe"
        headers = self._build_headers(route_token)
        resp = await self._http.get(url, headers=headers)
        self._check_transport_status(resp)
        return ProviderManifest.model_validate(resp.json())

    async def list_models(self, route_token: str) -> list[ModelInfo]:
        """Fetch the declared models for a specific provider."""
        url = f"{self.config.base_url}/v1/models"
        headers = self._build_headers(route_token)
        resp = await self._http.get(url, headers=headers)
        self._check_transport_status(resp)
        data = ModelsListResponse.model_validate(resp.json())
        return data.models

    async def check_health(self, route_token: str) -> HealthResponse:
        """Inspect provider health status."""
        url = f"{self.config.base_url}/v1/health"
        headers = self._build_headers(route_token)
        resp = await self._http.get(url, headers=headers)
        self._check_transport_status(resp)
        return HealthResponse.model_validate(resp.json())

    # ----------------------------------------------------------------------- #
    # Low-level Execution Engine with Fallback Support                        #
    # ----------------------------------------------------------------------- #

    async def execute(
        self,
        route_token: str,
        operation: GatewayOperation | str,
        model: str,
        payload: dict[str, Any],
        tenant_id: str | None = None,
        request_id: str | None = None,
        credential_mode: str = "platform",
        credential_value: str | None = None,
        timeout_ms: int = 60000,
    ) -> ExecutionResult[Any]:
        """Send a canonical RequestEnvelope to the Gateway with automatic failover."""
        tokens = self._resolve_tokens_list(route_token)
        last_error: GatewayError | None = None

        for token in tokens:
            try:
                return await self._execute_single(
                    route_token=token,
                    operation=operation,
                    model=model,
                    payload=payload,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    credential_mode=credential_mode,
                    credential_value=credential_value,
                    timeout_ms=timeout_ms,
                )
            except GatewayError as exc:
                last_error = exc
                # If error is retryable and we have more fallback providers in group, continue
                if exc.retryable and len(tokens) > 1:
                    continue
                # If non-retryable but provider is unavailable, fallback may also help
                if exc.category == "provider_unavailable" and len(tokens) > 1:
                    continue
                raise exc

        if last_error:
            raise last_error
        raise GatewayError(category="provider_unavailable", message="No available routes in group")

    async def _execute_single(
        self,
        route_token: str,
        operation: GatewayOperation | str,
        model: str,
        payload: dict[str, Any],
        tenant_id: str | None = None,
        request_id: str | None = None,
        credential_mode: str = "platform",
        credential_value: str | None = None,
        timeout_ms: int = 60000,
    ) -> ExecutionResult[Any]:
        url = f"{self.config.base_url}/v1/execute"
        headers = self._build_headers(route_token)

        envelope: dict[str, Any] = {
            "operation": str(operation),
            "model": model,
            "request_id": request_id or f"req_{uuid.uuid4().hex[:12]}",
            "tenant_id": tenant_id or self.config.default_tenant_id,
            "credential": {
                "mode": credential_mode,
            },
            "payload": payload,
            "timeout_ms": timeout_ms,
        }
        if credential_value:
            envelope["credential"]["value"] = credential_value

        http_timeout = max(5.0, (timeout_ms / 1000.0) + 5.0)
        resp = await self._http.post(url, headers=headers, json=envelope, timeout=http_timeout)
        self._check_transport_status(resp)

        body = resp.json()
        if not body.get("succeeded", False):
            raw_err = body.get("error") or {}
            raise create_gateway_error(
                category=raw_err.get("category", "non_retryable_error"),
                message=raw_err.get("message", "upstream call failed"),
                retryable=raw_err.get("retryable", False),
                retry_after_ms=raw_err.get("retry_after_ms"),
                provider_code=raw_err.get("provider_code"),
                http_status=resp.status_code,
                raw_error=raw_err,
            )

        raw_usage = body.get("usage") or {}
        usage = UsageInfo(
            input_tokens=raw_usage.get("input_tokens"),
            output_tokens=raw_usage.get("output_tokens"),
            units=raw_usage.get("units", 1),
        )

        return ExecutionResult(
            succeeded=True,
            output=body.get("output"),
            usage=usage,
            latency_ms=body.get("latency_ms", 0),
            raw_response=body,
        )

    def _check_transport_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 404:
            raise RouteNotFoundError(
                category="provider_unavailable",
                message="Unknown, revoked, or disabled route token",
                http_status=404,
            )
        if resp.status_code == 401:
            body = resp.json() if resp.text else {}
            err = body.get("error", {})
            raise create_gateway_error(
                category=err.get("category", "invalid_credential"),
                message=err.get("message", "Gateway authentication failed"),
                retryable=err.get("retryable", False),
                http_status=401,
                raw_error=err,
            )
        if resp.status_code == 400:
            body = resp.json() if resp.text else {}
            err = body.get("error", {})
            raise create_gateway_error(
                category=err.get("category", "bad_request"),
                message=err.get("message", "Malformed request envelope"),
                retryable=False,
                http_status=400,
                raw_error=err,
            )
        if resp.status_code >= 500:
            body = resp.json() if resp.text else {}
            err = body.get("error", {})
            raise create_gateway_error(
                category=err.get("category", "retryable_server_error"),
                message=err.get("message", "Gateway internal fault"),
                retryable=True,
                http_status=resp.status_code,
                raw_error=err,
            )

    # ----------------------------------------------------------------------- #
    # High-level Typed Operations                                             #
    # ----------------------------------------------------------------------- #

    async def generate_text(
        self,
        route_token: str,
        model: str,
        messages: Sequence[ChatMessage | dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_ms: int = 60000,
        **kwargs: Any,
    ) -> ExecutionResult[TextOutput]:
        """Generate text from chat messages."""
        formatted_messages = [
            m.model_dump() if isinstance(m, ChatMessage) else m for m in messages
        ]
        payload: dict[str, Any] = {"messages": formatted_messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.GENERATE_TEXT,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = TextOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def generate_image(
        self,
        route_token: str,
        model: str,
        prompt: str,
        size: str | None = None,
        count: int = 1,
        timeout_ms: int = 90000,
        **kwargs: Any,
    ) -> ExecutionResult[ImageOutput]:
        """Generate an image from a text prompt."""
        payload: dict[str, Any] = {"prompt": prompt, "count": count}
        if size:
            payload["size"] = size

        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.GENERATE_IMAGE,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = ImageOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def transcribe_audio(
        self,
        route_token: str,
        model: str,
        audio: bytes | str,
        audio_format: str = "wav",
        language: str | None = None,
        timeout_ms: int = 60000,
        **kwargs: Any,
    ) -> ExecutionResult[AudioOutput]:
        """Transcribe speech/audio to text."""
        if isinstance(audio, bytes):
            audio_b64 = base64.b64encode(audio).decode("utf-8")
        else:
            audio_b64 = audio

        payload: dict[str, Any] = {
            "audio_b64": audio_b64,
            "audio_format": audio_format,
        }
        if language:
            payload["language"] = language

        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.TRANSCRIBE_AUDIO,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = AudioOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def synthesize_speech(
        self,
        route_token: str,
        model: str,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
        timeout_ms: int = 60000,
        **kwargs: Any,
    ) -> ExecutionResult[SpeechOutput]:
        """Synthesize text to speech audio."""
        payload: dict[str, Any] = {"text": text, "audio_format": audio_format}
        if voice:
            payload["voice"] = voice

        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.SYNTHESIZE_SPEECH,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = SpeechOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def create_embeddings(
        self,
        route_token: str,
        model: str,
        inputs: Sequence[str],
        timeout_ms: int = 30000,
        **kwargs: Any,
    ) -> ExecutionResult[EmbeddingsOutput]:
        """Generate vector embeddings for input strings."""
        payload = {"inputs": list(inputs)}
        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.CREATE_EMBEDDINGS,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = EmbeddingsOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def rerank_documents(
        self,
        route_token: str,
        model: str,
        query: str,
        documents: Sequence[str],
        top_n: int | None = None,
        timeout_ms: int = 30000,
        **kwargs: Any,
    ) -> ExecutionResult[RerankOutput]:
        """Rerank candidate documents based on query relevance."""
        payload: dict[str, Any] = {"query": query, "documents": list(documents)}
        if top_n is not None:
            payload["top_n"] = top_n

        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.RERANK_DOCUMENTS,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = RerankOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def moderate_content(
        self,
        route_token: str,
        model: str,
        content: str,
        timeout_ms: int = 15000,
        **kwargs: Any,
    ) -> ExecutionResult[ModerationOutput]:
        """Evaluate text for safety and policy moderation."""
        payload = {"content": content}
        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.MODERATE_CONTENT,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = ModerationOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    async def analyze_vision(
        self,
        route_token: str,
        model: str,
        image: bytes | str,
        instruction: str,
        image_format: str = "png",
        timeout_ms: int = 60000,
        **kwargs: Any,
    ) -> ExecutionResult[VisionOutput]:
        """Analyze an image with multimodal models."""
        if isinstance(image, bytes):
            image_b64 = base64.b64encode(image).decode("utf-8")
        else:
            image_b64 = image

        payload = {
            "image_b64": image_b64,
            "image_format": image_format,
            "instruction": instruction,
        }
        result = await self.execute(
            route_token=route_token,
            operation=GatewayOperation.ANALYZE_VISION,
            model=model,
            payload=payload,
            timeout_ms=timeout_ms,
            **kwargs,
        )
        typed_output = VisionOutput.model_validate(result.output or {})
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=result.usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )


# --------------------------------------------------------------------------- #
# Synchronous Wrapper for Non-Async Workloads                                 #
# --------------------------------------------------------------------------- #

class SyncGatewayClient:
    """Synchronous Gateway Client for scripts, Django, Flask, or background workers."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        router: SmartRouter | None = None,
    ) -> None:
        self.config = config or GatewayConfig.from_env()
        self.router = router or SmartRouter(self.config.route_tokens)
        self._http = httpx.Client(timeout=self.config.default_timeout)

    def __enter__(self) -> SyncGatewayClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _build_headers(self, route_token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Gateway-Secret": self.config.gateway_secret,
            "X-Gateway-Secret-Version": str(self.config.secret_version),
            "Content-Type": "application/json",
        }
        if route_token:
            resolved = self.router.resolve_token(route_token)
            headers["X-Route-Token"] = resolved
        return headers

    def healthz(self) -> bool:
        url = f"{self.config.base_url}/healthz"
        resp = self._http.get(url)
        return resp.status_code == 200 and resp.json().get("status") == "ok"

    def describe(self, route_token: str) -> ProviderManifest:
        url = f"{self.config.base_url}/v1/describe"
        resp = self._http.get(url, headers=self._build_headers(route_token))
        if resp.status_code == 404:
            raise RouteNotFoundError("provider_unavailable", "Unknown route token", http_status=404)
        return ProviderManifest.model_validate(resp.json())

    def list_models(self, route_token: str) -> list[ModelInfo]:
        url = f"{self.config.base_url}/v1/models"
        resp = self._http.get(url, headers=self._build_headers(route_token))
        if resp.status_code == 404:
            raise RouteNotFoundError("provider_unavailable", "Unknown route token", http_status=404)
        data = ModelsListResponse.model_validate(resp.json())
        return data.models

    def generate_text(
        self,
        route_token: str,
        model: str,
        messages: Sequence[ChatMessage | dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_ms: int = 60000,
    ) -> ExecutionResult[TextOutput]:
        url = f"{self.config.base_url}/v1/execute"
        formatted_messages = [
            m.model_dump() if isinstance(m, ChatMessage) else m for m in messages
        ]
        payload: dict[str, Any] = {"messages": formatted_messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        envelope = {
            "operation": "generate_text",
            "model": model,
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
            "tenant_id": self.config.default_tenant_id,
            "credential": {"mode": "platform"},
            "payload": payload,
            "timeout_ms": timeout_ms,
        }
        resp = self._http.post(
            url,
            headers=self._build_headers(route_token),
            json=envelope,
            timeout=max(5.0, (timeout_ms / 1000.0) + 5.0),
        )
        body = resp.json()
        if not body.get("succeeded", False):
            raw_err = body.get("error") or {}
            raise create_gateway_error(
                category=raw_err.get("category", "non_retryable_error"),
                message=raw_err.get("message", "upstream call failed"),
                retryable=raw_err.get("retryable", False),
                retry_after_ms=raw_err.get("retry_after_ms"),
                provider_code=raw_err.get("provider_code"),
                http_status=resp.status_code,
                raw_error=raw_err,
            )
        typed_output = TextOutput.model_validate(body.get("output") or {})
        raw_usage = body.get("usage") or {}
        usage = UsageInfo(
            input_tokens=raw_usage.get("input_tokens"),
            output_tokens=raw_usage.get("output_tokens"),
            units=raw_usage.get("units", 1),
        )
        return ExecutionResult(
            succeeded=True,
            output=typed_output,
            usage=usage,
            latency_ms=body.get("latency_ms", 0),
            raw_response=body,
        )

