"""Small, generic client for the Provider Gateway.

The SDK deliberately does not define operation enums or provider-specific
request/response models. Discovery data and execution payloads are passed
through as JSON objects returned by the Gateway.
"""

from .client import Gateway, GatewayClient
from .config import GatewayConfig
from .exceptions import (
    GatewayProtocolError,
    GatewaySDKError,
    GatewayTransportError,
    ProviderNotConfiguredError,
)

__all__ = [
    "Gateway",
    "GatewayClient",
    "GatewayConfig",
    "GatewayProtocolError",
    "GatewaySDKError",
    "GatewayTransportError",
    "ProviderNotConfiguredError",
]
