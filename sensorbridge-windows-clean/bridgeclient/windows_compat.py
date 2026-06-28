from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


def inspect_mf_virtual_camera_compatibility() -> dict[str, Any]:
    system = platform.system()
    version = platform.version()
    build = _windows_build_from_version(version)
    report: dict[str, Any] = {
        "ok": True,
        "command": "mf_virtual_camera_compatibility",
        "changes_system": False,
        "platform": platform.platform(),
        "os": {
            "system": system,
            "caption": None,
            "version": version,
            "build": build,
        },
        "required_build": 22000,
        "mfsensorgroup_dll": {
            "path": None,
            "exists": False,
            "loadable": False,
        },
        "mfcreatevirtualcamera": {
            "exported": False,
            "callable": False,
        },
        "mf_virtual_camera_supported": False,
        "status": "unsupported_on_this_windows_build_or_runtime",
        "notes": [
            "This probe does not start providers, install drivers, enable test signing, or reboot.",
            "MFCreateVirtualCamera is the Windows 11 Media Foundation route used by VCamSample.",
        ],
    }

    if system.lower() != "windows":
        report["ok"] = False
        report["error"] = {"code": "not_windows", "message": "Media Foundation virtual camera compatibility is Windows-only."}
        return report

    report["os"].update(_read_windows_os_cim())
    if report["os"].get("build") is None:
        report["os"]["build"] = build

    dll_path = _system32_path("mfsensorgroup.dll")
    report["mfsensorgroup_dll"]["path"] = str(dll_path)
    report["mfsensorgroup_dll"]["exists"] = dll_path.is_file()

    if dll_path.is_file():
        try:
            library = ctypes.WinDLL(str(dll_path))
            report["mfsensorgroup_dll"]["loadable"] = True
            try:
                getattr(library, "MFCreateVirtualCamera")
                report["mfcreatevirtualcamera"]["exported"] = True
                report["mfcreatevirtualcamera"]["callable"] = True
            except AttributeError:
                pass
        except OSError as exc:
            report["mfsensorgroup_dll"]["load_error"] = str(exc)

    os_build = report["os"].get("build")
    build_supported = isinstance(os_build, int) and os_build >= int(report["required_build"])
    supported = build_supported and bool(report["mfsensorgroup_dll"]["loadable"]) and bool(
        report["mfcreatevirtualcamera"]["exported"]
    )
    report["mf_virtual_camera_supported"] = supported
    report["status"] = "supported" if supported else "unsupported_on_this_windows_build_or_runtime"
    if not supported:
        report["fallback_required"] = True
        report["fallback_recommendation"] = (
            "Use a Windows 10-compatible DirectShow virtual source filter, or run the Media Foundation provider on "
            "Windows build 22000+ with mfsensorgroup.dll exporting MFCreateVirtualCamera."
        )
    return report


def _windows_build_from_version(version: str) -> int | None:
    parts = version.split(".")
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def _read_windows_os_cim() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                    "$OutputEncoding=[System.Text.Encoding]::UTF8; "
                    "Get-CimInstance Win32_OperatingSystem | "
                    "Select-Object Caption,Version,BuildNumber | ConvertTo-Json -Compress"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    build = payload.get("BuildNumber")
    try:
        build_int = int(build) if build is not None else None
    except (TypeError, ValueError):
        build_int = None
    return {
        "caption": payload.get("Caption"),
        "version": payload.get("Version") or platform.version(),
        "build": build_int,
    }


def _system32_path(filename: str) -> Path:
    root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    return Path(root) / "System32" / filename
