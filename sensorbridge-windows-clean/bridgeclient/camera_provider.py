from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from bridgeclient.windows_compat import inspect_mf_virtual_camera_compatibility


ROOT = Path(__file__).resolve().parents[1]
CAMERA_REGISTER_SCRIPT = ROOT / "drivers" / "camera" / "register-dev.ps1"
POWERSHELL = "powershell"


def inspect_camera_provider_status(root: Path | None = None) -> dict[str, Any]:
    return _run_camera_provider(["-Status"], "camera_provider_status", root=root)


def start_camera_provider(root: Path | None = None) -> dict[str, Any]:
    return _run_camera_provider(["-Start"], "camera_provider_start", root=root)


def register_camera_provider(root: Path | None = None) -> dict[str, Any]:
    return _run_camera_provider(["-Register", "-Start"], "camera_provider_register_start", root=root)


def stop_camera_provider(root: Path | None = None) -> dict[str, Any]:
    return _run_camera_provider(["-Stop"], "camera_provider_stop", root=root)


def _run_camera_provider(arguments: list[str], command: str, *, root: Path | None = None) -> dict[str, Any]:
    project_root = root or ROOT
    script = project_root / "drivers" / "camera" / "register-dev.ps1"
    compatibility = inspect_mf_virtual_camera_compatibility()
    unsupported = not bool(compatibility.get("mf_virtual_camera_supported"))
    changes_system = command != "camera_provider_status"
    if unsupported and changes_system and any(argument in ("-Register", "-Start") for argument in arguments):
        return {
            "ok": False,
            "command": command,
            "component": "VCamSample",
            "mode": "development-session",
            "provider_api": "MediaFoundation.MFCreateVirtualCamera",
            "compatibility": compatibility,
            "mf_virtual_camera_supported_by_current_os": False,
            "fallback_required": True,
            "fallback_recommendation": compatibility.get("fallback_recommendation"),
            "error": {
                "code": "unsupported_on_this_windows_build_or_runtime",
                "message": "MFCreateVirtualCamera is not available on this Windows build/runtime; VCamSample was not launched.",
            },
            "skipped": True,
            "changes_system": False,
            "installs_driver_or_camera": False,
            "creates_camera_while_process_runs": False,
            "installs_permanent_camera": False,
        }
    if not script.is_file():
        return {
            "ok": False,
            "command": command,
            "component": "VCamSample",
            "mode": "development-session",
            "error": "camera_register_script_missing",
            "script": str(script),
            "changes_system": changes_system,
            "installs_driver_or_camera": False,
            "compatibility": compatibility,
            "mf_virtual_camera_supported_by_current_os": bool(compatibility.get("mf_virtual_camera_supported")),
            "fallback_required": not bool(compatibility.get("mf_virtual_camera_supported")),
        }

    proc = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    try:
        payload: dict[str, Any] = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": stdout}

    payload.setdefault("component", "VCamSample")
    payload.setdefault("mode", "development-session")
    payload.setdefault("provider_api", "MediaFoundation.MFCreateVirtualCamera")
    payload.setdefault("compatibility", compatibility)
    payload.setdefault("mf_virtual_camera_supported_by_current_os", bool(compatibility.get("mf_virtual_camera_supported")))
    payload.setdefault("fallback_required", not bool(payload.get("mf_virtual_camera_supported_by_current_os")))
    if payload.get("fallback_required"):
        payload.setdefault(
            "fallback_recommendation",
            "Use a Windows 10-compatible DirectShow virtual source filter or upgrade to Windows 11 for MFCreateVirtualCamera.",
        )
    payload["command"] = command
    payload["script"] = str(script)
    payload["exit_code"] = proc.returncode
    payload["stderr"] = stderr
    payload["changes_system"] = changes_system
    payload["installs_driver_or_camera"] = False
    payload.setdefault("creates_camera_while_process_runs", bool(payload.get("mf_virtual_camera_supported_by_current_os")))
    payload.setdefault("installs_permanent_camera", False)
    if proc.returncode != 0:
        payload["ok"] = False
        payload.setdefault("error", "camera_provider_script_failed")
    else:
        payload.setdefault("ok", True)
    return payload
