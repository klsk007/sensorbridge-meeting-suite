from __future__ import annotations

import base64
import binascii
import time
from dataclasses import dataclass, field
from typing import Any

from bridgeclient.audio import analyze_audio_frame
from bridgeclient.client import SensorBridgeClient
from bridgeclient.models import AudioFrame, JsonDict


DEFAULT_CABLE_OUTPUT_DEVICE = "CABLE Input"
DEFAULT_MEETING_INPUT_DEVICE = "CABLE Output"


@dataclass
class VbCablePumpResult:
    frames_requested: int
    frames_received: int
    frames_written: int
    output_device: str
    output_device_found: bool
    meeting_input_device_found: bool
    latest_audio: JsonDict | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> JsonDict:
        return {
            "ok": self.output_device_found and self.meeting_input_device_found and self.frames_written > 0 and not self.errors,
            "command": "pump_vbcable",
            "changes_system": False,
            "mode": "user_mode_vbcable_audio_bridge",
            "frames_requested": self.frames_requested,
            "frames_received": self.frames_received,
            "frames_written": self.frames_written,
            "output_device": self.output_device,
            "output_device_found": self.output_device_found,
            "meeting_input_device": DEFAULT_MEETING_INPUT_DEVICE,
            "meeting_input_device_found": self.meeting_input_device_found,
            "latest_audio": self.latest_audio,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "notes": [
                "This uses VB-CABLE as a user-mode audio bridge and does not install or modify audio drivers.",
                "Send audio to CABLE Input, then select CABLE Output as the microphone in Tencent Meeting.",
            ],
        }


@dataclass
class VbCableLoopbackResult:
    frames_requested: int
    frames_received: int
    frames_written: int
    output_device: str
    output_device_found: bool
    meeting_input_device_found: bool
    recorded_frame_count: int
    recorded_peak_abs: int | None
    recorded_rms: float | None
    latest_audio: JsonDict | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> JsonDict:
        loopback_has_audio = bool(self.recorded_peak_abs and self.recorded_peak_abs > 0)
        return {
            "ok": (
                self.output_device_found
                and self.meeting_input_device_found
                and self.frames_written > 0
                and loopback_has_audio
                and not self.errors
            ),
            "command": "vbcable_loopback_check",
            "changes_system": False,
            "mode": "user_mode_vbcable_audio_bridge",
            "frames_requested": self.frames_requested,
            "frames_received": self.frames_received,
            "frames_written": self.frames_written,
            "output_device": self.output_device,
            "output_device_found": self.output_device_found,
            "meeting_input_device": DEFAULT_MEETING_INPUT_DEVICE,
            "meeting_input_device_found": self.meeting_input_device_found,
            "recorded_frame_count": self.recorded_frame_count,
            "recorded_peak_abs": self.recorded_peak_abs,
            "recorded_rms": self.recorded_rms,
            "ordinary_apps_can_record_cable_output": loopback_has_audio,
            "latest_audio": self.latest_audio,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "notes": [
                "This writes iPad microphone PCM to CABLE Input and records from CABLE Output.",
                "It does not install or modify drivers; it verifies the same capture path meeting apps use.",
            ],
        }


def inspect_vbcable(output_device: str = DEFAULT_CABLE_OUTPUT_DEVICE) -> JsonDict:
    backend = _load_sounddevice()
    if not backend["ok"]:
        return {
            "ok": False,
            "command": "vbcable_status",
            "changes_system": False,
            "mode": "user_mode_vbcable_audio_bridge",
            "sounddevice_available": False,
            "output_device": output_device,
            "output_device_found": False,
            "meeting_input_device": DEFAULT_MEETING_INPUT_DEVICE,
            "meeting_input_device_found": False,
            "error": backend["error"],
            "install_hint": "Install the optional Python sounddevice package, then install VB-CABLE manually from VB-Audio.",
        }

    sd = backend["sounddevice"]
    devices = _device_list(sd)
    output = _find_device(devices, output_device, is_output=True)
    meeting_input = _find_device(devices, DEFAULT_MEETING_INPUT_DEVICE, is_input=True)
    return {
        "ok": bool(output and meeting_input),
        "command": "vbcable_status",
        "changes_system": False,
        "mode": "user_mode_vbcable_audio_bridge",
        "sounddevice_available": True,
        "output_device": output_device,
        "output_device_found": output is not None,
        "output_device_info": output,
        "meeting_input_device": DEFAULT_MEETING_INPUT_DEVICE,
        "meeting_input_device_found": meeting_input is not None,
        "meeting_input_device_info": meeting_input,
        "audio_outputs": [device for device in devices if device["max_output_channels"] > 0],
        "audio_inputs": [device for device in devices if device["max_input_channels"] > 0],
        "notes": [
            "VB-CABLE must be installed manually by the user. This app does not install or configure drivers.",
            "Tencent Meeting should use CABLE Output as its microphone.",
        ],
    }


def pump_vbcable_frames(
    client: SensorBridgeClient,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
    output_device: str = DEFAULT_CABLE_OUTPUT_DEVICE,
) -> VbCablePumpResult:
    backend = _load_sounddevice()
    if not backend["ok"]:
        return VbCablePumpResult(
            frames_requested=frame_count,
            frames_received=0,
            frames_written=0,
            output_device=output_device,
            output_device_found=False,
            meeting_input_device_found=False,
            errors=[backend["error"]["message"]],
        )

    sd = backend["sounddevice"]
    devices = _device_list(sd)
    output = _find_device(devices, output_device, is_output=True)
    meeting_input = _find_device(devices, DEFAULT_MEETING_INPUT_DEVICE, is_input=True)
    if output is None:
        return VbCablePumpResult(
            frames_requested=frame_count,
            frames_received=0,
            frames_written=0,
            output_device=output_device,
            output_device_found=False,
            meeting_input_device_found=meeting_input is not None,
            errors=[f"VB-CABLE playback device not found: {output_device}"],
        )

    requested = frame_count
    unlimited = frame_count <= 0
    frames_received = 0
    frames_written = 0
    latest_audio: JsonDict | None = None
    errors: list[str] = []
    warnings: list[str] = []
    start = client.start_audio().to_json()
    if not start.get("ok", True):
        errors.append(str(start))

    stream = None
    try:
        first_frame = _next_valid_frame(client, warnings)
        if first_frame is None:
            errors.append("No valid S16LE microphone PCM frame was received.")
            return VbCablePumpResult(
                frames_requested=requested,
                frames_received=frames_received,
                frames_written=frames_written,
                output_device=output_device,
                output_device_found=True,
                meeting_input_device_found=meeting_input is not None,
                latest_audio=latest_audio,
                errors=errors,
                warnings=warnings,
            )

        sample_rate_hz = first_frame.sample_rate_hz or 48000
        channel_count = first_frame.channel_count or 1
        stream = sd.OutputStream(
            samplerate=sample_rate_hz,
            channels=channel_count,
            dtype="int16",
            device=output["index"],
        )
        stream.start()
        for frame in _frame_iter(client, first_frame, unlimited, frame_count):
            frames_received += 1
            analysis = analyze_audio_frame(frame)
            latest_audio = analysis.to_json()
            try:
                samples = _decode_s16le_frame(frame)
                stream.write(samples)
                frames_written += 1
            except Exception as exc:
                warnings.append(f"sequence {frame.audio_sample_sequence}: {exc}")
            if frame_delay_s > 0:
                time.sleep(frame_delay_s)
    except KeyboardInterrupt:
        warnings.append("Interrupted by user.")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                warnings.append(f"closing output stream: {exc}")
        try:
            client.stop_audio()
        except Exception as exc:
            warnings.append(f"stop_audio: {exc}")

    return VbCablePumpResult(
        frames_requested=requested,
        frames_received=frames_received,
        frames_written=frames_written,
        output_device=output_device,
        output_device_found=True,
        meeting_input_device_found=meeting_input is not None,
        latest_audio=latest_audio,
        errors=errors,
        warnings=warnings,
    )


def check_vbcable_loopback(
    client: SensorBridgeClient,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
    output_device: str = DEFAULT_CABLE_OUTPUT_DEVICE,
) -> VbCableLoopbackResult:
    backend = _load_sounddevice()
    if not backend["ok"]:
        return VbCableLoopbackResult(
            frames_requested=frame_count,
            frames_received=0,
            frames_written=0,
            output_device=output_device,
            output_device_found=False,
            meeting_input_device_found=False,
            recorded_frame_count=0,
            recorded_peak_abs=None,
            recorded_rms=None,
            errors=[backend["error"]["message"]],
        )

    sd = backend["sounddevice"]
    np = backend["numpy"]
    devices = _device_list(sd)
    output = _find_device(devices, output_device, is_output=True)
    meeting_input = _find_device(devices, DEFAULT_MEETING_INPUT_DEVICE, is_input=True)
    if output is None or meeting_input is None:
        return VbCableLoopbackResult(
            frames_requested=frame_count,
            frames_received=0,
            frames_written=0,
            output_device=output_device,
            output_device_found=output is not None,
            meeting_input_device_found=meeting_input is not None,
            recorded_frame_count=0,
            recorded_peak_abs=None,
            recorded_rms=None,
            errors=["VB-CABLE CABLE Input/CABLE Output pair was not found."],
        )

    frames_received = 0
    frames_written = 0
    latest_audio: JsonDict | None = None
    recorded_chunks: list[Any] = []
    errors: list[str] = []
    warnings: list[str] = []
    start = client.start_audio().to_json()
    if not start.get("ok", True):
        errors.append(str(start))

    output_stream = None
    input_stream = None
    try:
        first_frame = _next_valid_frame(client, warnings)
        if first_frame is None:
            errors.append("No valid S16LE microphone PCM frame was received.")
        else:
            sample_rate_hz = first_frame.sample_rate_hz or 48000
            channel_count = first_frame.channel_count or 1
            output_stream = sd.OutputStream(
                samplerate=sample_rate_hz,
                channels=channel_count,
                dtype="int16",
                device=output["index"],
            )
            input_stream = sd.InputStream(
                samplerate=sample_rate_hz,
                channels=channel_count,
                dtype="int16",
                device=meeting_input["index"],
            )
            output_stream.start()
            input_stream.start()
            for frame in _frame_iter(client, first_frame, False, max(1, frame_count)):
                frames_received += 1
                analysis = analyze_audio_frame(frame)
                latest_audio = analysis.to_json()
                try:
                    samples = _decode_s16le_frame(frame)
                    output_stream.write(samples)
                    frames_written += 1
                    if frame_delay_s > 0:
                        time.sleep(frame_delay_s)
                    recorded, overflowed = input_stream.read(samples.shape[0])
                    if overflowed:
                        warnings.append("CABLE Output input stream reported overflow.")
                    recorded_chunks.append(recorded.copy())
                except Exception as exc:
                    warnings.append(f"sequence {frame.audio_sample_sequence}: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        for stream, label in ((input_stream, "input"), (output_stream, "output")):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    warnings.append(f"closing {label} stream: {exc}")
        try:
            client.stop_audio()
        except Exception as exc:
            warnings.append(f"stop_audio: {exc}")

    recorded_frame_count = 0
    recorded_peak_abs = None
    recorded_rms = None
    if recorded_chunks:
        recorded_audio = np.concatenate(recorded_chunks, axis=0)
        recorded_frame_count = int(recorded_audio.shape[0])
        recorded_peak_abs, recorded_rms = _sample_stats(recorded_audio)

    return VbCableLoopbackResult(
        frames_requested=max(1, frame_count),
        frames_received=frames_received,
        frames_written=frames_written,
        output_device=output_device,
        output_device_found=True,
        meeting_input_device_found=True,
        recorded_frame_count=recorded_frame_count,
        recorded_peak_abs=recorded_peak_abs,
        recorded_rms=recorded_rms,
        latest_audio=latest_audio,
        errors=errors,
        warnings=warnings,
    )


def _load_sounddevice() -> JsonDict:
    try:
        import numpy as np
        import sounddevice as sd
        return {"ok": True, "numpy": np, "sounddevice": sd}
    except Exception as exc:
        return {
            "ok": False,
            "error": {
                "code": "sounddevice_unavailable",
                "message": str(exc),
            },
        }


def _device_list(sd: Any) -> list[JsonDict]:
    devices = []
    hostapis = sd.query_hostapis() if hasattr(sd, "query_hostapis") else []
    for index, device in enumerate(sd.query_devices()):
        hostapi_index = int(device.get("hostapi", -1) or -1)
        hostapi_name = ""
        if 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name", ""))
        devices.append(
            {
                "index": index,
                "name": str(device.get("name", "")),
                "hostapi": hostapi_index,
                "hostapi_name": hostapi_name,
                "max_input_channels": int(device.get("max_input_channels", 0) or 0),
                "max_output_channels": int(device.get("max_output_channels", 0) or 0),
                "default_samplerate": float(device.get("default_samplerate", 0) or 0),
            }
        )
    return devices


def _find_device(devices: list[JsonDict], name: str, *, is_input: bool = False, is_output: bool = False) -> JsonDict | None:
    needle = name.lower()
    candidates = []
    for device in devices:
        text = str(device.get("name", "")).lower()
        if needle not in text:
            continue
        if is_input and int(device.get("max_input_channels") or 0) < 1:
            continue
        if is_output and int(device.get("max_output_channels") or 0) < 1:
            continue
        candidates.append(device)
    if not candidates:
        return None

    def score(device: JsonDict) -> tuple[int, int, int, int, int]:
        rate = int(float(device.get("default_samplerate") or 0))
        channels_key = "max_input_channels" if is_input else "max_output_channels"
        channels = int(device.get(channels_key) or 0)
        exact = 1 if str(device.get("name", "")).lower().strip() == needle.strip() else 0
        hostapi = str(device.get("hostapi_name", "")).lower()
        hostapi_score = 4 if "wasapi" in hostapi else 2 if "directsound" in hostapi else 1 if "mme" in hostapi else 0
        rate_score = 2 if rate == 48000 else 1 if rate == 44100 else 0
        stereo_score = 2 if channels == 2 else 1 if channels > 2 else 0
        fewer_channels = -abs(channels - 2)
        return (exact, hostapi_score, rate_score, stereo_score, fewer_channels)

    return sorted(candidates, key=score, reverse=True)[0]


def _next_valid_frame(client: SensorBridgeClient, warnings: list[str]) -> AudioFrame | None:
    for _ in range(20):
        frame = client.sample_audio_frame()
        analysis = analyze_audio_frame(frame)
        if analysis.valid_pcm:
            return frame
        warnings.extend(f"sequence {analysis.sequence}: {error}" for error in analysis.errors)
    return None


def _frame_iter(client: SensorBridgeClient, first_frame: AudioFrame, unlimited: bool, frame_count: int):
    yield first_frame
    remaining = None if unlimited else max(0, frame_count - 1)
    while remaining is None or remaining > 0:
        yield client.sample_audio_frame()
        if remaining is not None:
            remaining -= 1


def _decode_s16le_frame(frame: AudioFrame) -> Any:
    backend = _load_sounddevice()
    np = backend["numpy"]
    if not frame.data_base64:
        raise ValueError("audio frame does not contain PCM data")
    try:
        raw = base64.b64decode(frame.data_base64, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ValueError(f"invalid base64 PCM data: {exc}") from exc
    channel_count = frame.channel_count or 1
    if len(raw) % (2 * channel_count):
        raise ValueError("PCM bytes are not aligned to S16LE channel frames")
    samples = np.frombuffer(raw, dtype=np.int16)
    return samples.reshape((-1, channel_count))


def _sample_stats(samples: Any) -> tuple[int | None, float | None]:
    if samples is None or samples.size == 0:
        return None, None
    import numpy as np

    values = samples.astype(np.float64)
    peak = int(np.max(np.abs(values)))
    rms = float(np.sqrt(np.mean(np.square(values))))
    return peak, round(rms, 3)
