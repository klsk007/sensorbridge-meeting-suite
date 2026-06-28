from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bridgeclient.models import JsonDict


def default_microphone_pcm_directory() -> Path:
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SensorBridge" / "microphone"


@dataclass
class MicrophonePcmFeederCheckResult:
    directory: str
    metadata_path: str
    pcm_path: str | None
    metadata_exists: bool
    pcm_exists: bool
    pcm_bytes: int
    expected_bytes: int | None
    sample_rate_hz: int | None
    channel_count: int | None
    sample_format: str | None
    frame_count: int | None
    duration_ms: float | None
    target_buffer_ms: float
    can_feed_driver: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_json(self) -> JsonDict:
        return {
            "ok": self.can_feed_driver,
            "command": "microphone_feeder_check",
            "changes_system": False,
            "directory": self.directory,
            "metadata_path": self.metadata_path,
            "pcm_path": self.pcm_path,
            "metadata_exists": self.metadata_exists,
            "pcm_exists": self.pcm_exists,
            "pcm_bytes": self.pcm_bytes,
            "expected_bytes": self.expected_bytes,
            "sample_rate_hz": self.sample_rate_hz,
            "channel_count": self.channel_count,
            "sample_format": self.sample_format,
            "frame_count": self.frame_count,
            "duration_ms": self.duration_ms,
            "target_buffer_ms": self.target_buffer_ms,
            "can_feed_driver": self.can_feed_driver,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": self.metadata,
            "notes": [
                "This read-only check consumes the microphone PCM handoff as a future SysVAD/APO/user-mode feeder would.",
                "It does not install a driver, enable Windows test signing, reboot, or create a Windows microphone endpoint.",
            ],
        }


def inspect_microphone_pcm_feeder(
    directory: str | Path | None = None,
    *,
    target_buffer_ms: float = 20.0,
    stale_after_s: float | None = 30.0,
) -> MicrophonePcmFeederCheckResult:
    if directory is None:
        directory = default_microphone_pcm_directory()
    pcm_dir = Path(directory)
    metadata_path = pcm_dir / "latest.json"
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    pcm_path: Path | None = None
    pcm_bytes = 0
    expected_bytes: int | None = None
    sample_rate_hz: int | None = None
    channel_count: int | None = None
    sample_format: str | None = None
    frame_count: int | None = None
    duration_ms: float | None = None

    metadata_exists = metadata_path.is_file()
    if not metadata_exists:
        errors.append("latest.json is missing")
    else:
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metadata = loaded
            else:
                errors.append("latest.json is not a JSON object")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"latest.json could not be read: {exc}")

    if metadata:
        pcm_path_value = metadata.get("path")
        pcm_path = Path(str(pcm_path_value)) if pcm_path_value else pcm_dir / "latest.pcm"
        sample_rate_hz = _optional_positive_int(metadata.get("sample_rate_hz"))
        channel_count = _optional_positive_int(metadata.get("channel_count"))
        sample_format = str(metadata.get("sample_format", "")).upper() or None
        frame_count = _optional_positive_int(metadata.get("frame_count"))
        declared_byte_count = _optional_positive_int(metadata.get("byte_count"))

        if sample_format != "S16LE":
            errors.append(f"unsupported sample_format {sample_format!r}; expected S16LE")
        if sample_rate_hz is None:
            errors.append("sample_rate_hz is missing or invalid")
        if channel_count is None:
            errors.append("channel_count is missing or invalid")
        if frame_count is None:
            errors.append("frame_count is missing or invalid")
        if sample_rate_hz and frame_count:
            duration_ms = round((frame_count / sample_rate_hz) * 1000.0, 3)
            if duration_ms < target_buffer_ms / 4:
                warnings.append("PCM frame is much shorter than the target feeder buffer")
        if channel_count and frame_count:
            expected_bytes = frame_count * channel_count * 2
            if declared_byte_count is not None and declared_byte_count != expected_bytes:
                errors.append("metadata byte_count does not match frame_count * channel_count * 2")
        if stale_after_s is not None:
            updated_at = _optional_float(metadata.get("updated_at"))
            if updated_at is not None:
                age_s = max(0.0, time.time() - updated_at)
                if age_s > stale_after_s:
                    warnings.append(f"PCM handoff is stale by {round(age_s, 3)} seconds")

    if pcm_path is None:
        pcm_path = pcm_dir / "latest.pcm"
    pcm_exists = pcm_path.is_file()
    if not pcm_exists:
        errors.append("latest.pcm is missing")
    else:
        try:
            pcm_bytes = pcm_path.stat().st_size
        except OSError as exc:
            errors.append(f"latest.pcm could not be inspected: {exc}")
        if expected_bytes is not None and pcm_bytes != expected_bytes:
            errors.append("latest.pcm size does not match metadata")
        if pcm_bytes <= 0:
            errors.append("latest.pcm is empty")

    can_feed_driver = not errors and metadata_exists and pcm_exists and pcm_bytes > 0
    return MicrophonePcmFeederCheckResult(
        directory=str(pcm_dir),
        metadata_path=str(metadata_path),
        pcm_path=str(pcm_path) if pcm_path else None,
        metadata_exists=metadata_exists,
        pcm_exists=pcm_exists,
        pcm_bytes=pcm_bytes,
        expected_bytes=expected_bytes,
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        sample_format=sample_format,
        frame_count=frame_count,
        duration_ms=duration_ms,
        target_buffer_ms=target_buffer_ms,
        can_feed_driver=can_feed_driver,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
