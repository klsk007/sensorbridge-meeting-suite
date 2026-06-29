from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sensorbridge-microphone-windows"))
sys.path.insert(0, str(ROOT / "sensorbridge-speaker-windows"))

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, RTCRtpSender

from bridgeclient.webrtc_microphone import (
    WebRTCMicrophoneClient,
    _AudioReceiverState,
    _apply_polled_ice_candidates,
    _consume_audio_track,
    _device_list,
    _extract_description,
    _find_device,
    _load_audio_backend,
    _microphone_upstream_status,
    _ms_to_frames,
    _receiver_stats_payload,
    _wait_for_ice_gathering_complete,
)
from speakerclient.webrtc_downlink import (
    CableOutputAudioTrack,
    _outbound_audio_totals,
    _prefer_codec,
    _speaker_downlink_status,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Combined SensorBridge meeting audio WebRTC bridge.")
    parser.add_argument("--base-url", default="http://192.168.0.24:27180")
    parser.add_argument("--output-device", default="CABLE Input")
    parser.add_argument("--capture-device", default="CABLE Output")
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--mic-gain", type=float, default=1.0)
    parser.add_argument("--low-cut-hz", type=float, default=80.0)
    parser.add_argument("--noise-gate-threshold", type=float, default=0.0)
    parser.add_argument("--playback-prebuffer-ms", type=float, default=2500.0)
    parser.add_argument("--playback-max-buffer-ms", type=float, default=6000.0)
    parser.add_argument("--speaker-gain", type=float, default=0.35)
    parser.add_argument("--speaker-output-channels", type=int, default=1)
    parser.add_argument("--speaker-frame-samples", type=int, default=960)
    parser.add_argument("--enable-video", action="store_true")
    parser.add_argument("--no-microphone", action="store_true")
    parser.add_argument("--no-speaker", action="store_true")
    parser.add_argument("--push-to-talk-control", default="")
    parser.add_argument("--push-to-talk-default-muted", action="store_true")
    parser.add_argument("command", nargs="?", default="webrtc-duplex")
    return parser


def _is_connected_state(value: Any) -> bool:
    return str(value or "").lower() in {"connected", "completed"}


def _is_error_state(value: Any) -> bool:
    return str(value or "").lower() in {"error", "failed", "disconnected", "closed"}


def _exception_summary(exc: BaseException) -> str:
    message = str(exc)
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return f"{exc.__class__.__name__}: {exc!r}"


def _merge_video_receiver_stats(payload: dict[str, Any], video_sink: "FrameFileVideoSink | None", pc: Any) -> dict[str, Any]:
    if video_sink is None:
        return payload
    video_status = video_sink.status()
    received_fps = float(video_status.get("receivedFps") or 0.0)
    latest_age = video_status.get("latestFrameAgeMs")
    video_state = "virtual_camera_output" if received_fps > 0 else "waiting_for_video_frames"
    payload.update(
        {
            "videoReceiverState": video_state,
            "windowsVideoState": video_state,
            "receivedFps": received_fps,
            "decodedFps": received_fps,
            "virtualCameraFps": received_fps,
            "latestFrameAgeMs": latest_age,
            "droppedFrames": int(video_status.get("droppedFrames") or 0),
            "normalWindowsCameraVisible": True,
            "normalAppCameraVisible": True,
            "peerConnectionState": str(pc.connectionState),
            "iceConnectionState": str(pc.iceConnectionState),
        }
    )
    return payload


async def run_duplex(args: argparse.Namespace) -> dict[str, Any]:
    microphone_enabled = not bool(args.no_microphone)
    speaker_enabled = not bool(args.no_speaker)
    if not microphone_enabled and not speaker_enabled and not args.enable_video:
        return {"ok": False, "errors": ["At least one of microphone, speaker, or video must be enabled."]}

    backend = _load_audio_backend()
    if not backend["ok"]:
        return {"ok": False, "errors": [backend["error"]["message"]]}

    sd = backend["sounddevice"]
    np = backend["numpy"]
    devices = _device_list(sd)
    mic_output = _find_device(devices, args.output_device, is_output=True) if microphone_enabled else None
    speaker_capture = _find_device(devices, args.capture_device, is_input=True) if speaker_enabled else None
    missing_devices: list[str] = []
    if microphone_enabled and mic_output is None:
        missing_devices.append(f"Microphone output device not found: {args.output_device}")
    if speaker_enabled and speaker_capture is None:
        missing_devices.append(f"Speaker capture device not found: {args.capture_device}")
    if missing_devices:
        return {"ok": False, "errors": missing_devices}

    client = WebRTCMicrophoneClient(args.base_url, timeout=args.timeout)
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
    receiver = _AudioReceiverState(loopback_capture=False, loopback_input_index=None, capture_path=None)
    video_sink = FrameFileVideoSink() if args.enable_video else None
    receiver.output_gain = max(0.05, min(20.0, float(args.mic_gain or 1.0)))
    receiver.low_cut_hz = max(0.0, min(300.0, float(args.low_cut_hz or 0.0)))
    receiver.noise_gate_threshold = max(0.0, min(5000.0, float(args.noise_gate_threshold or 0.0)))
    receiver.playback_prebuffer_frames = _ms_to_frames(args.playback_prebuffer_ms, 48000, minimum=4800, maximum=240000)
    receiver.playback_max_buffer_frames = _ms_to_frames(
        args.playback_max_buffer_ms,
        48000,
        minimum=receiver.playback_prebuffer_frames,
        maximum=480000,
    )
    receiver.push_to_talk_control_path = args.push_to_talk_control or ""
    receiver.push_to_talk_default_muted = bool(args.push_to_talk_default_muted)

    warnings: list[str] = []
    errors: list[str] = []
    final_status: dict[str, Any] = {}
    speaker_track: CableOutputAudioTrack | None = None
    outbound_packets = 0
    outbound_bytes = 0
    last_post_at = 0.0
    peer_connection_state = "new"
    ice_connection_state = "new"

    @pc.on("track")
    def on_track(track: Any) -> None:
        if getattr(track, "kind", None) == "audio" and microphone_enabled and mic_output is not None:
            asyncio.create_task(_consume_audio_track(track, receiver, sd, np, int(mic_output["index"]), warnings))
        elif getattr(track, "kind", None) == "video" and video_sink is not None:
            asyncio.create_task(_consume_video_track(track, video_sink, warnings))

    try:
        if microphone_enabled:
            client.start_audio()
            mic_transceiver = pc.addTransceiver("audio", direction="recvonly")
            _prefer_codec(mic_transceiver, RTCRtpSender.getCapabilities("audio").codecs, "opus")

        if speaker_enabled and speaker_capture is not None:
            speaker_track = CableOutputAudioTrack(
                sounddevice=sd,
                numpy=np,
                device_index=int(speaker_capture["index"]),
                capture_channels=min(2, max(1, int(speaker_capture.get("max_input_channels") or 1))),
                sample_rate_hz=48000,
                output_channels=max(1, min(2, int(args.speaker_output_channels or 1))),
                frame_samples=max(160, int(args.speaker_frame_samples or 960)),
                gain=max(0.0, min(2.0, float(args.speaker_gain or 0.35))),
            )
            speaker_transceiver = pc.addTransceiver(speaker_track, direction="sendonly")
            _prefer_codec(speaker_transceiver, RTCRtpSender.getCapabilities("audio").codecs, "opus")

        if args.enable_video:
            video_transceiver = pc.addTransceiver("video", direction="recvonly")
            _prefer_codec(video_transceiver, RTCRtpSender.getCapabilities("video").codecs, "H264")

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await _wait_for_ice_gathering_complete(pc, timeout_seconds=5.0)
        local = pc.localDescription
        answer_payload = client.post_offer({"type": local.type, "sdp": local.sdp})
        answer = _extract_description(answer_payload)
        if answer is None:
            raise RuntimeError(f"WebRTC offer response did not include an answer: {answer_payload}")
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        await _apply_polled_ice_candidates(pc, client, warnings)

        deadline = None if args.duration_seconds <= 0 else time.monotonic() + max(1.0, float(args.duration_seconds))
        while deadline is None or time.monotonic() < deadline:
            await asyncio.sleep(0.25)
            peer_connection_state = str(pc.connectionState)
            ice_connection_state = str(pc.iceConnectionState)
            stats = await pc.getStats()
            outbound_packets, outbound_bytes = _outbound_audio_totals(stats)
            now = time.monotonic()
            if now - last_post_at >= 1.0:
                last_post_at = now
                if microphone_enabled or video_sink is not None:
                    try:
                        stats_payload = _receiver_stats_payload(receiver, True, True, pc)
                        client.post_receiver_stats(_merge_video_receiver_stats(stats_payload, video_sink, pc))
                    except Exception as exc:
                        warnings.append(f"receiver stats post failed: {exc}")
                try:
                    final_status = client.webrtc_status()
                except Exception as exc:
                    warnings.append(f"webrtc status poll failed: {exc}")

        if microphone_enabled or video_sink is not None:
            try:
                stats_payload = _receiver_stats_payload(receiver, True, True, pc)
                client.post_receiver_stats(_merge_video_receiver_stats(stats_payload, video_sink, pc))
            except Exception as exc:
                warnings.append(f"final receiver stats post failed: {exc}")
        try:
            final_status = client.webrtc_status()
        except Exception as exc:
            warnings.append(f"final webrtc status poll failed: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        receiver.stopping = True
        if receiver.playback_buffer is not None:
            receiver.playback_buffer.count_underflows = False
        if receiver.output_stream is not None:
            try:
                await asyncio.to_thread(receiver.output_stream.stop)
                await asyncio.to_thread(receiver.output_stream.close)
            except Exception as exc:
                warnings.append(f"closing microphone output stream: {exc}")
        if speaker_track is not None:
            try:
                await speaker_track.stop_capture()
            except Exception as exc:
                warnings.append(f"speaker capture stop: {exc}")
        try:
            await pc.close()
        except Exception as exc:
            warnings.append(f"peer close: {exc}")

    microphone = _microphone_upstream_status(final_status)
    speaker = _speaker_downlink_status(final_status)
    microphone_ok = True
    if microphone_enabled:
        microphone_ok = bool(
            microphone.get("microphoneUpstreamStatsFresh") is True
            and int(microphone.get("microphoneUpstreamPacketsSent") or 0) > 0
            and receiver.receiver_state == "receiving_webrtc_opus"
            and receiver.audio_frames_written > 0
        )
    speaker_ok = True
    if speaker_enabled:
        speaker_ok = bool(
            speaker.get("speakerDownlinkStatsFresh") is True
            and int(speaker.get("speakerDownlinkPacketsReceived") or 0) > 0
            and outbound_packets > 0
        )
    camera_ok = True
    if args.enable_video and args.duration_seconds > 0:
        camera_ok = bool(video_sink is not None and video_sink.frames_written > 0)
    status_peer_state = final_status.get("peerConnectionState")
    status_ice_state = final_status.get("iceConnectionState")
    status_windows_receiver_state = final_status.get("windowsReceiverState")
    status_windows_video_state = final_status.get("windowsVideoState")
    transport_ok = bool(
        _is_connected_state(peer_connection_state)
        and _is_connected_state(ice_connection_state)
        and _is_connected_state(status_peer_state)
        and _is_connected_state(status_ice_state)
        and not _is_error_state(status_windows_receiver_state)
        and not (args.enable_video and _is_error_state(status_windows_video_state))
    )
    ok = bool(
        not errors
        and transport_ok
        and microphone_ok
        and speaker_ok
        and camera_ok
    )
    return {
        "ok": ok,
        "command": "webrtc_duplex_audio",
        "transport": "single_webrtc_peer_connection",
        "base_url": args.base_url,
        "microphone": {
            "enabled": microphone_enabled,
            "output_device": args.output_device,
            "receiver_state": receiver.receiver_state,
            "frames_written": receiver.audio_frames_written,
            "packets_received": receiver.audio_packets_received,
            **microphone,
        },
        "speaker": {
            "enabled": speaker_enabled,
            "capture_device": args.capture_device,
            "windows_outbound_packets_sent": outbound_packets,
            "windows_outbound_bytes_sent": outbound_bytes,
            **speaker,
        },
        "camera": video_sink.status() if video_sink is not None else {"enabled": False},
        "peerConnectionState": peer_connection_state,
        "iceConnectionState": ice_connection_state,
        "transportOk": transport_ok,
        "microphoneOk": microphone_ok,
        "speakerOk": speaker_ok,
        "cameraOk": camera_ok,
        "errors": errors,
        "warnings": warnings,
        "ipad_webrtc_status": final_status,
    }


class FrameFileVideoSink:
    FPS_WINDOW_SECONDS = 3.0

    def __init__(self, directory: str | Path | None = None, target_fps: float = 30.0) -> None:
        if directory is None:
            directory = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SensorBridge" / "camera"
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.latest_frame_path = self.directory / "latest.bmp"
        self.latest_metadata_path = self.directory / "latest.json"
        self.frames_written = 0
        self.last_error: str | None = None
        self.last_frame_at: float | None = None
        self._frame_times: deque[float] = deque()
        self._dropped_frames = 0
        self._target_frame_interval = 1.0 / max(1.0, float(target_fps or 30.0))

    def should_accept_frame(self) -> bool:
        if self.last_frame_at is None:
            return True
        return (time.monotonic() - self.last_frame_at) >= self._target_frame_interval

    def write_raw_frame(self, *, sequence: int, width: int, height: int, pixel_format: str, raw: bytes) -> None:
        start = time.monotonic()
        payload = _encode_bmp(width, height, raw, pixel_format.lower())
        _atomic_write(self.latest_frame_path, payload)
        metadata = {
            "sequence": sequence,
            "timestamp_ns": time.time_ns(),
            "width": width,
            "height": height,
            "pixel_format": pixel_format,
            "content_type": "image/bmp",
            "path": str(self.latest_frame_path),
            "updated_at": time.time(),
            "source": "meeting_audio_bridge",
        }
        _atomic_write(self.latest_metadata_path, json.dumps(metadata, indent=2).encode("utf-8"))
        self.frames_written += 1
        self.last_frame_at = time.monotonic()
        self._frame_times.append(self.last_frame_at)
        cutoff = self.last_frame_at - self.FPS_WINDOW_SECONDS
        while self._frame_times and self._frame_times[0] < cutoff:
            self._frame_times.popleft()
        if self.last_frame_at - start > 0.08:
            self._dropped_frames += 1
        self.last_error = None

    def status(self) -> dict[str, Any]:
        age_ms = None
        if self.last_frame_at is not None:
            age_ms = round(max(0.0, (time.monotonic() - self.last_frame_at) * 1000.0), 3)
        fps = 0.0
        if len(self._frame_times) >= 2:
            elapsed = max(self._frame_times[-1] - self._frame_times[0], 0.001)
            fps = round((len(self._frame_times) - 1) / elapsed, 3)
        return {
            "enabled": True,
            "framesWritten": self.frames_written,
            "receivedFps": fps,
            "decodedFps": fps,
            "virtualCameraFps": fps,
            "latestFramePath": str(self.latest_frame_path),
            "latestFrameAgeMs": age_ms,
            "droppedFrames": self._dropped_frames,
            "lastError": self.last_error,
        }


async def _consume_video_track(track: Any, sink: FrameFileVideoSink, warnings: list[str]) -> None:
    sequence = 0
    while True:
        try:
            frame = await track.recv()
            if not sink.should_accept_frame():
                continue
            sequence += 1
            array = frame.to_ndarray(format="bgr24")
            height, width = int(array.shape[0]), int(array.shape[1])
            await asyncio.to_thread(
                sink.write_raw_frame,
                sequence=sequence,
                width=width,
                height=height,
                pixel_format="bgr24",
                raw=array.tobytes(),
            )
        except Exception as exc:
            summary = _exception_summary(exc)
            sink.last_error = summary
            warnings.append(f"video track consume stopped: {summary}")
            return


def _atomic_write(path: Path, payload: bytes) -> None:
    last_error: OSError | None = None
    for attempt in range(6):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
        try:
            tmp.write_bytes(payload)
            tmp.replace(path)
            return
        except OSError as exc:
            last_error = exc
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if getattr(exc, "winerror", None) not in {5, 32}:
                raise
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _encode_bmp(width: int, height: int, raw: bytes, pixel_format: str) -> bytes:
    channels = {"rgb24": 3, "bgr24": 3, "bgra32": 4, "rgba32": 4}[pixel_format]
    expected = width * height * channels
    if len(raw) != expected:
        raise ValueError(f"raw frame size mismatch: expected {expected}, got {len(raw)}")

    if pixel_format == "bgr24":
        row_bytes = width * 3
        padding = (4 - (row_bytes % 4)) % 4
        if padding:
            rows = [raw[offset : offset + row_bytes] + (b"\x00" * padding) for offset in range(0, len(raw), row_bytes)]
            pixel_payload = b"".join(rows)
        else:
            pixel_payload = raw
        bits_per_pixel = 24
    else:
        pixel_bytes = bytearray(width * height * 4)
        src = 0
        dst = 0
        for _ in range(width * height):
            if pixel_format == "rgb24":
                r, g, b = raw[src], raw[src + 1], raw[src + 2]
                src += 3
            elif pixel_format == "bgra32":
                b, g, r = raw[src], raw[src + 1], raw[src + 2]
                src += 4
            else:
                r, g, b = raw[src], raw[src + 1], raw[src + 2]
                src += 4
            pixel_bytes[dst : dst + 4] = bytes((b, g, r, 255))
            dst += 4
        pixel_payload = bytes(pixel_bytes)
        bits_per_pixel = 32

    dib_header_size = 40
    pixel_offset = 14 + dib_header_size
    image_size = len(pixel_payload)
    file_size = pixel_offset + image_size
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        dib_header_size,
        width,
        -height,
        1,
        bits_per_pixel,
        0,
        image_size,
        2835,
        2835,
        0,
        0,
    )
    return file_header + dib_header + pixel_payload


def main() -> int:
    args = build_parser().parse_args()
    if args.command not in {"webrtc-duplex", "webrtc_duplex", "start"}:
        print(json.dumps({"ok": False, "error": f"Unknown command: {args.command}"}, indent=2))
        return 1
    payload = asyncio.run(run_duplex(args))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
