"""Generic JSON aliases only; the SDK does not mirror Gateway schemas."""

from __future__ import annotations

from typing import Any, TypeAlias

JSONValue: TypeAlias = Any
JSONObject: TypeAlias = dict[str, JSONValue]
