from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from bridgeclient.camera_provider import inspect_camera_provider_status, start_camera_provider, stop_camera_provider


class CameraProviderTests(unittest.TestCase):
    def test_status_runs_register_script_without_system_change(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=0,
            stdout='{"ok": true, "registered_after": true, "running_after": true, "mf_virtual_camera_supported_by_current_os": true}',
            stderr="",
        )
        with (
            patch(
                "bridgeclient.camera_provider.inspect_mf_virtual_camera_compatibility",
                return_value={"ok": True, "mf_virtual_camera_supported": True},
            ),
            patch("bridgeclient.camera_provider.subprocess.run", return_value=completed) as run_mock,
        ):
            report = inspect_camera_provider_status(Path(__file__).resolve().parents[1])

        self.assertTrue(report["ok"])
        self.assertEqual(report["command"], "camera_provider_status")
        self.assertFalse(report["changes_system"])
        self.assertFalse(report["installs_driver_or_camera"])
        self.assertTrue(report["creates_camera_while_process_runs"])
        self.assertIn("-Status", run_mock.call_args.args[0])

    def test_start_and_stop_are_process_controls_not_driver_installs(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=0,
            stdout='{"ok": true, "registered_after": true, "running_after": true, "mf_virtual_camera_supported_by_current_os": true}',
            stderr="",
        )
        with (
            patch(
                "bridgeclient.camera_provider.inspect_mf_virtual_camera_compatibility",
                return_value={"ok": True, "mf_virtual_camera_supported": True},
            ),
            patch("bridgeclient.camera_provider.subprocess.run", return_value=completed) as run_mock,
        ):
            start_report = start_camera_provider(Path(__file__).resolve().parents[1])
            stop_report = stop_camera_provider(Path(__file__).resolve().parents[1])

        self.assertEqual(start_report["command"], "camera_provider_start")
        self.assertEqual(stop_report["command"], "camera_provider_stop")
        self.assertTrue(start_report["changes_system"])
        self.assertFalse(start_report["installs_driver_or_camera"])
        self.assertIn("-Start", run_mock.call_args_list[0].args[0])
        self.assertIn("-Stop", run_mock.call_args_list[1].args[0])

    def test_status_includes_media_foundation_os_support(self) -> None:
        with (
            patch(
                "bridgeclient.camera_provider.inspect_mf_virtual_camera_compatibility",
                return_value={
                    "ok": True,
                    "mf_virtual_camera_supported": False,
                    "fallback_recommendation": "Use a Windows 10-compatible DirectShow virtual source filter.",
                },
            ),
            patch("bridgeclient.camera_provider.subprocess.run") as run_mock,
        ):
            report = start_camera_provider(Path(__file__).resolve().parents[1])

        self.assertFalse(report["mf_virtual_camera_supported_by_current_os"])
        self.assertTrue(report["fallback_required"])
        self.assertIn("DirectShow", report["fallback_recommendation"])
        self.assertEqual(report["error"]["code"], "unsupported_on_this_windows_build_or_runtime")
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
