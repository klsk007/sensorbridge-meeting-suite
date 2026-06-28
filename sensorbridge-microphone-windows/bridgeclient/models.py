from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


JsonDict = dict[str, Any]


def error_json(code: str, message: str, *, detail: Any | None = None) -> JsonDict:
    error: JsonDict = {"code": code, "message": message}
    if detail is not None:
        error["detail"] = detail
    return {"ok": False, "error": error}


def _as_dict(payload: Mapping[str, Any], field_name: str = "payload") -> JsonDict:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return dict(payload)


def _unwrap(payload: Mapping[str, Any], *names: str) -> JsonDict:
    data = _as_dict(payload)
    for name in names:
        nested = data.get(name)
        if isinstance(nested, Mapping):
            return dict(nested)
    return data


def _first(data: Mapping[str, Any], *names: str) -> Any | None:
    for name in names:
        if name in data:
            return data[name]
    return None


def _optional_int(data: Mapping[str, Any], *names: str) -> int | None:
    value = _first(data, *names)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_int(data: Mapping[str, Any], *names: str) -> int:
    value = _optional_int(data, *names)
    if value is None:
        joined = ", ".join(names)
        raise ValueError(f"Missing required integer field; expected one of: {joined}")
    return value


def _optional_str(data: Mapping[str, Any], *names: str) -> str | None:
    value = _first(data, *names)
    if value is None:
        return None
    text = str(value)
    return text if text else None


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    command: str
    message: str | None = None
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, command: str, payload: Mapping[str, Any]) -> "CommandResult":
        data = _as_dict(payload)
        return cls(
            ok=bool(data.get("ok", True)),
            command=command,
            message=_optional_str(data, "message", "status"),
            raw=data,
        )

    def to_json(self) -> JsonDict:
        data: JsonDict = {"ok": self.ok, "command": self.command}
        if self.message is not None:
            data["message"] = self.message
        if self.raw:
            data["raw"] = self.raw
        return data


@dataclass(frozen=True)
class AudioFrame:
    audio_sample_sequence: int
    timestamp_ns: int | None = None
    sample_rate_hz: int | None = None
    channel_count: int | None = None
    sample_format: str | None = None
    data_base64: str | None = None
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "AudioFrame":
        data = _unwrap(payload, "audio_frame", "frame")
        return cls(
            audio_sample_sequence=_required_int(
                data,
                "audio_sample_sequence",
                "sequence",
                "sample_sequence",
            ),
            timestamp_ns=_timestamp_ns(data),
            sample_rate_hz=_optional_int(data, "sample_rate_hz", "sampleRateHz", "sample_rate"),
            channel_count=_optional_int(data, "channel_count", "channels"),
            sample_format=_optional_str(data, "sample_format", "format", "codec"),
            data_base64=_optional_str(data, "data_base64", "payloadBase64", "payload_base64", "base64", "pcm_base64"),
            raw=data,
        )

    def to_json(self) -> JsonDict:
        data: JsonDict = {"audio_sample_sequence": self.audio_sample_sequence}
        if self.timestamp_ns is not None:
            data["timestamp_ns"] = self.timestamp_ns
        if self.sample_rate_hz is not None:
            data["sample_rate_hz"] = self.sample_rate_hz
        if self.channel_count is not None:
            data["channel_count"] = self.channel_count
        if self.sample_format is not None:
            data["sample_format"] = self.sample_format
        if self.data_base64 is not None:
            data["data_base64"] = self.data_base64
        if self.raw:
            data["raw"] = self.raw
        return data


def _timestamp_ns(data: Mapping[str, Any]) -> int | None:
    timestamp_ns = _optional_int(data, "timestamp_ns", "timestampNanoseconds")
    if timestamp_ns is not None:
        return timestamp_ns
    timestamp_us = _optional_int(data, "timestampUs", "timestamp_us")
    if timestamp_us is not None:
        return timestamp_us * 1000
    return None
