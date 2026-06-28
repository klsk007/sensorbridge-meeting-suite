from __future__ import annotations

from typing import Any, Mapping

from bridgeclient.errors import BridgeClientError
from bridgeclient.models import (
    CommandResult,
    JsonDict,
    WebRTCIceCandidate,
    WebRTCReceiverStats,
    WebRTCSessionDescription,
    WebRTCSignalingResult,
    WebRTCStatus,
)
from bridgeclient.transport import Transport


class SensorBridgeClient:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def health(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/health")
        self._raise_if_failed("health", payload)
        return payload

    def status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/status")
        self._raise_if_failed("status", payload)
        return payload

    def network(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/network")
        self._raise_if_failed("network", payload)
        return payload

    def capabilities(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/capabilities")
        self._raise_if_failed("capabilities", payload)
        return payload

    def product_status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/product/status")
        self._raise_if_failed("product_status", payload)
        return payload

    def product_contract(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/product/contract")
        self._raise_if_failed("product_contract", payload)
        return payload

    def start_product_mode(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v1/product/start", {})
        self._raise_if_failed("start_product_mode", payload)
        return payload

    def stop_product_mode(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v1/product/stop", {})
        self._raise_if_failed("stop_product_mode", payload)
        return payload

    def webrtc_status(self) -> WebRTCStatus:
        payload = self.transport.request_json("GET", "/api/v2/webrtc/status")
        self._raise_if_failed("webrtc_status", payload)
        return WebRTCStatus.from_json(payload)

    def post_webrtc_offer(self, description: WebRTCSessionDescription | Mapping[str, Any]) -> WebRTCSignalingResult:
        body = description.to_json() if isinstance(description, WebRTCSessionDescription) else WebRTCSessionDescription.from_json(description).to_json()
        payload = self.transport.request_json("POST", "/api/v2/webrtc/offer", body)
        self._raise_if_failed("webrtc_offer", payload)
        return WebRTCSignalingResult.from_json("webrtc_offer", payload)

    def post_webrtc_ice_candidate(self, candidate: WebRTCIceCandidate | Mapping[str, Any]) -> WebRTCSignalingResult:
        body = candidate.to_json() if isinstance(candidate, WebRTCIceCandidate) else WebRTCIceCandidate.from_json(candidate).to_json()
        payload = self.transport.request_json("POST", "/api/v2/webrtc/ice-candidate", body)
        self._raise_if_failed("webrtc_ice_candidate", payload)
        return WebRTCSignalingResult.from_json("webrtc_ice_candidate", payload)

    def create_webrtc_receiver_offer(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v2/webrtc/receiver/offer", {})
        self._raise_if_failed("webrtc_receiver_offer", payload)
        return payload

    def apply_webrtc_receiver_answer(self, description: WebRTCSessionDescription | Mapping[str, Any]) -> JsonDict:
        body = description.to_json() if isinstance(description, WebRTCSessionDescription) else WebRTCSessionDescription.from_json(description).to_json()
        payload = self.transport.request_json("POST", "/api/v2/webrtc/receiver/answer", body)
        self._raise_if_failed("webrtc_receiver_answer", payload)
        return payload

    def add_webrtc_receiver_ice_candidate(self, candidate: WebRTCIceCandidate | Mapping[str, Any]) -> JsonDict:
        body = candidate.to_json() if isinstance(candidate, WebRTCIceCandidate) else WebRTCIceCandidate.from_json(candidate).to_json()
        payload = self.transport.request_json("POST", "/api/v2/webrtc/receiver/ice-candidate", body)
        self._raise_if_failed("webrtc_receiver_ice_candidate", payload)
        return payload

    def webrtc_local_ice_candidates(self) -> WebRTCSignalingResult:
        payload = self.transport.request_json("GET", "/api/v2/webrtc/local-ice-candidates")
        self._raise_if_failed("webrtc_local_ice_candidates", payload)
        return WebRTCSignalingResult.from_json("webrtc_local_ice_candidates", payload)

    def connect_webrtc_receiver(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v2/webrtc/connect", {})
        self._raise_if_failed("connect_webrtc_receiver", payload)
        return payload

    def post_webrtc_receiver_stats(self, stats: WebRTCReceiverStats | Mapping[str, Any]) -> JsonDict:
        body = stats.to_json() if isinstance(stats, WebRTCReceiverStats) else WebRTCReceiverStats.from_json(stats).to_json()
        payload = self.transport.request_json("POST", "/api/v2/webrtc/receiver-stats", body)
        self._raise_if_failed("webrtc_receiver_stats", payload)
        return payload

    def receiver_stats(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v2/webrtc/receiver-stats")
        self._raise_if_failed("receiver_stats", payload)
        return payload

    def directshow_camera_status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/directshow/camera/status")
        self._raise_if_failed("directshow_camera_status", payload)
        return payload

    def directshow_camera_open_status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/directshow/camera/open-status")
        self._raise_if_failed("directshow_camera_open_status", payload)
        return payload

    def directshow_camera_sender_status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/directshow/camera/sender/status")
        self._raise_if_failed("directshow_camera_sender_status", payload)
        return payload

    def start_directshow_camera_sender(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/directshow/camera/sender/start", {})
        self._raise_if_failed("start_directshow_camera_sender", payload)
        return payload

    def stop_directshow_camera_sender(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/directshow/camera/sender/stop", {})
        self._raise_if_failed("stop_directshow_camera_sender", payload)
        return payload

    def camera_provider_status(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/camera/provider/status")
        self._raise_if_failed("camera_provider_status", payload)
        return payload

    def start_camera_provider(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/camera/provider/start", {})
        self._raise_if_failed("start_camera_provider", payload)
        return payload

    def stop_camera_provider(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/camera/provider/stop", {})
        self._raise_if_failed("stop_camera_provider", payload)
        return payload

    def reset_session(self) -> CommandResult:
        return CommandResult(ok=True, command="reset_session", raw={"product": "camera_only"})

    def doctor(self) -> JsonDict:
        checks = [
            {"name": "health", "required": True, "payload": self.health()},
            {"name": "capabilities", "required": True, "payload": self.capabilities()},
            {"name": "product_status", "required": True, "payload": self.product_status()},
            {"name": "directshow_camera_status", "required": False, "payload": self.directshow_camera_status()},
        ]
        for check in checks:
            payload = check["payload"]
            check["ok"] = bool(payload.get("ok", True)) if isinstance(payload, Mapping) else False
        return {
            "ok": all(bool(check["ok"]) for check in checks if check["required"]),
            "command": "doctor",
            "product": "camera_only",
            "checks": checks,
        }

    def _raise_if_failed(self, command: str, payload: Mapping[str, Any]) -> None:
        if payload.get("ok", True):
            return
        error = payload.get("error")
        code = "request_failed"
        message = f"SensorBridge command '{command}' failed."
        if isinstance(error, Mapping):
            code = str(error.get("code") or code)
            message = str(error.get("message") or message)
        elif error:
            message = str(error)
        raise BridgeClientError(message, code=code, detail={"command": command, "payload": dict(payload)})
