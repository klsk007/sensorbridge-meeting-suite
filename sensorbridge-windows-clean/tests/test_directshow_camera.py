from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridgeclient.directshow_camera import (
    build_directshow_camera_sender,
    inspect_directshow_camera_build_status,
    inspect_directshow_camera_open_status,
    inspect_directshow_camera_register_status,
    inspect_directshow_camera_sender_status,
    register_directshow_camera,
    start_directshow_camera_sender,
)


class DirectShowCameraTests(unittest.TestCase):
    def test_build_status_runs_safe_status_script(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "command": "directshow_camera_build",
                    "changes_system": False,
                    "readiness": {"can_register_after_build": False},
                }
            ),
            stderr="",
        )
        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = inspect_directshow_camera_build_status(Path(__file__).resolve().parents[1])

        self.assertTrue(report["ok"])
        self.assertEqual(report["command"], "directshow_camera_build_status")
        self.assertFalse(report["changes_system"])
        self.assertFalse(report["installs_driver_or_camera"])
        run_mock.assert_called_once()
        self.assertNotIn("-Register", run_mock.call_args.args[0])

    def test_register_status_does_not_claim_app_visibility_from_registry_only(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "registered_after": True,
                    "creates_windows_camera_now": False,
                    "visible_to_windows_apps": False,
                }
            ),
            stderr="",
        )
        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result):
            report = inspect_directshow_camera_register_status(Path(__file__).resolve().parents[1])

        self.assertTrue(report["registered_after"])
        self.assertFalse(report["creates_windows_camera_now"])
        self.assertFalse(report["visible_to_windows_apps"])
        self.assertFalse(report["changes_system"])

    def test_register_command_is_explicit_system_change(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "registered_after": True}),
            stderr="",
        )
        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = register_directshow_camera(Path(__file__).resolve().parents[1])

        self.assertTrue(report["ok"])
        self.assertEqual(report["command"], "directshow_camera_register")
        self.assertTrue(report["changes_system"])
        self.assertFalse(report["installs_driver_or_camera"])
        self.assertIn("-Register", run_mock.call_args.args[0])

    def test_sender_controls_are_user_mode_and_explicit(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "running": False,
                    "changes_system": False,
                    "installs_driver_or_camera": False,
                }
            ),
            stderr="",
        )
        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = inspect_directshow_camera_sender_status(Path(__file__).resolve().parents[1])

        self.assertEqual(report["command"], "directshow_camera_sender_status")
        self.assertFalse(report["changes_system"])
        self.assertFalse(report["installs_driver_or_camera"])
        self.assertIn("-Status", run_mock.call_args.args[0])

        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = build_directshow_camera_sender(Path(__file__).resolve().parents[1])

        self.assertEqual(report["command"], "directshow_camera_sender_build")
        self.assertFalse(report["changes_system"])
        self.assertIn("-Build", run_mock.call_args.args[0])

        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = start_directshow_camera_sender(Path(__file__).resolve().parents[1])

        self.assertEqual(report["command"], "directshow_camera_sender_start")
        self.assertFalse(report["changes_system"])
        self.assertIn("-Start", run_mock.call_args.args[0])

    def test_open_status_runs_directshow_capture_probe(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "command": "directshow_camera_open_probe",
                    "selected": "SensorBridge Camera",
                    "buffer_bytes": 921600,
                    "width": 640,
                    "height": 480,
                }
            ),
            stderr="",
        )
        with patch("bridgeclient.directshow_camera.subprocess.run", return_value=result) as run_mock:
            report = inspect_directshow_camera_open_status(Path(__file__).resolve().parents[1], timeout_ms=1234)

        self.assertEqual(report["command"], "directshow_camera_open_status")
        self.assertTrue(report["ok"])
        self.assertEqual(report["selected"], "SensorBridge Camera")
        self.assertEqual(report["buffer_bytes"], 921600)
        self.assertTrue(report["opens_camera_now"])
        self.assertTrue(report["visible_to_windows_apps"])
        self.assertFalse(report["changes_system"])
        command_line = " ".join(str(part) for part in run_mock.call_args.args[0])
        self.assertIn("directshow-camera-open-probe.ps1", command_line)
        self.assertIn("1234", command_line)
