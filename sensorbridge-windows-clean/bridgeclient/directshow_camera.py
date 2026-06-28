from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = "powershell"


def inspect_directshow_camera_build_status(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "build-dev.ps1",
        [],
        "directshow_camera_build_status",
        root=root,
        changes_system=False,
        timeout_s=45,
    )


def inspect_directshow_camera_register_status(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "register-dev.ps1",
        ["-Status"],
        "directshow_camera_register_status",
        root=root,
        changes_system=False,
        timeout_s=45,
    )


def register_directshow_camera(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "register-dev.ps1",
        ["-Register"],
        "directshow_camera_register",
        root=root,
        changes_system=True,
        timeout_s=90,
    )


def unregister_directshow_camera(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "register-dev.ps1",
        ["-Unregister"],
        "directshow_camera_unregister",
        root=root,
        changes_system=True,
        timeout_s=90,
    )


def inspect_directshow_camera_sender_status(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "sender-dev.ps1",
        ["-Status"],
        "directshow_camera_sender_status",
        root=root,
        changes_system=False,
        timeout_s=45,
    )


def inspect_directshow_camera_open_status(root: Path | None = None, *, timeout_ms: int = 5000) -> dict[str, Any]:
    project_root = root or ROOT
    script = project_root / "tools" / "directshow-camera-open-probe.ps1"
    if not script.is_file():
        return {
            "ok": False,
            "command": "directshow_camera_open_status",
            "component": "softcam",
            "provider_api": "DirectShow",
            "changes_system": False,
            "installs_driver_or_camera": False,
            "script": str(script),
            "error": {"code": "directshow_camera_open_probe_missing", "message": "DirectShow camera open probe was not found."},
        }
    payload = _run_powershell_json(
        script,
        ["-TimeoutMilliseconds", str(timeout_ms)],
        "directshow_camera_open_status",
        changes_system=False,
        timeout_s=max(10, timeout_ms / 1000 + 10),
    )
    payload["opens_camera_now"] = bool(payload.get("ok"))
    payload["visible_to_windows_apps"] = bool(payload.get("ok"))
    return payload


def build_directshow_camera_sender(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "sender-dev.ps1",
        ["-Build"],
        "directshow_camera_sender_build",
        root=root,
        changes_system=False,
        timeout_s=120,
    )


def start_directshow_camera_sender(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "sender-dev.ps1",
        ["-Start"],
        "directshow_camera_sender_start",
        root=root,
        changes_system=False,
        timeout_s=45,
    )


def stop_directshow_camera_sender(root: Path | None = None) -> dict[str, Any]:
    return _run_directshow_camera_script(
        "sender-dev.ps1",
        ["-Stop"],
        "directshow_camera_sender_stop",
        root=root,
        changes_system=False,
        timeout_s=45,
    )


def _run_directshow_camera_script(
    script_name: str,
    arguments: list[str],
    command: str,
    *,
    root: Path | None = None,
    changes_system: bool,
    timeout_s: float,
) -> dict[str, Any]:
    project_root = root or ROOT
    script = project_root / "drivers" / "camera" / "directshow" / script_name
    if not script.is_file():
        return {
            "ok": False,
            "command": command,
            "component": "softcam",
            "provider_api": "DirectShow",
            "changes_system": changes_system,
            "installs_driver_or_camera": False,
            "script": str(script),
            "error": {"code": "directshow_camera_script_missing", "message": f"{script_name} was not found."},
        }
    return _run_powershell_json(
        script,
        arguments,
        command,
        changes_system=changes_system,
        timeout_s=timeout_s,
    )


def _run_powershell_json(
    script: Path,
    arguments: list[str],
    command: str,
    *,
    changes_system: bool,
    timeout_s: float,
) -> dict[str, Any]:
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
        timeout=timeout_s,
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    try:
        payload: dict[str, Any] = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": stdout}

    payload["command"] = command
    payload.setdefault("component", "softcam")
    payload.setdefault("provider_api", "DirectShow")
    payload["script"] = str(script)
    payload["exit_code"] = proc.returncode
    payload["stderr"] = stderr
    payload["changes_system"] = changes_system
    payload["installs_driver_or_camera"] = False
    payload.setdefault("visible_to_windows_apps", False)
    payload.setdefault("creates_windows_camera_now", False)
    payload.setdefault("requires_enumeration_probe", True)
    if proc.returncode != 0:
        payload["ok"] = False
        payload.setdefault("error", "directshow_camera_script_failed")
    else:
        payload.setdefault("ok", True)
    return payload
