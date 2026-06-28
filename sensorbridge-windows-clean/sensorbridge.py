from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import socket
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bridgeclient.camera_provider import (
    inspect_camera_provider_status,
    register_camera_provider,
    start_camera_provider,
    stop_camera_provider,
)
from bridgeclient.client import SensorBridgeClient
from bridgeclient.directshow_camera import (
    build_directshow_camera_sender,
    inspect_directshow_camera_build_status,
    inspect_directshow_camera_open_status,
    inspect_directshow_camera_register_status,
    inspect_directshow_camera_sender_status,
    register_directshow_camera,
    start_directshow_camera_sender,
    stop_directshow_camera_sender,
    unregister_directshow_camera,
)
from bridgeclient.errors import BridgeClientError
from bridgeclient.models import WebRTCIceCandidate, WebRTCReceiverStats, WebRTCSessionDescription, WebRTCStatus
from bridgeclient.transport import HttpTransport
from bridgeclient.video_sink import FrameFileVideoSink
from bridgeclient.webrtc_receiver import (
    WebRTCReceiverRuntime,
    build_webrtc_receiver_stats,
    create_default_peer_connection_runtime,
)


ROOT = Path(__file__).resolve().parent
PRODUCT_STATUS_FIELDS = (
    "activeCameraTransport",
    "receivedFps",
    "decodedFps",
    "virtualCameraFps",
    "latestFrameAgeMs",
    "estimatedLatencyMs",
    "droppedFrames",
    "normalWindowsCameraVisible",
)

REMOVED_CAMERA_ONLY_EXACT_PATHS = {
    "/phone",
    "/video/sample",
    "/api/v1/sample/video-frame",
    "/api/v/sample/acceleration",
    "/api/v1/sample/acceleration",
    "/api/v1/sample/audio-frame",
    "/api/v1/media/readiness",
    "/api/media/readiness",
}

REMOVED_CAMERA_ONLY_PATH_PREFIXES = (
    "/api/microphone",
    "/api/v1/microphone",
    "/api/v1/audio",
    "/audio",
    "/api/v1/speaker",
    "/speaker",
    "/api/v/acceleration",
    "/api/v1/acceleration",
    "/api/upstream/acceleration",
    "/api/v1/upstream/acceleration",
    "/api/upstream/audio",
    "/api/v1/upstream/audio",
    "/api/upstream/pull/audio-frame",
    "/api/v1/upstream/pull/audio-frame",
    "/api/upstream/pull/acceleration",
    "/api/v1/upstream/pull/acceleration",
    "/api/upstream/pull/video-frame",
    "/api/v1/upstream/pull/video-frame",
    "/api/upstream/poll",
    "/api/v1/upstream/poll",
    "/api/camera/feed",
    "/api/v1/camera/feed",
    "/api/v1/mock",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def camera_only_removed_feature(path: str) -> bool:
    if path in REMOVED_CAMERA_ONLY_EXACT_PATHS:
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in REMOVED_CAMERA_ONLY_PATH_PREFIXES)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


REMOVED_STATUS_KEYWORDS = ("audio", "microphone", "speaker", "accelerometer", "acceleration")


def _camera_only_status(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(keyword in lowered for keyword in REMOVED_STATUS_KEYWORDS):
                continue
            cleaned[key] = _camera_only_status(item)
        return cleaned
    if isinstance(value, list):
        return [_camera_only_status(item) for item in value]
    if isinstance(value, str):
        text = value.lower()
        if any(keyword in text for keyword in REMOVED_STATUS_KEYWORDS):
            return "camera_only"
    return value


class SensorBridgeState:
    def __init__(self, data_dir: Path, upstream_url: str = "http://192.168.0.24:27180") -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "sensorbridge-camera.ndjson"
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.upstream_url = upstream_url.rstrip("/")
        self._last_upstream_status: WebRTCStatus | None = None
        self._last_connect: dict[str, Any] | None = None
        self._normal_camera_visible_cache: tuple[float, bool | None] | None = None
        self._product_mode_active = False
        self._connect_lock = threading.Lock()
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_stop = threading.Event()
        self._latest_receiver_stats: WebRTCReceiverStats | None = None
        self._latest_receiver_stats_at: float | None = None
        self._video_sink = FrameFileVideoSink()
        self.webrtc_receiver = WebRTCReceiverRuntime(
            native_runtime_linked=True,
            peer_runtime_name="aiortc",
            peer_connection=create_default_peer_connection_runtime(self._video_sink),
            video_sink=self._video_sink,
            fallback_reason="",
            next_action="connect_ipad_webrtc_h264_camera",
        )

    def latest_frame_path(self) -> Path:
        return self._video_sink.directory / "latest.bmp"

    def latest_frame_payload(self) -> tuple[bytes, dict[str, Any]]:
        frame_path = self.latest_frame_path()
        if not frame_path.is_file():
            raise FileNotFoundError(str(frame_path))
        metadata_path = self._video_sink.latest_metadata_path
        metadata: dict[str, Any] = {}
        if metadata_path.is_file():
            try:
                loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, json.JSONDecodeError):
                metadata = {}
        return frame_path.read_bytes(), metadata

    def save_photo(self) -> dict[str, Any]:
        frame_path = self.latest_frame_path()
        if not frame_path.is_file():
            return {
                "ok": False,
                "command": "save_camera_photo",
                "error": {"code": "camera_frame_missing", "message": "No decoded camera frame is available yet."},
            }
        photo_dir = Path.home() / "Pictures" / "SensorBridge"
        photo_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = photo_dir / f"SensorBridge-{stamp}.bmp"
        shutil.copy2(frame_path, target)
        return {
            "ok": True,
            "command": "save_camera_photo",
            "path": str(target),
            "filename": target.name,
            "contentType": "image/bmp",
            "bytes": target.stat().st_size,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "product": "camera_only",
            "started_at": datetime.fromtimestamp(self.started_at, timezone.utc).isoformat().replace("+00:00", "Z"),
            "uptime_s": max(time.time() - self.started_at, 0.0),
            "capabilities": self.capabilities_payload()["capabilities"],
            "product_status": self.product_status_payload(),
        }

    def capabilities_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "capabilities",
            "product": "camera_only",
            "capabilities": {
                "transport": {"active": "webrtc", "codec": "H264", "fallback": None},
                "devices": {
                    "camera": {
                        "available": True,
                        "input": "ipad_camera",
                        "receiver": "windows_webrtc_h264",
                        "output": "windows_virtual_camera",
                    }
                },
                "removed": {
                    "non_camera_features": True,
                    "http_frame_polling": True,
                    "default_device_changes": True,
                },
            },
        }

    def network_payload(self, port: int | None = None) -> dict[str, Any]:
        lan_ip = get_lan_ip()
        return {
            "ok": True,
            "command": "network",
            "lan_ip": lan_ip,
            "port": port,
            "urls": {
                "dashboard": f"http://{lan_ip}:{port}/" if port else None,
                "local_dashboard": f"http://127.0.0.1:{port}/" if port else None,
                "upstream": self.upstream_url,
            },
        }

    def configure_upstream(self, base_url: str) -> dict[str, Any]:
        if not base_url:
            return {"ok": False, "command": "configure_upstream", "error": {"code": "missing_upstream_url", "message": "base_url is required."}}
        if not base_url.startswith(("http://", "https://")):
            base_url = "http://" + base_url
        self.upstream_url = base_url.rstrip("/")
        return {"ok": True, "command": "configure_upstream", "base_url": self.upstream_url}

    def check_upstream(self) -> dict[str, Any]:
        try:
            client = self._upstream_client()
            health = client.transport.request_json("GET", "/health", timeout=5.0)
            status_payload = client.transport.request_json("GET", "/api/v2/webrtc/status", timeout=5.0)
            status = WebRTCStatus.from_json(status_payload)
            with self._lock:
                self._last_upstream_status = status
            return {
                "ok": True,
                "command": "check_upstream",
                "base_url": self.upstream_url,
                "health": health,
                "webrtc": status_payload,
            }
        except Exception as exc:
            return {
                "ok": False,
                "command": "check_upstream",
                "base_url": self.upstream_url,
                "error": {"code": "upstream_check_failed", "message": str(exc)},
            }

    def status_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "status",
            "product": "camera_only",
            "camera": self.product_status_payload(),
        }

    def webrtc_status_payload(self) -> dict[str, Any]:
        status = self.webrtc_receiver.status(self._latest_upstream_status())
        self._normalize_camera_status(status)
        status["command"] = "webrtc_status"
        status["activeCameraTransport"] = "webrtc"
        return _camera_only_status(status)

    def _normalize_camera_status(self, status: dict[str, Any]) -> None:
        received_fps = _number(status.get("received_fps"))
        decoded_fps = _number(status.get("decoded_fps"))
        virtual_camera_fps = _number(status.get("virtual_camera_fps"))
        latest_frame_age = _number(status.get("latest_frame_age_ms"), default=999999.0)
        active = received_fps > 0 and decoded_fps > 0 and virtual_camera_fps > 0 and latest_frame_age <= 3000.0
        if not active:
            return
        status["complete"] = True
        status["product_ready"] = True
        status["product_readiness"] = "active"
        status["product_incomplete_reason"] = None
        status["performance_readiness"] = "active"
        status["performance_bottleneck"] = None
        status["performance_measured_fps"] = virtual_camera_fps
        status["performance_measured_latency_ms"] = status.get("estimated_latency_ms")
        status["performance_latency_source"] = "windows_receiver"
        status["performance_target_met"] = virtual_camera_fps >= 24.0
        status["windows_video_state"] = "receiving"
        status["virtual_camera_state"] = "active"
        status["next_action"] = "camera_active"
        status["fallback_reason"] = None
        status["media_degradation_reason"] = None
        status["ipad_video_state"] = "camera_streaming"

    def product_status_payload(self) -> dict[str, Any]:
        status = self.webrtc_status_payload()
        received_fps = _number(status.get("received_fps"))
        decoded_fps = _number(status.get("decoded_fps"))
        virtual_camera_fps = _number(status.get("virtual_camera_fps"))
        latest_frame_age_ms = status.get("latest_frame_age_ms")
        latest_frame_age_number = _number(latest_frame_age_ms, default=999999.0)
        estimated_latency_ms = status.get("estimated_latency_ms")
        dropped_frames = _int(status.get("dropped_frames"))
        normal_windows_camera_visible = status.get("normal_windows_camera_visible")
        media_connected = bool(status.get("media_connected"))
        if normal_windows_camera_visible is None and virtual_camera_fps > 0:
            normal_windows_camera_visible = self._normal_camera_visible()
        frame_is_fresh = latest_frame_age_number <= 3000.0
        camera_available = media_connected and frame_is_fresh and received_fps > 0 and decoded_fps > 0 and virtual_camera_fps > 0
        camera_state = "active" if camera_available else "unavailable"
        payload = {
            "ok": True,
            "command": "product_status",
            "product": "camera_only",
            "activeCameraTransport": "webrtc",
            "active_camera_transport": "webrtc",
            "receivedFps": received_fps,
            "decodedFps": decoded_fps,
            "virtualCameraFps": virtual_camera_fps,
            "latestFrameAgeMs": latest_frame_age_ms,
            "estimatedLatencyMs": estimated_latency_ms,
            "droppedFrames": dropped_frames,
            "normalWindowsCameraVisible": normal_windows_camera_visible,
            "normal_windows_camera_visible": normal_windows_camera_visible,
            "cameraAvailable": camera_available,
            "camera": {
                "status": camera_state,
                "transport": "webrtc",
                "codec": "H264",
                "received_fps": received_fps,
                "decoded_fps": decoded_fps,
                "virtual_camera_fps": virtual_camera_fps,
                "latest_frame_age_ms": latest_frame_age_ms,
                "estimated_latency_ms": estimated_latency_ms,
                "dropped_frames": dropped_frames,
                "normal_windows_camera_visible": normal_windows_camera_visible,
            },
            "webrtc": status,
            "virtual_camera": {
                "provider": "DirectShow",
                "name": "SensorBridge Camera",
                "fps": virtual_camera_fps,
                "visible_to_normal_windows_camera": normal_windows_camera_visible,
            },
            "acceptance_probes": {
                "activeCameraTransport": "webrtc",
                "receivedFps": received_fps,
                "decodedFps": decoded_fps,
                "virtualCameraFps": virtual_camera_fps,
                "latestFrameAgeMs": latest_frame_age_ms,
                "estimatedLatencyMs": estimated_latency_ms,
                "droppedFrames": dropped_frames,
                "normalWindowsCameraVisible": normal_windows_camera_visible,
            },
            "blockers": [] if camera_available else ["windows_webrtc_camera_unavailable" if frame_is_fresh else "windows_webrtc_frame_stale"],
            "notes": [
                "Product Mode uses only WebRTC/H.264 receiver and Windows virtual camera output.",
                "If WebRTC is unavailable, SensorBridge Camera is reported unavailable.",
            ],
        }
        for field in PRODUCT_STATUS_FIELDS:
            payload.setdefault(field, None)
        return payload

    def product_contract_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "product_contract",
            "product": "camera_only",
            "version": 4,
            "only_supported_chain": [
                "iPad Camera",
                "WebRTC/H.264 low-latency transport",
                "Windows receiver/decoder",
                "Windows virtual camera",
            ],
            "endpoints": {
                "status": "/api/v1/product/status",
                "start": "/api/v1/product/start",
                "webrtc_status": "/api/v2/webrtc/status",
                "webrtc_connect": "/api/v2/webrtc/connect",
                "virtual_camera_status": "/api/directshow/camera/status",
            },
            "removed_routes_return": "410 camera_only_feature_removed",
        }

    def start_product_mode(self) -> dict[str, Any]:
        self._product_mode_active = True
        self._start_watchdog()
        sender = start_directshow_camera_sender()
        webrtc_connect = self.connect_webrtc_receiver()
        acceptance = self.product_status_payload()
        return {
            "ok": bool(webrtc_connect.get("ok", True)),
            "command": "start_product_mode",
            "product": "camera_only",
            "requested": {
                "webrtc_receiver": True,
                "directshow_camera_sender": True,
            },
            "webrtc_connect": webrtc_connect,
            "directshow_sender": sender,
            "acceptance_snapshot": acceptance,
            "product_status": acceptance,
            "notes": [
                "Product Mode starts the WebRTC/H.264 receiver and Windows virtual camera sender only.",
                "There is no HTTP frame polling fallback.",
            ],
        }

    def stop_product_mode(self) -> dict[str, Any]:
        self._product_mode_active = False
        self._watchdog_stop.set()
        sender = stop_directshow_camera_sender()
        return {
            "ok": bool(sender.get("ok", True)),
            "command": "stop_product_mode",
            "product": "camera_only",
            "directshow_sender": sender,
            "product_status": self.product_status_payload(),
        }

    def create_webrtc_receiver_offer(self) -> dict[str, Any]:
        return self.webrtc_receiver.peer_connection.create_offer() if self.webrtc_receiver.peer_connection else {}

    def apply_webrtc_receiver_answer(self, body: dict[str, Any]) -> dict[str, Any]:
        description = WebRTCSessionDescription.from_json(body)
        if not self.webrtc_receiver.peer_connection:
            return {"ok": False, "error": {"code": "webrtc_receiver_missing", "message": "WebRTC receiver is unavailable."}}
        return self.webrtc_receiver.peer_connection.apply_answer(description)

    def add_webrtc_receiver_ice_candidate(self, body: dict[str, Any]) -> dict[str, Any]:
        candidate = WebRTCIceCandidate.from_json(body)
        if not self.webrtc_receiver.peer_connection:
            return {"ok": False, "error": {"code": "webrtc_receiver_missing", "message": "WebRTC receiver is unavailable."}}
        return self.webrtc_receiver.peer_connection.add_ice_candidate(candidate)

    def local_webrtc_receiver_ice_candidates(self) -> dict[str, Any]:
        peer = self.webrtc_receiver.peer_connection
        candidates = peer.local_ice_candidates() if peer else []
        return {"ok": True, "command": "webrtc_receiver_local_ice_candidates", "localIceCandidates": candidates}

    def connect_webrtc_receiver(self) -> dict[str, Any]:
        if not self._connect_lock.acquire(blocking=False):
            return {
                "ok": False,
                "command": "connect_webrtc_receiver",
                "activeCameraTransport": "webrtc",
                "error": {"code": "webrtc_connect_in_progress", "message": "A WebRTC connect attempt is already running."},
            }
        try:
            return self._connect_webrtc_receiver()
        finally:
            self._connect_lock.release()

    def _connect_webrtc_receiver(self) -> dict[str, Any]:
        peer = self.webrtc_receiver.peer_connection
        if peer is not None and hasattr(peer, "reset_connection"):
            peer.reset_connection()
        offer = self.create_webrtc_receiver_offer()
        upstream_response: dict[str, Any] | None = None
        answer_apply_result: dict[str, Any] | None = None
        remote_candidate_results: list[dict[str, Any]] = []
        polled_remote_candidate_results: list[dict[str, Any]] = []
        local_candidate_posts: list[dict[str, Any]] = []
        error: dict[str, Any] | None = None
        if not offer.get("ok") or not isinstance(offer.get("localDescription"), dict):
            error = {"code": "windows_offer_failed", "message": "Windows WebRTC receiver could not create an offer."}
        else:
            try:
                client = self._upstream_client()
                signaling = client.post_webrtc_offer(offer["localDescription"])
                upstream_response = signaling.raw
                if signaling.local_description is not None:
                    answer_apply_result = self.webrtc_receiver.peer_connection.apply_answer(signaling.local_description) if self.webrtc_receiver.peer_connection else None
                for candidate in signaling.local_ice_candidates:
                    if self.webrtc_receiver.peer_connection:
                        remote_candidate_results.append(self.webrtc_receiver.peer_connection.add_ice_candidate(candidate))
                try:
                    polled = client.webrtc_local_ice_candidates()
                    for candidate in polled.local_ice_candidates:
                        if self.webrtc_receiver.peer_connection:
                            polled_remote_candidate_results.append(self.webrtc_receiver.peer_connection.add_ice_candidate(candidate))
                except Exception as exc:
                    polled_remote_candidate_results.append({"ok": False, "error": str(exc)})
                if self.webrtc_receiver.peer_connection:
                    for local_candidate in self.webrtc_receiver.peer_connection.local_ice_candidates():
                        try:
                            posted = client.transport.request_json("POST", "/api/v2/webrtc/ice-candidate", local_candidate)
                            local_candidate_posts.append({"ok": bool(posted.get("ok", True)), "candidate": local_candidate, "response": posted})
                        except Exception as exc:
                            local_candidate_posts.append({"ok": False, "candidate": local_candidate, "error": str(exc)})
                try:
                    upstream_status_payload = client.transport.request_json("GET", "/api/v2/webrtc/status", timeout=5.0)
                    with self._lock:
                        self._last_upstream_status = WebRTCStatus.from_json(upstream_status_payload)
                except Exception:
                    pass
            except Exception as exc:
                error = {"code": "webrtc_signaling_failed", "message": str(exc)}
        event = {
            "ok": error is None,
            "command": "connect_webrtc_receiver",
            "upstream_url": self.upstream_url,
            "offer": offer,
            "upstream_response": upstream_response,
            "answer_apply_result": answer_apply_result,
            "remote_candidate_results": remote_candidate_results,
            "polled_remote_candidate_results": polled_remote_candidate_results,
            "local_candidate_posts": local_candidate_posts,
            "error": error,
            "at": utc_now_iso(),
        }
        with self._lock:
            self._last_connect = event
        return {
            "ok": error is None,
            "command": "connect_webrtc_receiver",
            "activeCameraTransport": "webrtc",
            "upstreamUrl": self.upstream_url,
            "cameraAvailable": bool(self.product_status_payload().get("cameraAvailable")),
            "receiver_offer": offer,
            "upstream_response": upstream_response,
            "answer_apply_result": answer_apply_result,
            "remote_candidate_results": remote_candidate_results,
            "polled_remote_candidate_results": polled_remote_candidate_results,
            "local_candidate_posts": local_candidate_posts,
            "truth": "Offer/answer/ICE success is not media success; real success requires received and decoded FPS.",
            **({"error": error} if error is not None else {}),
        }

    def _start_watchdog(self) -> None:
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="SensorBridgeWebRTCWatchdog", daemon=True)
        self._watchdog_thread.start()

    def _watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(2.0):
            if not self._product_mode_active:
                continue
            try:
                status = self.webrtc_status_payload()
                peer = status.get("peer_connection") if isinstance(status.get("peer_connection"), dict) else {}
                peer_state = str(peer.get("peer_connection_state") or status.get("peer_connection_state") or "")
                latest_age = _number(status.get("latest_frame_age_ms"), default=0.0)
                frames_seen = _int(peer.get("video_frames_decoded") or 0)
                stale = frames_seen > 0 and latest_age > 3000.0
                failed = peer_state in {"closed", "failed"}
                if stale or failed:
                    self.connect_webrtc_receiver()
            except Exception:
                continue

    def record_webrtc_receiver_stats(self, body: dict[str, Any]) -> dict[str, Any]:
        stats = WebRTCReceiverStats.from_json(body)
        with self._lock:
            self._latest_receiver_stats = stats
            self._latest_receiver_stats_at = time.time()
        return {
            "ok": True,
            "command": "webrtc_receiver_stats",
            "activeCameraTransport": "webrtc",
            "stats": stats.to_json(),
            "product_status": self.product_status_payload(),
        }

    def receiver_stats_payload(self) -> dict[str, Any]:
        with self._lock:
            stats = self._latest_receiver_stats
            stats_at = self._latest_receiver_stats_at
        payload = (stats or build_webrtc_receiver_stats(self.webrtc_status_payload())).to_json()
        payload["ok"] = True
        payload["command"] = "webrtc_receiver_stats"
        payload["activeCameraTransport"] = "webrtc"
        payload["lastStatsAt"] = (
            datetime.fromtimestamp(stats_at, timezone.utc).isoformat().replace("+00:00", "Z") if stats_at else None
        )
        return payload

    def stop_webrtc_receiver_stats_heartbeat(self) -> None:
        return None

    def _latest_upstream_status(self) -> WebRTCStatus | None:
        with self._lock:
            stats = self._latest_receiver_stats
            upstream = self._last_upstream_status
        if upstream is not None and stats is None:
            return upstream
        if stats is None:
            return None
        return WebRTCStatus(
            media_connected=stats.decoded_fps > 0,
            transport_mode="webrtc",
            received_fps=stats.received_fps,
            decoded_fps=stats.decoded_fps,
            virtual_camera_fps=stats.virtual_camera_fps,
            dropped_frames=stats.dropped_frames,
            estimated_latency_ms=stats.estimated_latency_ms,
            normal_app_camera_visible=stats.normal_app_camera_visible,
        )

    def _upstream_client(self) -> SensorBridgeClient:
        return SensorBridgeClient(HttpTransport(self.upstream_url, timeout=10.0))

    def _normal_camera_visible(self) -> bool | None:
        now = time.monotonic()
        with self._lock:
            cached = self._normal_camera_visible_cache
        if cached is not None and now - cached[0] < 5.0:
            return cached[1]
        visible: bool | None
        try:
            probe = inspect_directshow_camera_open_status()
            visible = bool(probe.get("ok") and probe.get("opens_camera_now"))
        except Exception:
            visible = None
        with self._lock:
            self._normal_camera_visible_cache = (now, visible)
        return visible


class SensorBridgeHandler(BaseHTTPRequestHandler):
    state: SensorBridgeState
    static_dir: Path

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path, _query = self._path_and_query()
        if camera_only_removed_feature(path):
            self.send_removed_feature()
            return
        if path in {"/", "/dashboard.html"}:
            self.send_static_file("dashboard.html")
            return
        if path in {"/dashboard.js", "/styles.css", "/static/dashboard.js", "/static/styles.css"}:
            self.send_static_file(path.rsplit("/", 1)[-1])
            return
        if path == "/health":
            self.send_json({"ok": True, "product": "camera_only", "time": utc_now_iso()})
            return
        if path == "/api/v1/status":
            self.send_json(self.state.status_payload())
            return
        if path == "/api/v1/network":
            self.send_json(self.state.network_payload(self.server.server_address[1]))
            return
        if path == "/api/v1/upstream/config":
            self.send_json({"ok": True, "base_url": self.state.upstream_url})
            return
        if path == "/api/v1/upstream/check":
            self.send_json(self.state.check_upstream())
            return
        if path == "/api/v1/capabilities":
            self.send_json(self.state.capabilities_payload())
            return
        if path == "/api/v1/product/status":
            self.send_json(self.state.product_status_payload())
            return
        if path == "/api/v1/product/contract":
            self.send_json(self.state.product_contract_payload())
            return
        if path == "/api/v1/camera/latest-frame.bmp":
            try:
                payload, metadata = self.state.latest_frame_payload()
            except FileNotFoundError:
                self.send_error_json(404, "camera_frame_missing", "No decoded camera frame is available yet.")
                return
            self.send_response(200)
            self.send_common_headers("image/bmp")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            if metadata.get("sequence") is not None:
                self.send_header("X-SensorBridge-Frame-Sequence", str(metadata.get("sequence")))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path in {"/api/v2/webrtc/status", "/api/v2/webrtc/receiver/status"}:
            self.send_json(self.state.webrtc_status_payload())
            return
        if path == "/api/v2/webrtc/receiver-stats":
            self.send_json(self.state.receiver_stats_payload())
            return
        if path == "/api/v2/webrtc/local-ice-candidates":
            self.send_json(self.state.local_webrtc_receiver_ice_candidates())
            return
        if path in {"/api/camera/provider/status", "/api/v1/camera/provider/status"}:
            self.send_json(inspect_camera_provider_status())
            return
        if path in {"/api/directshow/camera/status", "/api/v1/directshow/camera/status"}:
            self.send_json(inspect_directshow_camera_register_status())
            return
        if path in {"/api/directshow/camera/build-status", "/api/v1/directshow/camera/build-status"}:
            self.send_json(inspect_directshow_camera_build_status())
            return
        if path in {"/api/directshow/camera/sender/status", "/api/v1/directshow/camera/sender/status"}:
            self.send_json(inspect_directshow_camera_sender_status())
            return
        if path in {"/api/directshow/camera/open-status", "/api/v1/directshow/camera/open-status"}:
            self.send_json(inspect_directshow_camera_open_status())
            return
        self.send_error_json(404, "not_found", f"No camera-only route for {path}.")

    def do_POST(self) -> None:
        path, _query = self._path_and_query()
        if camera_only_removed_feature(path):
            self.send_removed_feature()
            return
        try:
            body = self.read_json_body()
        except ValueError as exc:
            self.send_error_json(400, "invalid_json", str(exc))
            return
        try:
            if path == "/api/v1/product/start":
                self.send_json(self.state.start_product_mode())
                return
            if path == "/api/v1/product/stop":
                self.send_json(self.state.stop_product_mode())
                return
            if path == "/api/v1/app/shutdown":
                self.state.stop_product_mode()
                self.send_json({"ok": True, "command": "app_shutdown", "product": "camera_only"})
                threading.Thread(target=self.server.shutdown, name="SensorBridgeShutdown", daemon=True).start()
                return
            if path == "/api/v1/camera/photo":
                result = self.state.save_photo()
                self.send_json(result, 200 if result.get("ok") else 404)
                return
            if path == "/api/v1/upstream/config":
                self.send_json(self.state.configure_upstream(str(body.get("base_url", ""))))
                return
            if path == "/api/v1/upstream/check":
                self.send_json(self.state.check_upstream())
                return
            if path == "/api/v2/webrtc/connect":
                self.send_json(self.state.connect_webrtc_receiver())
                return
            if path == "/api/v2/webrtc/receiver/offer":
                self.send_json(self.state.create_webrtc_receiver_offer())
                return
            if path in {"/api/v2/webrtc/receiver/answer", "/api/v2/webrtc/answer"}:
                self.send_json(self.state.apply_webrtc_receiver_answer(body))
                return
            if path in {"/api/v2/webrtc/receiver/ice-candidate", "/api/v2/webrtc/ice-candidate"}:
                self.send_json(self.state.add_webrtc_receiver_ice_candidate(body))
                return
            if path == "/api/v2/webrtc/receiver-stats":
                self.send_json(self.state.record_webrtc_receiver_stats(body))
                return
            if path in {"/api/camera/provider/start", "/api/v1/camera/provider/start"}:
                self.send_json(start_camera_provider())
                return
            if path in {"/api/camera/provider/stop", "/api/v1/camera/provider/stop"}:
                self.send_json(stop_camera_provider())
                return
            if path in {"/api/camera/provider/register-start", "/api/v1/camera/provider/register-start"}:
                self.send_json(register_camera_provider())
                return
            if path in {"/api/directshow/camera/register", "/api/v1/directshow/camera/register"}:
                self.send_json(register_directshow_camera())
                return
            if path in {"/api/directshow/camera/unregister", "/api/v1/directshow/camera/unregister"}:
                self.send_json(unregister_directshow_camera())
                return
            if path in {"/api/directshow/camera/sender/build", "/api/v1/directshow/camera/sender/build"}:
                self.send_json(build_directshow_camera_sender())
                return
            if path in {"/api/directshow/camera/sender/start", "/api/v1/directshow/camera/sender/start"}:
                self.send_json(start_directshow_camera_sender())
                return
            if path in {"/api/directshow/camera/sender/stop", "/api/v1/directshow/camera/sender/stop"}:
                self.send_json(stop_directshow_camera_sender())
                return
        except (BridgeClientError, ValueError) as exc:
            detail = exc.to_json()["error"] if isinstance(exc, BridgeClientError) else {"message": str(exc)}
            self.send_error_json(400, "camera_request_failed", str(exc), detail)
            return
        self.send_error_json(404, "not_found", f"No camera-only route for {path}.")

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def send_removed_feature(self) -> None:
        self.send_error_json(
            410,
            "camera_only_feature_removed",
            "This SensorBridge build only supports the iPad camera to Windows virtual camera path.",
        )

    def send_static_file(self, name: str) -> None:
        target = (self.static_dir / name).resolve()
        try:
            target.relative_to(self.static_dir.resolve())
        except ValueError:
            self.send_error_json(403, "forbidden", "Static path escapes static directory.")
            return
        if not target.is_file():
            self.send_error_json(404, "not_found", f"Static file {name} was not found.")
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_common_headers(content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_common_headers("application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, code: str, message: str, detail: Any | None = None) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if detail is not None:
            error["detail"] = detail
        self.send_json({"ok": False, "error": error}, status)

    def send_common_headers(self, content_type: str = "text/plain; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _path_and_query(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlparse(self.path)
        return parsed.path.rstrip("/") if parsed.path != "/" else "/", parse_qs(parsed.query)

    def log_message(self, fmt: str, *args: Any) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] {self.address_string()} {fmt % args}", flush=True)


def build_handler(state: SensorBridgeState, static_dir: Path) -> type[SensorBridgeHandler]:
    class ConfiguredSensorBridgeHandler(SensorBridgeHandler):
        pass

    ConfiguredSensorBridgeHandler.state = state
    ConfiguredSensorBridgeHandler.static_dir = static_dir
    return ConfiguredSensorBridgeHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SensorBridge camera-only Windows receiver")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind. Default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on. Default: 8765")
    parser.add_argument("--data-dir", default="data", help="Directory for runtime state.")
    parser.add_argument(
        "--upstream-url",
        default="http://192.168.0.24:27180",
        help="iPad SensorBridge URL. Default: http://192.168.0.24:27180",
    )
    parser.add_argument("--open-dashboard", action="store_true", help="Open the dashboard after the server starts.")
    parser.add_argument(
        "--start-directshow-camera-sender",
        action="store_true",
        help="Launch the DirectShow sender for SensorBridge Camera frames.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = SensorBridgeState(ROOT / args.data_dir, upstream_url=args.upstream_url)
    handler = build_handler(state, ROOT / "static")
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    lan_ip = get_lan_ip()
    directshow_sender_started = False

    print("SensorBridge Camera Windows receiver", flush=True)
    print(f"Listening on: http://{args.host}:{args.port}", flush=True)
    print(f"Dashboard:    http://{lan_ip}:{args.port}/", flush=True)
    print(f"iPad URL:     {state.upstream_url}", flush=True)
    print(f"Log file:     {state.log_path}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    if args.open_dashboard:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/")).start()

    if args.start_directshow_camera_sender:
        result = start_directshow_camera_sender()
        directshow_sender_started = bool(result.get("running"))
        print(f"DirectShow sender: {json.dumps(result, ensure_ascii=True)}", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SensorBridge Camera.", flush=True)
    finally:
        if directshow_sender_started:
            stop_directshow_camera_sender()
        httpd.server_close()


if __name__ == "__main__":
    main()
