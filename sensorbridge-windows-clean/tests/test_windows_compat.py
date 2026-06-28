from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bridgeclient.windows_compat import inspect_mf_virtual_camera_compatibility


class WindowsCompatTests(unittest.TestCase):
    def test_mf_virtual_camera_probe_reports_unsupported_without_export(self) -> None:
        cim = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=0,
            stdout=json.dumps({"Caption": "Microsoft Windows 10 Pro", "Version": "10.0.19045", "BuildNumber": "19045"}),
            stderr="",
        )
        with (
            patch("bridgeclient.windows_compat.platform.system", return_value="Windows"),
            patch("bridgeclient.windows_compat.platform.version", return_value="10.0.19045"),
            patch("bridgeclient.windows_compat.platform.platform", return_value="Windows-10-test"),
            patch("bridgeclient.windows_compat.subprocess.run", return_value=cim),
            patch("bridgeclient.windows_compat._system32_path", return_value=Path("C:/Windows/System32/mfsensorgroup.dll")),
            patch("bridgeclient.windows_compat.Path.is_file", return_value=False),
        ):
            report = inspect_mf_virtual_camera_compatibility()

        self.assertTrue(report["ok"])
        self.assertEqual(report["os"]["caption"], "Microsoft Windows 10 Pro")
        self.assertEqual(report["os"]["build"], 19045)
        self.assertFalse(report["mfsensorgroup_dll"]["exists"])
        self.assertFalse(report["mfcreatevirtualcamera"]["exported"])
        self.assertFalse(report["mf_virtual_camera_supported"])
        self.assertEqual(report["status"], "unsupported_on_this_windows_build_or_runtime")
        self.assertTrue(report["fallback_required"])

    def test_mf_virtual_camera_probe_reports_supported_when_export_is_present(self) -> None:
        cim = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=0,
            stdout=json.dumps({"Caption": "Microsoft Windows 11 Pro", "Version": "10.0.22631", "BuildNumber": "22631"}),
            stderr="",
        )
        fake_library = SimpleNamespace(MFCreateVirtualCamera=object())
        with (
            patch("bridgeclient.windows_compat.platform.system", return_value="Windows"),
            patch("bridgeclient.windows_compat.platform.version", return_value="10.0.22631"),
            patch("bridgeclient.windows_compat.platform.platform", return_value="Windows-11-test"),
            patch("bridgeclient.windows_compat.subprocess.run", return_value=cim),
            patch("bridgeclient.windows_compat._system32_path", return_value=Path("C:/Windows/System32/mfsensorgroup.dll")),
            patch("bridgeclient.windows_compat.Path.is_file", return_value=True),
            patch("bridgeclient.windows_compat.ctypes.WinDLL", return_value=fake_library),
        ):
            report = inspect_mf_virtual_camera_compatibility()

        self.assertTrue(report["mfsensorgroup_dll"]["exists"])
        self.assertTrue(report["mfsensorgroup_dll"]["loadable"])
        self.assertTrue(report["mfcreatevirtualcamera"]["exported"])
        self.assertTrue(report["mf_virtual_camera_supported"])
        self.assertEqual(report["status"], "supported")


if __name__ == "__main__":
    unittest.main()
