"""Typed Data Models representing the Gateway Canonical Contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field


class GatewayOperation(StrEnum):
    """The 8 canonical operations supported by Gateway v1."""
    GENERATE_TEXT = "generate_text"
    GENERATE_IMAGE = "generate_image"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    SYNTHESIZE_SPEECH = "synthesize_speech"
    CREATE_EMBEDDINGS = "create_embeddings"
    RERANK_DOCUMENTS = "rerank_documents"
    MODERATE_CONTENT = "moderate_content"
    ANALYZE_VISION = "analyze_vision"


class ErrorCategory(StrEnum):
    """The 12 canonical error categories mapped by the Gateway."""
    AUTH_EXPIRED = "auth_expired"
    INVALID_CREDENTIAL = "invalid_credential"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    BAD_REQUEST = "bad_request"
    CONTENT_REJECTED = "content_rejected"
    TIMEOUT = "timeout"
    RETRYABLE_SERVER_ERROR = "retryable_server_error"
    NON_RETRYABLE_ERROR = "non_retryable_error"


class ChatMessage(BaseModel):
    """Standard role-content message for text generation."""
    role: str = Field(description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(description="Message text content")


class UsageInfo(BaseModel):
    """Token and unit consumption reported by the Gateway for platform billing."""
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    units: int = 1


# --------------------------------------------------------------------------- #
# Canonical Output Shapes                                                     #
# --------------------------------------------------------------------------- #

class TextOutput(BaseModel):
    text: str
    finish_reason: str = "stop"


class GeneratedImage(BaseModel):
    b64: str
    format: str = "png"


class ImageOutput(BaseModel):
    images: list[GeneratedImage] = Field(default_factory=list)


class AudioOutput(BaseModel):
    text: str
    language: str | None = None


class SpeechOutput(BaseModel):
    audio_b64: str
    audio_format: str = "mp3"


class EmbeddingsOutput(BaseModel):
    embeddings: list[list[float]]
    dimensions: int


class RerankItem(BaseModel):
    index: int
    relevance_score: float


class RerankOutput(BaseModel):
    results: list[RerankItem] = Field(default_factory=list)


class ModerationOutput(BaseModel):
    flagged: bool
    categories: dict[str, bool] = Field(default_factory=dict)


class VisionOutput(BaseModel):
    text: str


T = TypeVar("T")


class ExecutionResult(BaseModel, Generic[T]):
    """Standard container for any Gateway execution."""
    succeeded: bool
    output: T | None = None
    usage: UsageInfo | None = None
    latency_ms: int = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Discovery & Manifest Shapes                                                 #
# --------------------------------------------------------------------------- #

class ModelInfo(BaseModel):
    name: str
    context_window: int | None = None


class ModelsListResponse(BaseModel):
    models: list[ModelInfo] = Field(default_factory=list)


class ProviderManifest(BaseModel):
    display_name: str
    credential_mode: str
    definition_version: str
    capabilities: dict[str, bool] = Field(default_factory=dict)
    operations: list[str] = Field(default_factory=list)
    models: list[ModelInfo] = Field(default_factory=list)
    health_supported: bool = False


class HealthResponse(BaseModel):
    status: str
    checked_at: str | None = None

