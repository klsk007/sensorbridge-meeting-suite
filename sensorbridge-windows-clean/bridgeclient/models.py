from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


JsonDict = dict[str, Any]


def error_json(code: str, message: str, detail: Any | None = None) -> JsonDict:
    payload: JsonDict = {"ok": False, "error": {"code": code, "message": message}}
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload


def _unwrap(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return payload


def _optional_str(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value)
    return None


def _optional_bool(data: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return bool(value)
    return None


def _optional_float(data: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_int(data: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


@dataclass
class CommandResult:
    ok: bool
    command: str
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, command: str, payload: Mapping[str, Any]) -> "CommandResult":
        return cls(ok=bool(payload.get("ok", True)), command=command, raw=dict(payload))

    def to_json(self) -> JsonDict:
        return {"ok": self.ok, "command": self.command, **self.raw}


@dataclass
class VideoFrame:
    sequence: int | None = None
    timestamp_ns: int | None = None
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None
    data_base64: str | None = None
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "VideoFrame":
        data = _unwrap(payload, "video_frame", "frame")
        return cls(
            sequence=_optional_int(data, "sequence"),
            timestamp_ns=_optional_int(data, "timestamp_ns", "timestampNs"),
            width=_optional_int(data, "width"),
            height=_optional_int(data, "height"),
            pixel_format=_optional_str(data, "pixel_format", "pixelFormat", "format"),
            data_base64=_optional_str(data, "data_base64", "payloadBase64", "payload_base64", "base64"),
            raw=dict(data),
        )

    def to_json(self) -> JsonDict:
        data: JsonDict = {}
        if self.sequence is not None:
            data["sequence"] = self.sequence
        if self.timestamp_ns is not None:
            data["timestamp_ns"] = self.timestamp_ns
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        if self.pixel_format is not None:
            data["pixel_format"] = self.pixel_format
        if self.data_base64 is not None:
            data["data_base64"] = self.data_base64
        return data


@dataclass
class WebRTCSessionDescription:
    type: str
    sdp: str

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "WebRTCSessionDescription":
        data = _unwrap(payload, "description", "localDescription", "remoteDescription")
        sdp_type = _optional_str(data, "type")
        sdp = _optional_str(data, "sdp")
        if not sdp_type or not sdp:
            raise ValueError("WebRTC session description requires type and sdp.")
        return cls(type=sdp_type, sdp=sdp)

    def to_json(self) -> JsonDict:
        return {"type": self.type, "sdp": self.sdp}


@dataclass
class WebRTCIceCandidate:
    candidate: str
    sdp_mid: str | None = None
    sdp_mline_index: int | None = None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "WebRTCIceCandidate":
        data = _unwrap(payload, "candidate", "iceCandidate")
        candidate = _optional_str(data, "candidate")
        if not candidate:
            raise ValueError("WebRTC ICE candidate requires candidate.")
        return cls(
            candidate=candidate,
            sdp_mid=_optional_str(data, "sdpMid", "sdp_mid"),
            sdp_mline_index=_optional_int(data, "sdpMLineIndex", "sdp_mline_index"),
        )

    def to_json(self) -> JsonDict:
        data: JsonDict = {"candidate": self.candidate}
        if self.sdp_mid is not None:
            data["sdpMid"] = self.sdp_mid
        if self.sdp_mline_index is not None:
            data["sdpMLineIndex"] = self.sdp_mline_index
        return data


@dataclass
class WebRTCSignalingResult:
    ok: bool
    command: str
    local_description: WebRTCSessionDescription | None = None
    local_ice_candidates: list[WebRTCIceCandidate] = field(default_factory=list)
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, command: str, payload: Mapping[str, Any]) -> "WebRTCSignalingResult":
        local_description = None
        raw_description = payload.get("localDescription")
        if isinstance(raw_description, Mapping):
            local_description = WebRTCSessionDescription.from_json(raw_description)
        raw_candidates = payload.get("localIceCandidates") or []
        candidates = [
            WebRTCIceCandidate.from_json(candidate)
            for candidate in raw_candidates
            if isinstance(candidate, Mapping) and candidate.get("candidate")
        ]
        return cls(
            ok=bool(payload.get("ok", True)),
            command=command,
            local_description=local_description,
            local_ice_candidates=candidates,
            raw=dict(payload),
        )

    def to_json(self) -> JsonDict:
        data = {"ok": self.ok, "command": self.command, **self.raw}
        if self.local_description is not None:
            data["localDescription"] = self.local_description.to_json()
        if self.local_ice_candidates:
            data["localIceCandidates"] = [candidate.to_json() for candidate in self.local_ice_candidates]
        return data


@dataclass
class WebRTCStatus:
    media_connected: bool | None = None
    product_ready: bool | None = None
    product_readiness: str | None = None
    product_incomplete_reason: str | None = None
    transport_mode: str | None = "webrtc"
    next_action: str | None = None
    real_ipad_camera: bool | None = None
    sender_stats_fresh: bool | None = None
    windows_receiver_stats_fresh: bool | None = None
    ipad_video_state: str | None = None
    windows_video_state: str | None = None
    virtual_camera_state: str | None = None
    normal_app_camera_visible: bool | None = None
    performance_target_fps: float | None = None
    performance_target_latency_ms: float | None = None
    performance_measured_fps: float | None = None
    performance_measured_latency_ms: float | None = None
    performance_latency_source: str | None = None
    performance_target_met: bool | None = None
    performance_readiness: str | None = None
    performance_bottleneck: str | None = None
    windows_receiver_stats_age_ms: float | None = None
    windows_receiver_stats_fresh_window_ms: float | None = None
    last_sender_stats_at: str | None = None
    sender_stats_age_ms: float | None = None
    sender_stats_fresh_window_ms: float | None = None
    signaling_state: str | None = None
    ice_state: str | None = None
    ice_gathering_state: str | None = None
    native_runtime_linked: bool | None = None
    runtime_name: str | None = None
    runtime_state: str | None = None
    peer_connection_state: str | None = None
    camera_track_ready: bool | None = None
    local_description_type: str | None = None
    remote_description_type: str | None = None
    local_ice_candidates_generated: int | None = None
    last_local_candidate_at: str | None = None
    video_codec: str | None = None
    requested_resolution: str | None = None
    requested_fps: float | None = None
    selected_resolution: str | None = None
    selected_fps: float | None = None
    capture_profile_resolution: str | None = None
    capture_profile_fps: float | None = None
    capture_profile_supported: bool | None = None
    capture_profile_reason: str | None = None
    sender_max_framerate: float | None = None
    sender_max_bitrate_bps: int | None = None
    sender_min_bitrate_bps: int | None = None
    sender_parameters_applied: bool | None = None
    sender_parameters_reason: str | None = None
    media_degradation_reason: str | None = None
    width: int | None = None
    height: int | None = None
    target_fps: float | None = None
    sent_fps: float | None = None
    received_fps: float | None = None
    decoded_fps: float | None = None
    virtual_camera_fps: float | None = None
    receiver_resolution: str | None = None
    benchmark_window_ms: float | None = None
    benchmark_sample_count: int | None = None
    receiver_cpu_percent: float | None = None
    sender_estimated_latency_ms: float | None = None
    estimated_latency_ms: float | None = None
    dropped_frames: int | None = None
    raw: JsonDict = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "WebRTCStatus":
        return cls(
            media_connected=_optional_bool(payload, "media_connected", "mediaConnected"),
            product_ready=_optional_bool(payload, "product_ready", "productReady"),
            product_readiness=_optional_str(payload, "product_readiness", "productReadiness"),
            product_incomplete_reason=_optional_str(payload, "product_incomplete_reason", "productIncompleteReason"),
            transport_mode=_optional_str(payload, "transport_mode", "transportMode", "activeCameraTransport") or "webrtc",
            next_action=_optional_str(payload, "next_action", "nextAction"),
            real_ipad_camera=_optional_bool(payload, "real_ipad_camera", "realIpadCamera"),
            sender_stats_fresh=_optional_bool(payload, "sender_stats_fresh", "senderStatsFresh"),
            windows_receiver_stats_fresh=_optional_bool(payload, "windows_receiver_stats_fresh", "windowsReceiverStatsFresh"),
            ipad_video_state=_optional_str(payload, "ipad_video_state", "ipadVideoState"),
            windows_video_state=_optional_str(payload, "windows_video_state", "windowsVideoState"),
            virtual_camera_state=_optional_str(payload, "virtual_camera_state", "virtualCameraState"),
            normal_app_camera_visible=_optional_bool(payload, "normal_app_camera_visible", "normalWindowsCameraVisible"),
            performance_target_fps=_optional_float(payload, "performance_target_fps", "performanceTargetFps"),
            performance_target_latency_ms=_optional_float(payload, "performance_target_latency_ms", "performanceTargetLatencyMs"),
            performance_measured_fps=_optional_float(payload, "performance_measured_fps", "performanceMeasuredFps"),
            performance_measured_latency_ms=_optional_float(payload, "performance_measured_latency_ms", "performanceMeasuredLatencyMs"),
            performance_latency_source=_optional_str(payload, "performance_latency_source", "performanceLatencySource"),
            performance_target_met=_optional_bool(payload, "performance_target_met", "performanceTargetMet"),
            performance_readiness=_optional_str(payload, "performance_readiness", "performanceReadiness"),
            performance_bottleneck=_optional_str(payload, "performance_bottleneck", "performanceBottleneck"),
            windows_receiver_stats_age_ms=_optional_float(payload, "windows_receiver_stats_age_ms", "windowsReceiverStatsAgeMs"),
            windows_receiver_stats_fresh_window_ms=_optional_float(payload, "windows_receiver_stats_fresh_window_ms", "windowsReceiverStatsFreshWindowMs"),
            last_sender_stats_at=_optional_str(payload, "last_sender_stats_at", "lastSenderStatsAt"),
            sender_stats_age_ms=_optional_float(payload, "sender_stats_age_ms", "senderStatsAgeMs"),
            sender_stats_fresh_window_ms=_optional_float(payload, "sender_stats_fresh_window_ms", "senderStatsFreshWindowMs"),
            signaling_state=_optional_str(payload, "signaling_state", "signalingState"),
            ice_state=_optional_str(payload, "ice_state", "iceState"),
            ice_gathering_state=_optional_str(payload, "ice_gathering_state", "iceGatheringState"),
            native_runtime_linked=_optional_bool(payload, "native_runtime_linked", "nativeRuntimeLinked"),
            runtime_name=_optional_str(payload, "runtime_name", "runtimeName"),
            runtime_state=_optional_str(payload, "runtime_state", "runtimeState"),
            peer_connection_state=_optional_str(payload, "peer_connection_state", "peerConnectionState"),
            camera_track_ready=_optional_bool(payload, "camera_track_ready", "cameraTrackReady"),
            local_description_type=_optional_str(payload, "local_description_type", "localDescriptionType"),
            remote_description_type=_optional_str(payload, "remote_description_type", "remoteDescriptionType"),
            local_ice_candidates_generated=_optional_int(payload, "local_ice_candidates_generated", "localIceCandidatesGenerated"),
            last_local_candidate_at=_optional_str(payload, "last_local_candidate_at", "lastLocalCandidateAt"),
            video_codec=_optional_str(payload, "video_codec", "videoCodec"),
            requested_resolution=_optional_str(payload, "requested_resolution", "requestedResolution"),
            requested_fps=_optional_float(payload, "requested_fps", "requestedFps"),
            selected_resolution=_optional_str(payload, "selected_resolution", "selectedResolution"),
            selected_fps=_optional_float(payload, "selected_fps", "selectedFps"),
            capture_profile_resolution=_optional_str(payload, "capture_profile_resolution", "captureProfileResolution"),
            capture_profile_fps=_optional_float(payload, "capture_profile_fps", "captureProfileFps"),
            capture_profile_supported=_optional_bool(payload, "capture_profile_supported", "captureProfileSupported"),
            capture_profile_reason=_optional_str(payload, "capture_profile_reason", "captureProfileReason"),
            sender_max_framerate=_optional_float(payload, "sender_max_framerate", "senderMaxFramerate"),
            sender_max_bitrate_bps=_optional_int(payload, "sender_max_bitrate_bps", "senderMaxBitrateBps"),
            sender_min_bitrate_bps=_optional_int(payload, "sender_min_bitrate_bps", "senderMinBitrateBps"),
            sender_parameters_applied=_optional_bool(payload, "sender_parameters_applied", "senderParametersApplied"),
            sender_parameters_reason=_optional_str(payload, "sender_parameters_reason", "senderParametersReason"),
            media_degradation_reason=_optional_str(payload, "media_degradation_reason", "mediaDegradationReason"),
            width=_optional_int(payload, "width"),
            height=_optional_int(payload, "height"),
            target_fps=_optional_float(payload, "target_fps", "targetFps"),
            sent_fps=_optional_float(payload, "sent_fps", "sentFps"),
            received_fps=_optional_float(payload, "received_fps", "receivedFps"),
            decoded_fps=_optional_float(payload, "decoded_fps", "decodedFps"),
            virtual_camera_fps=_optional_float(payload, "virtual_camera_fps", "virtualCameraFps"),
            receiver_resolution=_optional_str(payload, "receiver_resolution", "receiverResolution"),
            benchmark_window_ms=_optional_float(payload, "benchmark_window_ms", "benchmarkWindowMs"),
            benchmark_sample_count=_optional_int(payload, "benchmark_sample_count", "benchmarkSampleCount"),
            receiver_cpu_percent=_optional_float(payload, "receiver_cpu_percent", "receiverCpuPercent"),
            sender_estimated_latency_ms=_optional_float(payload, "sender_estimated_latency_ms", "senderEstimatedLatencyMs"),
            estimated_latency_ms=_optional_float(payload, "estimated_latency_ms", "estimatedLatencyMs"),
            dropped_frames=_optional_int(payload, "dropped_frames", "droppedFrames"),
            raw=dict(payload),
        )

    def to_json(self) -> JsonDict:
        data = dict(self.raw)
        values = {
            "media_connected": self.media_connected,
            "transport_mode": self.transport_mode,
            "received_fps": self.received_fps,
            "decoded_fps": self.decoded_fps,
            "virtual_camera_fps": self.virtual_camera_fps,
            "estimated_latency_ms": self.estimated_latency_ms,
            "dropped_frames": self.dropped_frames,
            "normal_app_camera_visible": self.normal_app_camera_visible,
            "native_runtime_linked": self.native_runtime_linked,
        }
        for key, value in values.items():
            if value is not None:
                data[key] = value
        return data


@dataclass
class WebRTCReceiverStats:
    receiver_state: str = "idle"
    received_fps: float = 0.0
    decoded_fps: float = 0.0
    virtual_camera_fps: float = 0.0
    estimated_latency_ms: float | None = None
    latest_frame_age_ms: float | None = None
    dropped_frames: int = 0
    normal_app_camera_visible: bool | None = None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "WebRTCReceiverStats":
        data = _unwrap(payload, "stats")
        return cls(
            receiver_state=_optional_str(data, "receiverState", "receiver_state") or "idle",
            received_fps=_optional_float(data, "receivedFps", "received_fps") or 0.0,
            decoded_fps=_optional_float(data, "decodedFps", "decoded_fps") or 0.0,
            virtual_camera_fps=_optional_float(data, "virtualCameraFps", "virtual_camera_fps") or 0.0,
            estimated_latency_ms=_optional_float(data, "estimatedLatencyMs", "estimated_latency_ms"),
            latest_frame_age_ms=_optional_float(data, "latestFrameAgeMs", "latest_frame_age_ms"),
            dropped_frames=_optional_int(data, "droppedFrames", "dropped_frames") or 0,
            normal_app_camera_visible=_optional_bool(data, "normalWindowsCameraVisible", "normal_app_camera_visible"),
        )

    def to_json(self) -> JsonDict:
        data: JsonDict = {
            "receiverState": self.receiver_state,
            "receivedFps": float(self.received_fps),
            "decodedFps": float(self.decoded_fps),
            "virtualCameraFps": float(self.virtual_camera_fps),
            "droppedFrames": int(self.dropped_frames),
        }
        if self.estimated_latency_ms is not None:
            data["estimatedLatencyMs"] = float(self.estimated_latency_ms)
        if self.latest_frame_age_ms is not None:
            data["latestFrameAgeMs"] = float(self.latest_frame_age_ms)
        if self.normal_app_camera_visible is not None:
            data["normalWindowsCameraVisible"] = bool(self.normal_app_camera_visible)
        return data
