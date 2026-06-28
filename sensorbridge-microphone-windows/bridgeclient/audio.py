from __future__ import annotations

import base64
import binascii
import json
import math
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from bridgeclient.client import SensorBridgeClient
from bridgeclient.models import AudioFrame, JsonDict


class AudioSink(Protocol):
    name: str

    def write_frame(self, frame: AudioFrame) -> None:
        ...

    def to_json(self) -> JsonDict:
        ...


class NullAudioSink:
    name = "null"

    def __init__(self) -> None:
        self.frames_written = 0
        self.audio_frames_written = 0
        self.bytes_written = 0

    def write_frame(self, frame: AudioFrame) -> None:
        self.frames_written += 1
        self.audio_frames_written += 1
        if frame.data_base64:
            self.bytes_written += len(base64.b64decode(frame.data_base64))

    def to_json(self) -> JsonDict:
        return {
            "name": self.name,
            "frames_written": self.frames_written,
            "audio_frames_written": self.audio_frames_written,
            "bytes_written": self.bytes_written,
        }


class PcmFileAudioSink:
    name = "pcm_file"

    def __init__(self, directory: str | Path | None = None) -> None:
        if directory is None:
            directory = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SensorBridge" / "microphone"
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.frames_written = 0
        self.audio_frames_written = 0
        self.bytes_written = 0
        self.latest_pcm_path = self.directory / "latest.pcm"
        self.latest_metadata_path = self.directory / "latest.json"

    def write_frame(self, frame: AudioFrame) -> None:
        if not frame.data_base64:
            raise ValueError("pcm-file sink requires data_base64 in the audio frame")
        raw = base64.b64decode(frame.data_base64, validate=True)
        sample_format = _normalize_sample_format(frame.sample_format)
        if sample_format != "S16LE":
            raise ValueError(f"pcm-file sink requires S16LE audio, got {frame.sample_format!r}")
        sample_rate_hz = frame.sample_rate_hz or 48000
        channel_count = frame.channel_count or 1
        if sample_rate_hz < 1:
            raise ValueError("pcm-file sink requires a positive sample_rate_hz")
        if channel_count < 1:
            raise ValueError("pcm-file sink requires a positive channel_count")

        bytes_per_frame = 2 * channel_count
        if len(raw) % bytes_per_frame:
            raise ValueError("pcm-file sink requires PCM bytes aligned to S16LE channel frames")
        frame_count = len(raw) // bytes_per_frame

        _atomic_write(self.latest_pcm_path, raw)
        metadata = {
            "sequence": frame.audio_sample_sequence,
            "timestamp_ns": frame.timestamp_ns,
            "sample_rate_hz": sample_rate_hz,
            "channel_count": channel_count,
            "sample_format": sample_format,
            "frame_count": frame_count,
            "byte_count": len(raw),
            "content_type": "audio/L16",
            "pcm_encoding": "S16LE",
            "path": str(self.latest_pcm_path),
            "updated_at": time.time(),
            "source": frame.raw.get("source", "sensorbridge-audio-frame") if isinstance(frame.raw, dict) else "sensorbridge-audio-frame",
        }
        _atomic_write(self.latest_metadata_path, json.dumps(metadata, indent=2).encode("utf-8"))
        self.frames_written += 1
        self.audio_frames_written += 1
        self.bytes_written += len(raw)

    def to_json(self) -> JsonDict:
        return {
            "name": self.name,
            "frames_written": self.frames_written,
            "audio_frames_written": self.audio_frames_written,
            "bytes_written": self.bytes_written,
            "directory": str(self.directory),
            "latest_pcm_path": str(self.latest_pcm_path),
            "latest_metadata_path": str(self.latest_metadata_path),
        }


@dataclass
class AudioBridgeRunResult:
    frames_requested: int
    frames_written: int
    first_sequence: int | None
    last_sequence: int | None
    sink: JsonDict

    def to_json(self) -> JsonDict:
        return {
            "ok": True,
            "command": "pump_audio",
            "frames_requested": self.frames_requested,
            "frames_written": self.frames_written,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "sink": self.sink,
        }


@dataclass
class AudioFrameAnalysis:
    sequence: int
    sample_rate_hz: int | None
    channel_count: int | None
    sample_format: str | None
    byte_count: int
    frame_count: int | None
    peak_abs: int | None
    rms: float | None
    valid_pcm: bool
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> JsonDict:
        return {
            "sequence": self.sequence,
            "sample_rate_hz": self.sample_rate_hz,
            "channel_count": self.channel_count,
            "sample_format": self.sample_format,
            "byte_count": self.byte_count,
            "frame_count": self.frame_count,
            "peak_abs": self.peak_abs,
            "rms": self.rms,
            "valid_pcm": self.valid_pcm,
            "errors": list(self.errors),
        }


@dataclass
class MicrophonePipelineCheckResult:
    frames_requested: int
    frames_checked: int
    start: JsonDict
    stop: JsonDict | None
    analyses: list[AudioFrameAnalysis]
    consistent_format: bool
    sequence_monotonic: bool
    driver_injection_ready: bool
    sink: JsonDict
    pcm_file_ready: bool
    latest_pcm_exists: bool
    latest_metadata_exists: bool
    latest_pcm_bytes: int
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> JsonDict:
        return {
            "ok": self.driver_injection_ready,
            "command": "microphone_pipeline_check",
            "changes_system": False,
            "frames_requested": self.frames_requested,
            "frames_checked": self.frames_checked,
            "start": self.start,
            "stop": self.stop,
            "analyses": [analysis.to_json() for analysis in self.analyses],
            "consistent_format": self.consistent_format,
            "sequence_monotonic": self.sequence_monotonic,
            "driver_injection_ready": self.driver_injection_ready,
            "sink": self.sink,
            "pcm_file_ready": self.pcm_file_ready,
            "latest_pcm_exists": self.latest_pcm_exists,
            "latest_metadata_exists": self.latest_metadata_exists,
            "latest_pcm_bytes": self.latest_pcm_bytes,
            "errors": list(self.errors),
            "notes": [
                "This check validates sampled SensorBridge microphone frames and writes the latest PCM file for the future driver injection path.",
                "It does not install a Windows virtual microphone or inject audio into SysVAD by itself.",
            ],
        }


def pump_audio_frames(
    client: SensorBridgeClient,
    sink: AudioSink,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
) -> AudioBridgeRunResult:
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1")

    first_sequence: int | None = None
    last_sequence: int | None = None
    for index in range(frame_count):
        frame = client.sample_audio_frame()
        sink.write_frame(frame)
        if first_sequence is None:
            first_sequence = frame.audio_sample_sequence
        last_sequence = frame.audio_sample_sequence
        if frame_delay_s > 0 and index < frame_count - 1:
            time.sleep(frame_delay_s)

    sink_payload = sink.to_json()
    return AudioBridgeRunResult(
        frames_requested=frame_count,
        frames_written=int(sink_payload.get("frames_written", frame_count)),
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        sink=sink_payload,
    )


def analyze_audio_frame(frame: AudioFrame) -> AudioFrameAnalysis:
    errors: list[str] = []
    raw = b""
    if frame.data_base64:
        try:
            raw = base64.b64decode(frame.data_base64, validate=True)
        except (ValueError, TypeError):
            errors.append("data_base64 is not valid base64")
    else:
        errors.append("data_base64 is missing")

    sample_format = _normalize_sample_format(frame.sample_format)
    channel_count = frame.channel_count or 1
    sample_rate_hz = frame.sample_rate_hz or 48000
    bytes_per_sample = 2 if sample_format == "S16LE" else None
    if sample_format != "S16LE":
        errors.append(f"unsupported sample_format {frame.sample_format!r}; expected S16LE")
    if channel_count is None or channel_count < 1:
        errors.append("channel_count is missing or invalid")
    if sample_rate_hz is None or sample_rate_hz < 1:
        errors.append("sample_rate_hz is missing or invalid")

    frame_count: int | None = None
    peak_abs: int | None = None
    rms: float | None = None
    if raw and bytes_per_sample and channel_count and channel_count > 0:
        bytes_per_frame = bytes_per_sample * channel_count
        if len(raw) % bytes_per_frame:
            errors.append("PCM byte length is not aligned to channel_count and S16LE sample size")
        else:
            frame_count = len(raw) // bytes_per_frame
        if len(raw) % 2 == 0:
            sample_count = len(raw) // 2
            if sample_count:
                samples = struct.unpack("<" + "h" * sample_count, raw)
                peak_abs = max(abs(sample) for sample in samples)
                rms = math.sqrt(sum(sample * sample for sample in samples) / sample_count)

    return AudioFrameAnalysis(
        sequence=frame.audio_sample_sequence,
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        sample_format=frame.sample_format,
        byte_count=len(raw),
        frame_count=frame_count,
        peak_abs=peak_abs,
        rms=round(rms, 3) if rms is not None else None,
        valid_pcm=not errors,
        errors=errors,
    )


def check_microphone_pipeline(
    client: SensorBridgeClient,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
    directory: str | Path | None = None,
) -> MicrophonePipelineCheckResult:
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1")

    start = client.start_audio().to_json()
    stop: JsonDict | None = None
    analyses: list[AudioFrameAnalysis] = []
    errors: list[str] = []
    sink = PcmFileAudioSink(directory)
    try:
        for index in range(frame_count):
            frame = client.sample_audio_frame()
            analyses.append(analyze_audio_frame(frame))
            try:
                sink.write_frame(frame)
            except (ValueError, TypeError, binascii.Error) as exc:
                errors.append(f"sequence {frame.audio_sample_sequence}: PCM file sink rejected frame: {exc}")
            if frame_delay_s > 0 and index < frame_count - 1:
                time.sleep(frame_delay_s)
    finally:
        stop = client.stop_audio().to_json()

    formats = {
        (analysis.sample_rate_hz, analysis.channel_count, _normalize_sample_format(analysis.sample_format))
        for analysis in analyses
    }
    consistent_format = len(formats) == 1 and bool(analyses)
    sequences = [analysis.sequence for analysis in analyses]
    sequence_monotonic = all(after > before for before, after in zip(sequences, sequences[1:]))
    if not consistent_format:
        errors.append("audio frame format changed across samples")
    if not sequence_monotonic:
        errors.append("audio sample sequence is not strictly increasing")
    for analysis in analyses:
        errors.extend(f"sequence {analysis.sequence}: {error}" for error in analysis.errors)

    sink_payload = sink.to_json()
    pcm_value = sink_payload.get("latest_pcm_path")
    metadata_value = sink_payload.get("latest_metadata_path")
    pcm_path = Path(str(pcm_value)) if pcm_value else Path()
    metadata_path = Path(str(metadata_value)) if metadata_value else Path()
    latest_pcm_exists = pcm_path.is_file()
    latest_metadata_exists = metadata_path.is_file()
    latest_pcm_bytes = pcm_path.stat().st_size if latest_pcm_exists else 0
    pcm_file_ready = bool(
        sink.frames_written == frame_count
        and latest_pcm_exists
        and latest_metadata_exists
        and latest_pcm_bytes > 0
    )

    driver_injection_ready = bool(analyses) and consistent_format and sequence_monotonic and pcm_file_ready and not errors
    return MicrophonePipelineCheckResult(
        frames_requested=frame_count,
        frames_checked=len(analyses),
        start=start,
        stop=stop,
        analyses=analyses,
        consistent_format=consistent_format,
        sequence_monotonic=sequence_monotonic,
        driver_injection_ready=driver_injection_ready,
        sink=sink_payload,
        pcm_file_ready=pcm_file_ready,
        latest_pcm_exists=latest_pcm_exists,
        latest_metadata_exists=latest_metadata_exists,
        latest_pcm_bytes=latest_pcm_bytes,
        errors=errors,
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def _normalize_sample_format(value: str | None) -> str:
    text = (value or "").upper().replace("-", "_")
    if text in {"S16LE", "PCM_S16LE", "PCM16", "PCM_16", "L16"}:
        return "S16LE"
    return text
