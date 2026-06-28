from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sensorbridge import SensorBridgeHandler, SensorBridgeState


ROOT = Path(__file__).resolve().parents[1]


class CameraOnlyServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = SensorBridgeState(ROOT / "tmp-test-data")

        class Handler(SensorBridgeHandler):
            pass

        Handler.state = self.state
        Handler.static_dir = ROOT / "static"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.state.stop_webrtc_receiver_stats_heartbeat()

    def request_json(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_product_status_is_camera_only(self) -> None:
        payload = self.request_json("GET", "/api/v1/product/status")

        self.assertEqual(payload["command"], "product_status")
        self.assertEqual(payload["product"], "camera_only")
        self.assertEqual(payload["activeCameraTransport"], "webrtc")
        for key in (
            "receivedFps",
            "decodedFps",
            "virtualCameraFps",
            "latestFrameAgeMs",
            "estimatedLatencyMs",
            "droppedFrames",
            "normalWindowsCameraVisible",
        ):
            self.assertIn(key, payload)
        self.assertNotIn("microphone", payload)
        self.assertNotIn("speaker_return", payload)
        self.assertNotIn("accelerometer", payload)

    def test_upstream_audio_status_is_scrubbed_from_camera_only_payload(self) -> None:
        from bridgeclient.models import WebRTCStatus

        self.state._last_upstream_status = WebRTCStatus.from_json(
            {
                "transportMode": "webrtc",
                "realIpadCamera": True,
                "cameraTrackReady": True,
                "microphoneTrackReady": True,
                "audioCodec": "opus",
                "virtualMicrophoneReady": False,
                "nextAction": "start_camera_microphone_then_retry_webrtc_offer",
            }
        )

        payload = self.request_json("GET", "/api/v2/webrtc/status")
        text = json.dumps(payload).lower()

        self.assertNotIn("microphone", text)
        self.assertNotIn("audio", text)
        self.assertNotIn("speaker", text)
        self.assertNotIn("accelerometer", text)

    def test_removed_feature_routes_return_410(self) -> None:
        for method, path in (
            ("GET", "/api/v1/sample/video-frame"),
            ("POST", "/api/v1/camera/feed/start"),
            ("POST", "/api/v1/upstream/pull/video-frame"),
            ("POST", "/api/v1/audio/start"),
            ("POST", "/api/v1/speaker/start"),
            ("POST", "/api/v1/acceleration/start"),
            ("GET", "/api/v1/sample/acceleration"),
            ("GET", "/phone"),
        ):
            with self.subTest(path=path):
                request = Request(self.base_url + path, data=b"{}" if method == "POST" else None, method=method)
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request, timeout=5)
                self.assertEqual(raised.exception.code, 410)
                body = json.loads(raised.exception.read().decode("utf-8"))
                self.assertEqual(body["error"]["code"], "camera_only_feature_removed")

    def test_product_start_uses_webrtc_without_jpeg_fallback(self) -> None:
        payload = self.request_json("POST", "/api/v1/product/start", {})

        self.assertEqual(payload["command"], "start_product_mode")
        self.assertTrue(payload["requested"]["webrtc_receiver"])
        self.assertTrue(payload["requested"]["directshow_camera_sender"])
        for removed_key in (
            "upstream_video_start",
            "upstream_audio_start",
            "camera_feed_start",
            "speaker_loopback",
            "upstream_acceleration_start",
        ):
            self.assertNotIn(removed_key, payload)
        self.assertEqual(payload["acceptance_snapshot"]["activeCameraTransport"], "webrtc")


class CameraOnlyUiTests(unittest.TestCase):
    def test_dashboard_contains_only_camera_controls(self) -> None:
        html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("SensorBridge Camera", html)
        self.assertIn("activeCameraTransport", html)
        self.assertIn("virtualCameraFps", html)
        self.assertIn("/api/v2/webrtc/status", script)
        self.assertIn("/api/v1/product/start", script)
        banned = ("microphone", "speaker", "accelerometer", "sample/video-frame", "camera/feed/start")
        for text in banned:
            with self.subTest(text=text):
                self.assertNotIn(text, html.lower())
                self.assertNotIn(text, script.lower())

    def test_winforms_app_source_is_camera_only(self) -> None:
        source = (ROOT / "windows-app" / "SensorBridge.App" / "Program.cs").read_text(encoding="utf-8")

        self.assertIn("-ProductMode -Json", source)
        self.assertIn("/api/v1/product/status", source)
        self.assertIn("activeCameraTransport", source)
        self.assertIn("virtualCameraFps", source)
        self.assertIn("Use your iPad as a Windows virtual camera", source)
        for text in ("MicrophoneTruthLine", "SpeakerTruthLine", "_microphoneStatus", "_speakerStatus", "_accelerometerStatus"):
            self.assertNotIn(text, source)


class CameraOnlyWebRTCTests(unittest.TestCase):
    def test_receiver_stats_payload_is_camera_only(self) -> None:
        from bridgeclient.models import WebRTCReceiverStats

        payload = WebRTCReceiverStats(
            receiver_state="decoded_video",
            received_fps=30,
            decoded_fps=30,
            virtual_camera_fps=30,
            dropped_frames=2,
        ).to_json()

        self.assertEqual(payload["receiverState"], "decoded_video")
        self.assertEqual(payload["virtualCameraFps"], 30.0)
        self.assertEqual(payload["droppedFrames"], 2)
        self.assertNotIn("audioPacketsReceived", payload)
        self.assertNotIn("virtualMicrophoneReady", payload)


if __name__ == "__main__":
    unittest.main()
