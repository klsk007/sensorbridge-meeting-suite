from __future__ import annotations

from typing import Any, Mapping

from bridgeclient.errors import BridgeClientError
from bridgeclient.models import AudioFrame, CommandResult, JsonDict
from bridgeclient.transport import Transport


class SensorBridgeClient:
    """Minimal iPhone/iPad SensorBridge client for microphone-only Windows use."""

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

    def capabilities(self) -> JsonDict:
        payload = self.transport.request_json("GET", "/api/v1/capabilities")
        self._raise_if_failed("capabilities", payload)
        return payload

    def start_audio(self) -> CommandResult:
        return self._command("start_audio", "/api/v1/audio/start")

    def stop_audio(self) -> CommandResult:
        return self._command("stop_audio", "/api/v1/audio/stop")

    def request_upstream_audio_start(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v1/upstream/audio/start", {})
        self._raise_if_failed("request_upstream_audio_start", payload)
        return payload

    def pull_upstream_audio_frame(self) -> JsonDict:
        payload = self.transport.request_json("POST", "/api/v1/upstream/pull/audio-frame", {})
        self._raise_if_failed("pull_upstream_audio_frame", payload)
        return payload

    def sample_audio_frame(self) -> AudioFrame:
        payload = self.transport.request_json("GET", "/api/v1/sample/audio-frame")
        self._raise_if_failed("sample_audio", payload)
        try:
            return AudioFrame.from_json(payload)
        except ValueError as exc:
            raise BridgeClientError(
                "SensorBridge audio sample response is missing required fields.",
                code="invalid_audio_sample",
                detail={"error": str(exc), "payload": payload},
            ) from exc

    def _command(self, command: str, path: str) -> CommandResult:
        payload = self.transport.request_json("POST", path, {})
        self._raise_if_failed(command, payload)
        return CommandResult.from_json(command, payload)

    def _raise_if_failed(self, command: str, payload: Mapping[str, Any]) -> None:
        if payload.get("ok", True) is not False:
            return
        error = payload.get("error")
        message = f"SensorBridge command '{command}' failed."
        if isinstance(error, Mapping) and error.get("message"):
            message = str(error["message"])
        raise BridgeClientError(
            message,
            code="bridge_command_failed",
            detail={"command": command, "payload": dict(payload)},
        )
