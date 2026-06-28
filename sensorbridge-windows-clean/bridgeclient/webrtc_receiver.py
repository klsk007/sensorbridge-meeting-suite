from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from bridgeclient.models import (
    JsonDict,
    VideoFrame,
    WebRTCIceCandidate,
    WebRTCReceiverStats,
    WebRTCSessionDescription,
    WebRTCSignalingResult,
    WebRTCStatus,
)


class WebRTCSignalingClient(Protocol):
    def status(self) -> WebRTCStatus:
        ...

    def send_offer(self, description: WebRTCSessionDescription) -> WebRTCSignalingResult:
        ...

    def send_answer(self, description: WebRTCSessionDescription) -> WebRTCSignalingResult:
        ...

    def send_ice_candidate(self, candidate: WebRTCIceCandidate) -> WebRTCSignalingResult:
        ...


class WebRTCPeerConnectionRuntime(Protocol):
    def status(self) -> JsonDict:
        ...

    def create_offer(self) -> JsonDict:
        ...

    def apply_answer(self, description: WebRTCSessionDescription) -> JsonDict:
        ...

    def add_ice_candidate(self, candidate: WebRTCIceCandidate) -> JsonDict:
        ...

    def local_ice_candidates(self) -> list[JsonDict]:
        ...

    def reset_connection(self) -> JsonDict:
        ...


class WebRTCDecodedVideoFrameSink(Protocol):
    def status(self) -> JsonDict:
        ...


class OptionalAiortcPeerConnectionRuntime:
    """Optional aiortc receiver runtime.

    When aiortc is installed, this runtime can create a receive-only video offer,
    apply an answer, accept trickle ICE, and write decoded frames into the camera
    sink using a bounded newest-frame-wins queue.
    """

    BENCHMARK_WINDOW_S = 2.0

    def __init__(self, video_sink: Any | None = None) -> None:
        self.available = importlib.util.find_spec("aiortc") is not None
        self._video_sink = video_sink
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pc: Any | None = None
        self._started_at = time.monotonic()
        self._last_video_frame_at: float | None = None
        self._local_description_type: str | None = None
        self._remote_description_type: str | None = None
        self._ice_candidates_added = 0
        self._local_ice_candidates: list[JsonDict] = []
        self._local_ice_candidate_keys: set[str] = set()
        self._ice_gathering_state = "unavailable" if not self.available else "new"
        self._signaling_state = "unavailable" if not self.available else "stable"
        self._video_frames_received = 0
        self._video_frames_decoded = 0
        self._video_received_times: deque[float] = deque()
        self._video_decoded_times: deque[float] = deque()
        self._video_width: int | None = None
        self._video_height: int | None = None
        self._video_sink_frames = 0
        self._video_sink_started_at = time.monotonic()
        self._video_sink_times: deque[float] = deque()
        self._video_pipeline_latency_ms: deque[float] = deque()
        self._video_pipeline_latency_times: deque[float] = deque()
        self._video_sink_write_ms: deque[float] = deque()
        self._video_sink_write_times: deque[float] = deque()
        self._last_video_sink_frame_at: float | None = None
        self._video_sink_last_error: str | None = None
        self._last_error: str | None = None
        self._peer_connection_state = "unavailable" if not self.available else "not_created"
        self._ice_connection_state = "not_connected"
        self._last_cpu_sample_monotonic: float | None = None
        self._last_cpu_sample_process_time: float | None = None
        self._receiver_cpu_percent: float | None = None
        self._dropped_frames = 0
        self._sink_queue: queue.Queue[JsonDict | None] = queue.Queue(maxsize=1)
        self._sink_stop_event = threading.Event()
        self._sink_thread: threading.Thread | None = None
        if self.available:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, name="SensorBridgeWebRTC", daemon=True)
            self._thread.start()
        if self._video_sink is not None:
            self._sink_thread = threading.Thread(target=self._video_sink_writer_loop, name="SensorBridgeVideoSink", daemon=True)
            self._sink_thread.start()

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro: Any) -> JsonDict:
        if not self.available or self._loop is None:
            return self._missing_dependency()
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=15)
        except Exception as exc:  # pragma: no cover - defensive runtime boundary.
            with self._lock:
                self._last_error = str(exc)
            return {"ok": False, "error": {"code": "aiortc_runtime_error", "message": str(exc)}}

    async def _ensure_peer_connection(self) -> Any:
        if self._pc is not None:
            return self._pc
        from aiortc import RTCConfiguration, RTCPeerConnection

        from aiortc import RTCRtpSender

        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
        video_transceiver = pc.addTransceiver("video", direction="recvonly")
        self._prefer_codecs(video_transceiver, RTCRtpSender.getCapabilities("video").codecs, "H264")

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            with self._lock:
                self._peer_connection_state = str(pc.connectionState)

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            with self._lock:
                self._ice_connection_state = str(pc.iceConnectionState)

        @pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange() -> None:
            with self._lock:
                self._ice_gathering_state = str(pc.iceGatheringState)
            self._record_local_ice_candidates(getattr(pc.localDescription, "sdp", "") if pc.localDescription else "")

        @pc.on("signalingstatechange")
        async def on_signalingstatechange() -> None:
            with self._lock:
                self._signaling_state = str(pc.signalingState)

        @pc.on("track")
        def on_track(track: Any) -> None:
            assert self._loop is not None
            self._loop.create_task(self._consume_track(track))

        self._pc = pc
        with self._lock:
            self._peer_connection_state = str(pc.connectionState)
            self._ice_connection_state = str(pc.iceConnectionState)
            self._ice_gathering_state = str(pc.iceGatheringState)
            self._signaling_state = str(pc.signalingState)
        return pc

    @staticmethod
    def _prefer_codecs(transceiver: Any, codecs: list[Any], preferred_name: str) -> None:
        preferred = [codec for codec in codecs if preferred_name.lower() in str(getattr(codec, "mimeType", "")).lower()]
        others = [codec for codec in codecs if codec not in preferred]
        if preferred:
            transceiver.setCodecPreferences(preferred + others)

    def _record_local_ice_candidates(self, sdp: str) -> None:
        if not sdp:
            return
        candidates: list[JsonDict] = []
        current_mid: str | None = None
        current_mline_index = -1
        for raw_line in sdp.splitlines():
            line = raw_line.strip()
            if line.startswith("m="):
                current_mline_index += 1
            elif line.startswith("a=mid:"):
                current_mid = line.removeprefix("a=mid:")
            elif line.startswith("a=candidate:"):
                candidate = line.removeprefix("a=")
                key = f"{current_mid}|{current_mline_index}|{candidate}"
                if key not in self._local_ice_candidate_keys:
                    candidates.append(
                        {
                            "candidate": candidate,
                            "sdpMid": current_mid,
                            "sdpMLineIndex": current_mline_index if current_mline_index >= 0 else None,
                        }
                    )
                    self._local_ice_candidate_keys.add(key)
        if candidates:
            self._local_ice_candidates.extend(candidates)

    async def _consume_track(self, track: Any) -> None:
        while True:
            try:
                frame = await track.recv()
                now = time.monotonic()
                with self._lock:
                    if getattr(track, "kind", "") == "video":
                        self._video_frames_received += 1
                        self._video_frames_decoded += 1
                        self._video_received_times.append(now)
                        self._video_decoded_times.append(now)
                        self._trim_benchmark_windows_locked(now)
                        decoded_sequence = self._video_frames_decoded
                        self._video_width = getattr(frame, "width", self._video_width)
                        self._video_height = getattr(frame, "height", self._video_height)
                        self._last_video_frame_at = now
                    else:
                        decoded_sequence = 0
                if getattr(track, "kind", "") == "video":
                    self._enqueue_decoded_video_frame(frame, decoded_sequence, now)
            except Exception as exc:  # pragma: no cover - depends on runtime track lifecycle.
                with self._lock:
                    self._last_error = str(exc)
                return

    def _enqueue_decoded_video_frame(self, frame: Any, sequence: int, received_at_monotonic: float) -> None:
        if self._video_sink is None:
            return
        try:
            array = frame.to_ndarray(format="bgr24")
            height, width = int(array.shape[0]), int(array.shape[1])
            item: JsonDict = {
                "sequence": sequence,
                "timestamp_ns": time.time_ns(),
                "received_at_monotonic": received_at_monotonic,
                "width": width,
                "height": height,
                "raw": array.tobytes(),
            }
            try:
                self._sink_queue.put_nowait(item)
            except queue.Full:
                try:
                    self._sink_queue.get_nowait()
                except queue.Empty:
                    pass
                with self._lock:
                    self._dropped_frames += 1
                self._sink_queue.put_nowait(item)
        except Exception as exc:  # pragma: no cover - depends on av frame formats and sink IO.
            with self._lock:
                self._video_sink_last_error = str(exc)

    def _video_sink_writer_loop(self) -> None:
        while not self._sink_stop_event.is_set():
            try:
                item = self._sink_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                continue
            self._write_raw_video_sink_item(item)

    def _write_raw_video_sink_item(self, item: JsonDict) -> None:
        if self._video_sink is None:
            return
        write_started = time.monotonic()
        raw = item["raw"]
        try:
            if hasattr(self._video_sink, "write_raw_frame"):
                self._video_sink.write_raw_frame(
                    sequence=int(item["sequence"]),
                    timestamp_ns=int(item["timestamp_ns"]),
                    width=int(item["width"]),
                    height=int(item["height"]),
                    pixel_format="BGR24",
                    raw=raw,
                    metadata={"source": "webrtc", "receiver_runtime": "aiortc"},
                )
            else:
                video_frame = VideoFrame(
                    sequence=int(item["sequence"]),
                    timestamp_ns=int(item["timestamp_ns"]),
                    width=int(item["width"]),
                    height=int(item["height"]),
                    pixel_format="BGR24",
                    data_base64=base64.b64encode(raw).decode("ascii"),
                    raw={"source": "webrtc", "receiver_runtime": "aiortc"},
                )
                self._video_sink.write_frame(video_frame)
            with self._lock:
                self._video_sink_frames += 1
                now = time.monotonic()
                self._last_video_sink_frame_at = now
                self._video_sink_times.append(now)
                self._video_pipeline_latency_times.append(now)
                self._video_pipeline_latency_ms.append(max((now - float(item["received_at_monotonic"])) * 1000.0, 0.0))
                self._video_sink_write_times.append(now)
                self._video_sink_write_ms.append(max((now - write_started) * 1000.0, 0.0))
                self._trim_benchmark_windows_locked(now)
                self._video_sink_last_error = None
        except Exception as exc:  # pragma: no cover - depends on sink IO.
            with self._lock:
                self._video_sink_last_error = str(exc)

    def create_offer(self) -> JsonDict:
        if not self.available:
            return self._missing_dependency()
        return self._run(self._create_offer())

    async def _create_offer(self) -> JsonDict:
        if self._pc is not None and str(getattr(self._pc, "connectionState", "")) in {"closed", "failed"}:
            await self._reset_connection()
        pc = await self._ensure_peer_connection()
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        local = pc.localDescription
        with self._lock:
            self._local_description_type = getattr(local, "type", None)
            self._peer_connection_state = str(pc.connectionState)
            self._ice_connection_state = str(pc.iceConnectionState)
            self._ice_gathering_state = str(pc.iceGatheringState)
            self._signaling_state = str(pc.signalingState)
            self._record_local_ice_candidates(getattr(local, "sdp", ""))
        return {
            "ok": True,
            "command": "webrtc_receiver_create_offer",
            "signaling_only": True,
            "media_connected": False,
            "localDescription": {
                "type": getattr(local, "type", "offer"),
                "sdp": getattr(local, "sdp", ""),
            },
            "localIceCandidates": self.local_ice_candidates(),
            "truth": "Offer generation is signaling only; real media requires received and decoded frames.",
        }

    def apply_answer(self, description: WebRTCSessionDescription) -> JsonDict:
        if not self.available:
            return self._missing_dependency()
        return self._run(self._apply_answer(description))

    async def _apply_answer(self, description: WebRTCSessionDescription) -> JsonDict:
        from aiortc import RTCSessionDescription

        pc = await self._ensure_peer_connection()
        await pc.setRemoteDescription(RTCSessionDescription(sdp=description.sdp, type=description.type))
        with self._lock:
            self._remote_description_type = description.type
            self._peer_connection_state = str(pc.connectionState)
            self._ice_connection_state = str(pc.iceConnectionState)
            self._ice_gathering_state = str(pc.iceGatheringState)
            self._signaling_state = str(pc.signalingState)
        return {
            "ok": True,
            "command": "webrtc_receiver_apply_answer",
            "signaling_only": True,
            "media_connected": False,
        }

    def add_ice_candidate(self, candidate: WebRTCIceCandidate) -> JsonDict:
        if not self.available:
            return self._missing_dependency()
        return self._run(self._add_ice_candidate(candidate))

    async def _add_ice_candidate(self, candidate: WebRTCIceCandidate) -> JsonDict:
        from aiortc.sdp import candidate_from_sdp

        pc = await self._ensure_peer_connection()
        parsed = candidate_from_sdp(candidate.candidate)
        parsed.sdpMid = candidate.sdp_mid
        parsed.sdpMLineIndex = candidate.sdp_mline_index
        await pc.addIceCandidate(parsed)
        with self._lock:
            self._ice_candidates_added += 1
            self._peer_connection_state = str(pc.connectionState)
            self._ice_connection_state = str(pc.iceConnectionState)
            self._ice_gathering_state = str(pc.iceGatheringState)
            self._signaling_state = str(pc.signalingState)
        return {
            "ok": True,
            "command": "webrtc_receiver_add_ice_candidate",
            "signaling_only": True,
            "media_connected": False,
            "ice_candidates_added": self._ice_candidates_added,
        }

    def status(self) -> JsonDict:
        if not self.available:
            return self._missing_dependency()
        with self._lock:
            now = time.monotonic()
            self._update_cpu_sample_locked(now)
            self._trim_benchmark_windows_locked(now)
            elapsed = max(now - self._started_at, 0.001)
            sink_elapsed = max(now - self._video_sink_started_at, 0.001)
            received_fps = self._window_fps_locked(self._video_received_times) or (self._video_frames_received / elapsed)
            decoded_fps = self._window_fps_locked(self._video_decoded_times) or (self._video_frames_decoded / elapsed)
            virtual_camera_fps = (
                self._window_fps_locked(self._video_sink_times)
                or (self._video_sink_frames / sink_elapsed if self._video_sink_frames else 0.0)
            )
            media_connected = self._video_frames_decoded > 0
            latest_frame_age_ms = (
                max((now - self._last_video_frame_at) * 1000.0, 0.0)
                if self._last_video_frame_at is not None
                else None
            )
            receiver_resolution = (
                f"{self._video_width}x{self._video_height}"
                if self._video_width is not None and self._video_height is not None
                else None
            )
            benchmark_sample_count = len(self._video_decoded_times) or None
            benchmark_window_ms = self._benchmark_window_ms_locked(self._video_decoded_times)
            latency_percentiles = self._latency_percentiles_locked()
            frame_file_write_percentiles = self._frame_file_write_percentiles_locked()
            return {
                "available": True,
                "component": "peer_connection",
                "runtime_name": "aiortc",
                "runtime_state": "available",
                "peer_connection_state": self._peer_connection_state,
                "ice_state": self._ice_connection_state,
                "ice_gathering_state": self._ice_gathering_state,
                "signaling_state": self._signaling_state,
                "local_description_type": self._local_description_type,
                "remote_description_type": self._remote_description_type,
                "ice_candidates_added": self._ice_candidates_added,
                "local_ice_candidates_generated": len(self._local_ice_candidates),
                "local_ice_candidates_pending": len(self._local_ice_candidates),
                "video_frames_received": self._video_frames_received,
                "video_frames_decoded": self._video_frames_decoded,
                "video_width": self._video_width,
                "video_height": self._video_height,
                "decoded_video_frame_sink": {
                    "available": self._video_sink is not None,
                    "component": "decoded_video_frame_sink",
                    "route": "frame_file_virtual_camera_input" if self._video_sink is not None else "not_configured",
                    "frames_written": self._video_sink_frames,
                    "fps": virtual_camera_fps,
                    "queue_policy": "bounded_newest_frame_wins",
                    "queue_max_size": self._sink_queue.maxsize,
                    "write_p50_ms": frame_file_write_percentiles.get("frame_file_write_p50_ms"),
                    "write_p90_ms": frame_file_write_percentiles.get("frame_file_write_p90_ms"),
                    "write_p99_ms": frame_file_write_percentiles.get("frame_file_write_p99_ms"),
                    "write_samples": frame_file_write_percentiles.get("frame_file_write_samples"),
                    "latest_frame_at_monotonic": self._last_video_sink_frame_at,
                    "last_error": self._video_sink_last_error,
                    "completion_truth": "Frame-file writes feed the SensorBridge camera route, but normal app visibility still requires the DirectShow/provider path to be running and verified.",
                },
                "active_camera_transport": "webrtc",
                "received_fps": received_fps,
                "decoded_fps": decoded_fps,
                "virtual_camera_fps": virtual_camera_fps,
                "latest_frame_age_ms": latest_frame_age_ms,
                "receiver_resolution": receiver_resolution,
                "benchmark_window_ms": benchmark_window_ms,
                "benchmark_sample_count": benchmark_sample_count,
                "receiver_cpu_percent": self._receiver_cpu_percent,
                "estimated_latency_ms": latency_percentiles.get("estimated_latency_ms"),
                "latency_p50_ms": latency_percentiles.get("latency_p50_ms"),
                "latency_p90_ms": latency_percentiles.get("latency_p90_ms"),
                "latency_p99_ms": latency_percentiles.get("latency_p99_ms"),
                **frame_file_write_percentiles,
                "media_connected": media_connected,
                "last_video_frame_at_monotonic": self._last_video_frame_at,
                "dropped_frames": self._dropped_frames,
                "last_error": self._last_error,
                "real_media": media_connected,
            }

    def _trim_benchmark_windows_locked(self, now: float) -> None:
        cutoff = now - self.BENCHMARK_WINDOW_S
        for values in (
            self._video_received_times,
            self._video_decoded_times,
            self._video_sink_times,
            self._video_pipeline_latency_times,
            self._video_sink_write_times,
        ):
            while values and values[0] < cutoff:
                values.popleft()
        while len(self._video_pipeline_latency_ms) > len(self._video_pipeline_latency_times):
            self._video_pipeline_latency_ms.popleft()
        while len(self._video_sink_write_ms) > len(self._video_sink_write_times):
            self._video_sink_write_ms.popleft()

    def _window_fps_locked(self, timestamps: deque[float]) -> float | None:
        if len(timestamps) < 2:
            return None
        span = max(timestamps[-1] - timestamps[0], 0.001)
        return (len(timestamps) - 1) / span

    def _benchmark_window_ms_locked(self, timestamps: deque[float]) -> float | None:
        if len(timestamps) < 2:
            return None
        return max((timestamps[-1] - timestamps[0]) * 1000.0, 0.0)

    def _latency_percentiles_locked(self) -> JsonDict:
        if not self._video_pipeline_latency_ms:
            return {}
        values = sorted(float(value) for value in self._video_pipeline_latency_ms)
        return {
            "estimated_latency_ms": values[-1],
            "latency_p50_ms": _percentile(values, 50),
            "latency_p90_ms": _percentile(values, 90),
            "latency_p99_ms": _percentile(values, 99),
        }

    def _frame_file_write_percentiles_locked(self) -> JsonDict:
        if not self._video_sink_write_ms:
            return {}
        values = sorted(float(value) for value in self._video_sink_write_ms)
        return {
            "frame_file_write_p50_ms": _percentile(values, 50),
            "frame_file_write_p90_ms": _percentile(values, 90),
            "frame_file_write_p99_ms": _percentile(values, 99),
            "frame_file_write_samples": len(values),
        }

    def _update_cpu_sample_locked(self, now: float) -> None:
        process_time = time.process_time()
        previous_now = self._last_cpu_sample_monotonic
        previous_process_time = self._last_cpu_sample_process_time
        self._last_cpu_sample_monotonic = now
        self._last_cpu_sample_process_time = process_time
        if previous_now is None or previous_process_time is None:
            return
        elapsed = now - previous_now
        if elapsed <= 0:
            return
        cpu_count = os.cpu_count() or 1
        cpu_percent = ((process_time - previous_process_time) / elapsed) * 100.0 / cpu_count
        self._receiver_cpu_percent = max(cpu_percent, 0.0)

    @staticmethod
    def _missing_dependency() -> JsonDict:
        return {
            "ok": False,
            "available": False,
            "component": "peer_connection",
            "runtime_name": "aiortc",
            "runtime_state": "python_aiortc_not_installed",
            "reason": "Install optional user-mode Python dependency aiortc to generate offers and receive WebRTC media.",
            "install_hint": "py -3.12 -m pip install aiortc",
            "real_media": False,
        }

    def local_ice_candidates(self) -> list[JsonDict]:
        with self._lock:
            return [dict(candidate) for candidate in self._local_ice_candidates]

    def reset_connection(self) -> JsonDict:
        if not self.available:
            return self._missing_dependency()
        return self._run(self._reset_connection())

    async def _reset_connection(self) -> JsonDict:
        pc = self._pc
        self._pc = None
        if pc is not None:
            await pc.close()
        with self._lock:
            self._last_video_frame_at = None
            self._local_description_type = None
            self._remote_description_type = None
            self._ice_candidates_added = 0
            self._local_ice_candidates = []
            self._local_ice_candidate_keys = set()
            self._ice_gathering_state = "new"
            self._signaling_state = "stable"
            self._peer_connection_state = "not_created"
            self._ice_connection_state = "not_connected"
            self._last_error = None
            self._video_received_times.clear()
            self._video_decoded_times.clear()
            self._video_sink_times.clear()
            self._video_pipeline_latency_ms.clear()
            self._video_pipeline_latency_times.clear()
            self._video_sink_write_ms.clear()
            self._video_sink_write_times.clear()
        return {"ok": True, "command": "webrtc_receiver_reset_connection"}


@dataclass
class WebRTCReceiverRuntime:
    """Windows-side WebRTC receiver boundary.

    This phase intentionally exposes readiness without pretending WebRTC media is
    connected. A future runtime can plug in aiortc, libdatachannel, GStreamer, or
    another peer-connection implementation behind these same boundaries.
    """

    native_runtime_linked: bool = False
    peer_runtime_name: str | None = None
    peer_connection: WebRTCPeerConnectionRuntime | None = None
    video_sink: WebRTCDecodedVideoFrameSink | None = None
    normal_app_camera_visible: bool | None = None
    fallback_reason: str = "webrtc_receiver_unavailable"
    next_action: str = "integrate_aiortc_libdatachannel_or_gstreamer_receiver_runtime"
    extra: dict[str, Any] = field(default_factory=dict)

    def status(self, upstream_status: WebRTCStatus | None = None) -> JsonDict:
        upstream = upstream_status.to_json() if upstream_status is not None else {}
        native_runtime_linked = self.native_runtime_linked and bool(
            upstream_status.native_runtime_linked if upstream_status is not None else True
        )
        peer_status = self.peer_connection.status() if self.peer_connection else self._unavailable("peer_connection")
        local_receiver_unavailable = not bool(peer_status.get("available")) if isinstance(peer_status, dict) else True
        fallback_reason = "webrtc_receiver_unavailable" if local_receiver_unavailable else None
        transport_mode = (
            upstream_status.transport_mode
            if upstream_status is not None and upstream_status.transport_mode
            else "webrtc"
        )
        next_action = (
            upstream_status.next_action
            if upstream_status is not None and upstream_status.next_action
            else self.next_action
        )
        receiver_received_fps = peer_status.get("received_fps") if isinstance(peer_status, dict) else None
        receiver_decoded_fps = peer_status.get("decoded_fps") if isinstance(peer_status, dict) else None
        receiver_media_connected = bool(peer_status.get("media_connected")) if isinstance(peer_status, dict) else False
        upstream_camera_ready = bool(
            upstream_status
            and (
                upstream_status.media_connected
                or upstream_status.camera_track_ready
                or upstream_status.real_ipad_camera
            )
        )
        media_connected = bool(receiver_media_connected and (upstream_status is None or upstream_camera_ready))
        virtual_camera_fps = (
            peer_status.get("virtual_camera_fps")
            if isinstance(peer_status, dict) and peer_status.get("virtual_camera_fps") is not None
            else (upstream_status.virtual_camera_fps if upstream_status else None)
        )
        normal_app_camera_visible = (
            self.normal_app_camera_visible
            if self.normal_app_camera_visible is not None
            else (upstream_status.normal_app_camera_visible if upstream_status else None)
        )
        normal_app_camera_blocked = normal_app_camera_visible is False and _number_or_zero(virtual_camera_fps) > 0
        real_ipad_camera = upstream_status.real_ipad_camera if upstream_status else None
        real_ipad_camera_blocked = real_ipad_camera is False
        real_ipad_media_bottleneck = "waiting_for_real_ipad_camera" if real_ipad_camera_blocked else None
        sender_stats_fresh = upstream_status.sender_stats_fresh if upstream_status else None
        sender_stats_stale = sender_stats_fresh is False or (
            upstream_status is not None and upstream_status.ipad_video_state == "sender_stats_stale"
        )
        receiver_stats_fresh = upstream_status.windows_receiver_stats_fresh if upstream_status else None
        receiver_stats_stale = receiver_stats_fresh is False
        upstream_product_ready = bool(upstream_status.product_ready) if upstream_status and upstream_status.product_ready is not None else False
        product_ready = bool(
            upstream_product_ready
            and not real_ipad_camera_blocked
            and not sender_stats_stale
            and not receiver_stats_stale
            and _number_or_zero(virtual_camera_fps) > 0
            and not normal_app_camera_blocked
        )
        product_readiness = upstream_status.product_readiness if upstream_status and upstream_status.product_readiness else None
        product_incomplete_reason = (
            upstream_status.product_incomplete_reason
            if upstream_status and upstream_status.product_incomplete_reason
            else self._product_incomplete_reason(
                fallback_reason=fallback_reason,
                real_ipad_camera_blocked=real_ipad_camera_blocked,
                sender_stats_stale=sender_stats_stale,
                receiver_stats_stale=receiver_stats_stale,
                normal_app_camera_blocked=normal_app_camera_blocked,
                receiver_media_connected=receiver_media_connected,
                virtual_camera_fps=virtual_camera_fps,
            )
        )
        if product_readiness is None:
            product_readiness = "complete" if product_ready else ("partial" if receiver_media_connected else "incomplete")
        elif product_readiness == "complete" and not product_ready:
            product_readiness = "partial" if receiver_media_connected else "incomplete"
        performance_target_fps = upstream_status.performance_target_fps if upstream_status else None
        performance_target_latency_ms = upstream_status.performance_target_latency_ms if upstream_status else None
        performance_measured_fps = (
            upstream_status.performance_measured_fps
            if upstream_status and upstream_status.performance_measured_fps is not None
            else virtual_camera_fps
        )
        performance_measured_latency_ms = upstream_status.performance_measured_latency_ms if upstream_status else None
        if performance_measured_latency_ms is None and isinstance(peer_status, dict):
            performance_measured_latency_ms = peer_status.get("latency_p90_ms") or peer_status.get("estimated_latency_ms")
        receiver_resolution = (
            peer_status.get("receiver_resolution")
            if isinstance(peer_status, dict) and peer_status.get("receiver_resolution") is not None
            else (upstream_status.receiver_resolution if upstream_status else None)
        )
        benchmark_window_ms = (
            peer_status.get("benchmark_window_ms")
            if isinstance(peer_status, dict) and peer_status.get("benchmark_window_ms") is not None
            else (upstream_status.benchmark_window_ms if upstream_status else None)
        )
        benchmark_sample_count = (
            peer_status.get("benchmark_sample_count")
            if isinstance(peer_status, dict) and peer_status.get("benchmark_sample_count") is not None
            else (upstream_status.benchmark_sample_count if upstream_status else None)
        )
        receiver_cpu_percent = (
            peer_status.get("receiver_cpu_percent")
            if isinstance(peer_status, dict) and peer_status.get("receiver_cpu_percent") is not None
            else (upstream_status.receiver_cpu_percent if upstream_status else None)
        )
        benchmark_bottleneck = self._benchmark_context_bottleneck(
            receiver_resolution=receiver_resolution,
            requested_resolution=upstream_status.requested_resolution if upstream_status else None,
            benchmark_window_ms=benchmark_window_ms,
            benchmark_sample_count=benchmark_sample_count,
            performance_target_fps=performance_target_fps,
            performance_target_latency_ms=performance_target_latency_ms,
            performance_measured_fps=performance_measured_fps,
            performance_measured_latency_ms=performance_measured_latency_ms,
        )
        performance_latency_source = (
            upstream_status.performance_latency_source
            if upstream_status and upstream_status.performance_latency_source
            else ("windows_estimated_latency" if performance_measured_latency_ms is not None else "not_reported")
        )
        performance_target_met = upstream_status.performance_target_met if upstream_status else None
        if sender_stats_stale or receiver_stats_stale:
            performance_target_met = False
        if real_ipad_media_bottleneck:
            performance_target_met = False
        if normal_app_camera_blocked:
            performance_target_met = False
        if benchmark_bottleneck:
            performance_target_met = False
        if performance_target_met is None:
            performance_target_met = self._performance_target_met(
                performance_target_fps=performance_target_fps,
                performance_target_latency_ms=performance_target_latency_ms,
                performance_measured_fps=performance_measured_fps,
                performance_measured_latency_ms=performance_measured_latency_ms,
            )
        if receiver_stats_stale:
            performance_readiness = "stale_receiver_stats"
            performance_bottleneck = "windows_receiver_stats_stale"
        elif sender_stats_stale:
            performance_readiness = "stale_sender_stats"
            performance_bottleneck = "ipad_sender_stats_stale"
        elif real_ipad_media_bottleneck:
            performance_readiness = "waiting_for_real_ipad_media"
            performance_bottleneck = real_ipad_media_bottleneck
        elif normal_app_camera_blocked:
            performance_readiness = "incomplete"
            performance_bottleneck = "windows_camera_not_visible_to_normal_app"
        elif benchmark_bottleneck:
            performance_readiness = "insufficient_benchmark_context"
            performance_bottleneck = benchmark_bottleneck
        else:
            performance_readiness = (
                upstream_status.performance_readiness
                if upstream_status and upstream_status.performance_readiness
                else ("complete" if performance_target_met else ("partial" if receiver_media_connected else "incomplete"))
            )
            performance_bottleneck = (
                upstream_status.performance_bottleneck
                if upstream_status and upstream_status.performance_bottleneck
                else self._performance_bottleneck(
                    performance_target_fps=performance_target_fps,
                    performance_target_latency_ms=performance_target_latency_ms,
                    performance_measured_fps=performance_measured_fps,
                    performance_measured_latency_ms=performance_measured_latency_ms,
                )
            )
        return {
            "ok": True,
            "phase": "windows_webrtc_receiver_phase_1_status_and_signaling",
            "complete": product_ready,
            "product_ready": product_ready,
            "product_readiness": product_readiness,
            "product_incomplete_reason": product_incomplete_reason,
            "ipad_video_state": upstream_status.ipad_video_state if upstream_status else None,
            "windows_video_state": upstream_status.windows_video_state if upstream_status else ("decoded" if receiver_decoded_fps else "not_receiving"),
            "virtual_camera_state": upstream_status.virtual_camera_state if upstream_status else ("delivering" if _number_or_zero(virtual_camera_fps) > 0 else "not_delivering"),
            "real_ipad_camera": real_ipad_camera,
            "real_ipad_media": {
                "camera": real_ipad_camera,
                "bottleneck": real_ipad_media_bottleneck,
                "meaning": "Only real iPad camera sources can satisfy WebRTC camera product readiness; simulator/mock/synthetic sources are incomplete.",
            },
            "normal_app_camera_visible": normal_app_camera_visible,
            "normal_windows_camera_visible": normal_app_camera_visible,
            "normal_app_camera_visibility": {
                "visible": normal_app_camera_visible,
                "blocked": normal_app_camera_blocked,
                "meaning": "Provider or frame-file output is not enough; true requires a normal Windows camera consumer to see SensorBridge Camera.",
            },
            "product_readiness_evidence": {
                "product_ready": product_ready,
                "readiness": product_readiness,
                "incomplete_reason": product_incomplete_reason,
                "meaning": "Product readiness is the top-level WebRTC virtual-device verdict; sender parameters and sent FPS are only iPad-side evidence.",
            },
            "performance_target_fps": performance_target_fps,
            "performance_target_latency_ms": performance_target_latency_ms,
            "performance_measured_fps": performance_measured_fps,
            "performance_measured_latency_ms": performance_measured_latency_ms,
            "performance_latency_source": performance_latency_source,
            "performance_target_met": performance_target_met,
            "performance_readiness": performance_readiness,
            "performance_bottleneck": performance_bottleneck,
            "benchmark_context_required": True,
            "benchmark_context_bottleneck": benchmark_bottleneck,
            "windows_receiver_stats_age_ms": upstream_status.windows_receiver_stats_age_ms if upstream_status else None,
            "windows_receiver_stats_fresh_window_ms": upstream_status.windows_receiver_stats_fresh_window_ms if upstream_status else None,
            "windows_receiver_stats_fresh": receiver_stats_fresh,
            "windows_receiver_stats_freshness": {
                "fresh": receiver_stats_fresh,
                "age_ms": upstream_status.windows_receiver_stats_age_ms if upstream_status else None,
                "fresh_window_ms": upstream_status.windows_receiver_stats_fresh_window_ms if upstream_status else None,
                "meaning": "Only fresh Windows receiver stats are current product/performance evidence.",
            },
            "last_sender_stats_at": upstream_status.last_sender_stats_at if upstream_status else None,
            "sender_stats_age_ms": upstream_status.sender_stats_age_ms if upstream_status else None,
            "sender_stats_fresh_window_ms": upstream_status.sender_stats_fresh_window_ms if upstream_status else None,
            "sender_stats_fresh": sender_stats_fresh,
            "ipad_sender_stats_freshness": {
                "fresh": sender_stats_fresh,
                "age_ms": upstream_status.sender_stats_age_ms if upstream_status else None,
                "fresh_window_ms": upstream_status.sender_stats_fresh_window_ms if upstream_status else None,
                "last_at": upstream_status.last_sender_stats_at if upstream_status else None,
                "meaning": "Only fresh iPad sender stats make sentFps current sending evidence.",
            },
            "performance_target_evidence": {
                "target_fps": performance_target_fps,
                "target_latency_ms": performance_target_latency_ms,
                "measured_fps": performance_measured_fps,
                "measured_latency_ms": performance_measured_latency_ms,
                "latency_source": performance_latency_source,
                "target_met": performance_target_met,
                "readiness": performance_readiness,
                "bottleneck": performance_bottleneck,
                "benchmark_context_bottleneck": benchmark_bottleneck,
                "normal_app_camera_visible": normal_app_camera_visible,
                "meaning": "Performance targets use Windows virtual camera FPS, Windows/benchmark latency, and sufficient receiver benchmark context; sender FPS and senderEstimatedLatencyMs are not accepted.",
            },
            "media_connected": media_connected,
            "active_camera_transport": "webrtc",
            "transport_mode": transport_mode,
            "signaling_state": upstream_status.signaling_state if upstream_status else None,
            "ice_state": upstream_status.ice_state if upstream_status else "not_connected",
            "ice_gathering_state": upstream_status.ice_gathering_state if upstream_status else "unknown",
            "runtime_name": upstream_status.runtime_name if upstream_status else "unavailable",
            "runtime_state": upstream_status.runtime_state if upstream_status else "windows_receiver_runtime_not_integrated",
            "peer_connection_state": upstream_status.peer_connection_state if upstream_status else "not_created",
            "camera_track_ready": bool(upstream_status.camera_track_ready) if upstream_status else False,
            "ipad_local_tracks": {
                "camera_track_ready": bool(upstream_status.camera_track_ready) if upstream_status else False,
                "windows_receiving_proven": receiver_media_connected,
                "meaning": "iPad local track readiness is remote preparation only; Windows completion requires received/decoded FPS and virtual-device sink evidence.",
            },
            "local_description_type": upstream_status.local_description_type if upstream_status else None,
            "remote_description_type": upstream_status.remote_description_type if upstream_status else None,
            "local_ice_candidates_generated": upstream_status.local_ice_candidates_generated if upstream_status else 0,
            "last_local_candidate_at": upstream_status.last_local_candidate_at if upstream_status else None,
            "video_codec": upstream_status.video_codec if upstream_status else None,
            "requested_resolution": upstream_status.requested_resolution if upstream_status else None,
            "requested_fps": upstream_status.requested_fps if upstream_status else None,
            "selected_resolution": upstream_status.selected_resolution if upstream_status else None,
            "selected_fps": upstream_status.selected_fps if upstream_status else None,
            "capture_profile_resolution": upstream_status.capture_profile_resolution if upstream_status else None,
            "capture_profile_fps": upstream_status.capture_profile_fps if upstream_status else None,
            "capture_profile_supported": upstream_status.capture_profile_supported if upstream_status else None,
            "capture_profile_reason": upstream_status.capture_profile_reason if upstream_status else None,
            "capture_profile_status": self.capture_profile_status(upstream_status),
            "sender_max_framerate": upstream_status.sender_max_framerate if upstream_status else None,
            "sender_max_bitrate_bps": upstream_status.sender_max_bitrate_bps if upstream_status else None,
            "sender_min_bitrate_bps": upstream_status.sender_min_bitrate_bps if upstream_status else None,
            "sender_parameters_applied": upstream_status.sender_parameters_applied if upstream_status else None,
            "sender_parameters_reason": upstream_status.sender_parameters_reason if upstream_status else None,
            "ipad_sender_parameters": {
                "max_framerate": upstream_status.sender_max_framerate if upstream_status else None,
                "max_bitrate_bps": upstream_status.sender_max_bitrate_bps if upstream_status else None,
                "min_bitrate_bps": upstream_status.sender_min_bitrate_bps if upstream_status else None,
                "applied": upstream_status.sender_parameters_applied if upstream_status else None,
                "reason": upstream_status.sender_parameters_reason if upstream_status else None,
                "stats_fresh": sender_stats_fresh,
                "stats_age_ms": upstream_status.sender_stats_age_ms if upstream_status else None,
                "stats_fresh_window_ms": upstream_status.sender_stats_fresh_window_ms if upstream_status else None,
                "last_stats_at": upstream_status.last_sender_stats_at if upstream_status else None,
                "windows_receiving_proven": receiver_media_connected,
                "meaning": "iPad sender parameters are outbound configuration evidence only, not proof Windows received or decoded media.",
            },
            "media_degradation_reason": upstream_status.media_degradation_reason if upstream_status else None,
            "width": upstream_status.width if upstream_status else None,
            "height": upstream_status.height if upstream_status else None,
            "target_fps": upstream_status.target_fps if upstream_status else None,
            "sent_fps": upstream_status.sent_fps if upstream_status else None,
            "received_fps": receiver_received_fps if receiver_received_fps is not None else (upstream_status.received_fps if upstream_status else None),
            "decoded_fps": receiver_decoded_fps if receiver_decoded_fps is not None else (upstream_status.decoded_fps if upstream_status else None),
            "virtual_camera_fps": virtual_camera_fps,
            "receiver_resolution": receiver_resolution,
            "benchmark_window_ms": benchmark_window_ms,
            "benchmark_sample_count": benchmark_sample_count,
            "receiver_cpu_percent": receiver_cpu_percent,
            "sender_estimated_latency_ms": upstream_status.sender_estimated_latency_ms if upstream_status else None,
            "estimated_latency_ms": (
                peer_status.get("estimated_latency_ms")
                if isinstance(peer_status, dict) and peer_status.get("estimated_latency_ms") is not None
                else (upstream_status.estimated_latency_ms if upstream_status else None)
            ),
            "latest_frame_age_ms": peer_status.get("latest_frame_age_ms") if isinstance(peer_status, dict) else None,
            "latency_p50_ms": peer_status.get("latency_p50_ms") if isinstance(peer_status, dict) else None,
            "latency_p90_ms": peer_status.get("latency_p90_ms") if isinstance(peer_status, dict) else None,
            "latency_p99_ms": peer_status.get("latency_p99_ms") if isinstance(peer_status, dict) else None,
            "frame_file_write_p50_ms": peer_status.get("frame_file_write_p50_ms") if isinstance(peer_status, dict) else None,
            "frame_file_write_p90_ms": peer_status.get("frame_file_write_p90_ms") if isinstance(peer_status, dict) else None,
            "frame_file_write_p99_ms": peer_status.get("frame_file_write_p99_ms") if isinstance(peer_status, dict) else None,
            "frame_file_write_samples": peer_status.get("frame_file_write_samples") if isinstance(peer_status, dict) else None,
            "dropped_frames": (
                peer_status.get("dropped_frames")
                if isinstance(peer_status, dict) and peer_status.get("dropped_frames") is not None
                else (upstream_status.dropped_frames if upstream_status else None)
            ),
            "native_runtime_linked": native_runtime_linked,
            "fallback_reason": fallback_reason,
            "next_action": next_action,
            "peer_connection": peer_status,
            "windows_receiver": {
                "receiving": receiver_media_connected,
                "received_fps": receiver_received_fps,
                "decoded_fps": receiver_decoded_fps,
                "completion_evidence": "received_fps, decoded_fps, virtual_camera_fps, and normal app visibility",
            },
            "decoded_video_frame_sink": (
                self.video_sink.status()
                if self.video_sink
                else (
                    peer_status.get("decoded_video_frame_sink")
                    if isinstance(peer_status.get("decoded_video_frame_sink"), dict)
                    else self._unavailable("decoded_video_frame_sink")
                )
            ),
            "upstream_status": upstream,
            **self.extra,
        }

    @staticmethod
    def capture_profile_status(upstream_status: WebRTCStatus | None) -> JsonDict:
        if upstream_status is None or upstream_status.capture_profile_supported is None:
            return {
                "known": False,
                "supported": None,
                "reason": "capture_profile_not_reported_by_upstream",
                "streaming_failure": False,
            }
        return {
            "known": True,
            "supported": bool(upstream_status.capture_profile_supported),
            "resolution": upstream_status.capture_profile_resolution,
            "fps": upstream_status.capture_profile_fps,
            "reason": upstream_status.capture_profile_reason,
            "streaming_failure": False,
            "meaning": "iPad camera hardware capture profile evidence only; not proof of WebRTC media flow",
        }

    @staticmethod
    def _unavailable(component: str) -> JsonDict:
        return {
            "available": False,
            "component": component,
            "reason": "not_integrated_in_windows_phase_1",
            "real_media": False,
        }

    @staticmethod
    def _product_incomplete_reason(
        *,
        fallback_reason: Any,
        real_ipad_camera_blocked: bool,
        sender_stats_stale: bool,
        receiver_stats_stale: bool,
        normal_app_camera_blocked: bool,
        receiver_media_connected: bool,
        virtual_camera_fps: Any,
    ) -> str | None:
        if real_ipad_camera_blocked:
            return "waiting_for_real_ipad_camera"
        if sender_stats_stale:
            return "ipad_sender_stats_stale"
        if receiver_stats_stale:
            return "windows_receiver_stats_stale"
        if normal_app_camera_blocked:
            return "windows_camera_not_visible_to_normal_app"
        if fallback_reason:
            return str(fallback_reason)
        if not receiver_media_connected:
            return "windows_webrtc_media_not_received"
        if _number_or_zero(virtual_camera_fps) <= 0:
            return "virtual_camera_not_delivering"
        return None

    @staticmethod
    def _performance_target_met(
        *,
        performance_target_fps: Any,
        performance_target_latency_ms: Any,
        performance_measured_fps: Any,
        performance_measured_latency_ms: Any,
    ) -> bool:
        target_fps = _optional_number(performance_target_fps)
        target_latency = _optional_number(performance_target_latency_ms)
        measured_fps = _optional_number(performance_measured_fps)
        measured_latency = _optional_number(performance_measured_latency_ms)
        if target_fps is None or target_latency is None or measured_fps is None or measured_latency is None:
            return False
        return measured_fps >= target_fps and measured_latency <= target_latency

    @staticmethod
    def _performance_bottleneck(
        *,
        performance_target_fps: Any,
        performance_target_latency_ms: Any,
        performance_measured_fps: Any,
        performance_measured_latency_ms: Any,
    ) -> str | None:
        target_fps = _optional_number(performance_target_fps)
        target_latency = _optional_number(performance_target_latency_ms)
        measured_fps = _optional_number(performance_measured_fps)
        measured_latency = _optional_number(performance_measured_latency_ms)
        if target_fps is None or target_latency is None:
            return "performance_target_not_reported"
        if measured_fps is None or measured_fps <= 0:
            return "virtual_camera_fps_not_reported"
        if measured_fps < target_fps:
            return "virtual_camera_fps_below_target"
        if measured_latency is None:
            return "windows_latency_not_reported"
        if measured_latency > target_latency:
            return "windows_latency_above_target"
        return None

    @staticmethod
    def _benchmark_context_bottleneck(
        *,
        receiver_resolution: Any,
        requested_resolution: Any,
        benchmark_window_ms: Any,
        benchmark_sample_count: Any,
        performance_target_fps: Any,
        performance_target_latency_ms: Any,
        performance_measured_fps: Any,
        performance_measured_latency_ms: Any,
    ) -> str | None:
        target_fps = _optional_number(performance_target_fps)
        target_latency = _optional_number(performance_target_latency_ms)
        measured_fps = _optional_number(performance_measured_fps)
        measured_latency = _optional_number(performance_measured_latency_ms)
        if target_fps is None or target_latency is None or measured_fps is None or measured_latency is None:
            return None
        if measured_fps < target_fps or measured_latency > target_latency:
            return None

        receiver_size = _parse_resolution(receiver_resolution)
        target_size = _parse_resolution(requested_resolution) or (1280, 720)
        if receiver_size is None:
            return "receiver_resolution_not_reported"
        if receiver_size[0] < target_size[0] or receiver_size[1] < target_size[1]:
            return "receiver_resolution_below_target"

        window_ms = _optional_number(benchmark_window_ms)
        if window_ms is None:
            return "benchmark_window_not_reported"
        if window_ms < 1000:
            return "benchmark_window_too_short"

        sample_count = _optional_int_value(benchmark_sample_count)
        minimum_samples = max(int(target_fps * 0.8), 1)
        if sample_count is None:
            return "benchmark_sample_count_not_reported"
        if sample_count < minimum_samples:
            return "benchmark_sample_count_too_low"
        return None

def create_default_peer_connection_runtime(video_sink: Any | None = None) -> WebRTCPeerConnectionRuntime:
    return OptionalAiortcPeerConnectionRuntime(video_sink=video_sink)


def build_webrtc_receiver_status(
    upstream_status: WebRTCStatus | None = None,
    *,
    peer_connection: WebRTCPeerConnectionRuntime | None = None,
    normal_app_camera_visible: bool | None = None,
) -> JsonDict:
    return WebRTCReceiverRuntime(
        peer_connection=peer_connection,
        normal_app_camera_visible=normal_app_camera_visible,
    ).status(upstream_status)


def build_webrtc_receiver_stats(status: JsonDict) -> WebRTCReceiverStats:
    windows_receiver = status.get("windows_receiver") if isinstance(status.get("windows_receiver"), dict) else {}
    peer_connection = status.get("peer_connection") if isinstance(status.get("peer_connection"), dict) else {}

    received_fps = _number(windows_receiver.get("received_fps"), status.get("received_fps"))
    decoded_fps = _number(windows_receiver.get("decoded_fps"), status.get("decoded_fps"))
    virtual_camera_fps = _number(status.get("virtual_camera_fps"), 0.0)
    dropped_frames = int(_number(status.get("dropped_frames"), 0))
    receiver_state = _receiver_state(status, received_fps, decoded_fps, virtual_camera_fps)
    message = _receiver_stats_message(
        receiver_state=receiver_state,
        received_fps=received_fps,
        decoded_fps=decoded_fps,
        virtual_camera_fps=virtual_camera_fps,
        fallback_reason=status.get("fallback_reason"),
        peer_error=peer_connection.get("last_error"),
    )

    return WebRTCReceiverStats(
        receiver_state=receiver_state,
        received_fps=received_fps,
        decoded_fps=decoded_fps,
        virtual_camera_fps=virtual_camera_fps,
        estimated_latency_ms=_optional_number(status.get("estimated_latency_ms")),
        latest_frame_age_ms=_optional_number(status.get("latest_frame_age_ms") or status.get("latestFrameAgeMs")),
        dropped_frames=dropped_frames,
        normal_app_camera_visible=_optional_bool_value(
            status.get("normal_app_camera_visible")
            if "normal_app_camera_visible" in status
            else status.get("normalAppCameraVisible")
        ),
    )


def _number(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _number_or_zero(value: Any) -> float:
    return _number(value, 0.0)


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_bool_value(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    fraction = rank - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _parse_resolution(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        width = _optional_int_value(value.get("width"))
        height = _optional_int_value(value.get("height"))
        return (width, height) if width is not None and height is not None else None
    text = str(value).lower().replace(" ", "")
    if "x" not in text:
        return None
    width_text, height_text = text.split("x", 1)
    width = _optional_int_value(width_text)
    height = _optional_int_value(height_text)
    return (width, height) if width is not None and height is not None else None


def _receiver_state(
    status: JsonDict,
    received_fps: float,
    decoded_fps: float,
    virtual_camera_fps: float,
) -> str:
    peer_status = status.get("peer_connection") if isinstance(status.get("peer_connection"), dict) else {}
    peer_state = str(peer_status.get("peer_connection_state") or status.get("peer_connection_state") or "")
    ice_state = str(peer_status.get("ice_state") or status.get("ice_state") or "")
    if virtual_camera_fps > 0:
        return "virtual_camera_output"
    if decoded_fps > 0:
        return "decoded_video"
    if received_fps > 0:
        return "receiving_media"
    if peer_state in {"connected", "connecting"} or ice_state in {"connected", "completed", "checking"}:
        return f"peer_{peer_state or ice_state}"
    if peer_status.get("available") is False:
        return str(peer_status.get("runtime_state") or "receiver_unavailable")
    return "not_started"


def _receiver_stats_message(
    *,
    receiver_state: str,
    received_fps: float,
    decoded_fps: float,
    virtual_camera_fps: float,
    fallback_reason: Any,
    peer_error: Any,
) -> str:
    parts = [f"Windows receiver state: {receiver_state}."]
    if received_fps <= 0:
        parts.append("No Windows video input FPS yet.")
    elif decoded_fps <= 0:
        parts.append("Video input observed, but decoded FPS is still zero.")
    elif virtual_camera_fps <= 0:
        parts.append("Decoded video is not yet wired into the virtual camera provider.")
    if fallback_reason:
        parts.append(f"Camera transport unavailable reason: {fallback_reason}.")
    if peer_error:
        parts.append(f"Peer runtime error: {peer_error}.")
    return " ".join(parts)
