from __future__ import annotations

import base64
import hashlib
import json
import math
import secrets
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel


IDENTITY_SCHEMA_VERSION = "qx.opportunity-identity.v1"


def utc_timestamp(value: datetime) -> str:
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return json_value(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        return utc_timestamp(value)
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite values are not canonical JSON")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def new_evaluation_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    milliseconds = int(timestamp.timestamp() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return f"qxev1_{uuid.UUID(int=value).hex}"


def command_payload_hash(
    *,
    environment_id: str,
    producer_id: str,
    producer_run_id: str,
    symbol: str,
    timeframe: str,
) -> str:
    return sha256_digest(
        {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "environment_id": environment_id,
            "producer_id": producer_id,
            "producer_run_id": producer_run_id,
            "symbol": symbol.upper(),
            "timeframe": timeframe.lower(),
        }
    )


def command_identity(**values: str) -> str:
    return f"qxcmd1_{command_payload_hash(**values)}"


def stream_key(
    *,
    environment_id: str,
    observation_mode: str,
    symbol: str,
    timeframe: str,
    pipeline_version: str,
    config_version: str,
) -> str:
    digest = sha256_digest(
        {
            "schema_version": "qx.opportunity-stream.v1",
            "environment_id": environment_id,
            "observation_mode": observation_mode,
            "symbol": symbol.upper(),
            "timeframe": timeframe.lower(),
            "pipeline_version": pipeline_version,
            "config_version": config_version,
        }
    )
    return f"qxstream1_{digest}"


def encode_cursor(values: dict[str, Any]) -> str:
    payload = canonical_json_bytes({"schema_version": "qx.opportunity-cursor.v1", **values})
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(value + padding)
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid opportunity cursor") from exc
    if (
        not isinstance(payload, dict)
        or payload.pop("schema_version", None) != "qx.opportunity-cursor.v1"
    ):
        raise ValueError("Invalid opportunity cursor schema")
    return payload
