from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIRTUAL_MICROPHONE_TERMS = ("sensorbridge", "sysvad", "virtual microphone", "virtual mic")
COMPATIBLE_MICROPHONE_ROUTE_TERMS = (
    "vb-audio",
    "virtual cable",
    "cable output",
    "voicemeeter",
)


def inspect_media_devices(root: Path | None = None, *, timeout_s: float = 12.0) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    project = project_root / "tools" / "MediaDeviceProbe" / "MediaDeviceProbe.csproj"
    report: dict[str, Any] = {
        "ok": False,
        "command": "media_devices",
        "changes_system": False,
        "method": "Windows.Devices.Enumeration.DeviceInformation.FindAllAsync",
        "probe_project": str(project),
        "audioCapture": [],
        "audioRender": [],
        "audio_capture_count": 0,
        "audio_render_count": 0,
        "matched_virtual_microphones": [],
        "matched_compatible_microphone_routes": [],
        "windows_detects_microphone_now": False,
        "windows_detects_compatible_microphone_route_now": False,
        "normal_app_microphone_visible": False,
        "notes": [
            "This check enumerates Windows audio devices only; it does not install, enable, or remove devices.",
            "SensorBridge Microphone appears only after the audio driver is signed, installed, loaded, and exposes an AudioEndpoint.",
            "Compatible virtual-audio capture devices are reported as integration candidates, not as SensorBridge endpoints.",
        ],
    }
    if not project.is_file():
        report["error"] = {"code": "probe_project_missing", "message": "MediaDeviceProbe project was not found."}
        return report

    command, mode = _probe_command(project)
    report["probe_mode"] = mode
    report["dotnet"] = shutil.which("dotnet")
    if command is None:
        return _inspect_pnp_audio_devices(report, reason="dotnet_missing")

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _inspect_pnp_audio_devices(report, reason="probe_timeout")
    except (OSError, subprocess.SubprocessError) as exc:
        report["error"] = {"code": "probe_failed", "message": str(exc)}
        return _inspect_pnp_audio_devices(report, reason="probe_failed")

    report["exit_code"] = result.returncode
    if result.returncode != 0:
        report["error"] = {
            "code": "probe_failed",
            "message": "MediaDeviceProbe returned a non-zero exit code.",
            "stderr": (result.stderr or "").strip()[:2000],
            "stdout": (result.stdout or "").strip()[:2000],
        }
        return _inspect_pnp_audio_devices(report, reason="probe_failed")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        report["error"] = {"code": "probe_non_json", "message": "MediaDeviceProbe returned non-JSON output."}
        return report
    if not isinstance(payload, dict):
        report["error"] = {"code": "probe_unexpected_shape", "message": "MediaDeviceProbe returned an unexpected payload."}
        return report

    for key in ("audioCapture", "audioRender"):
        value = payload.get(key)
        report[key] = value if isinstance(value, list) else []
    report["audio_capture_count"] = len(report["audioCapture"])
    report["audio_render_count"] = len(report["audioRender"])
    report["matched_virtual_microphones"] = _matching_devices(report["audioCapture"], VIRTUAL_MICROPHONE_TERMS)
    report["matched_available_virtual_microphones"] = _available_audio_endpoints(report["matched_virtual_microphones"])
    report["matched_compatible_microphone_routes"] = _matching_devices(
        report["audioCapture"], COMPATIBLE_MICROPHONE_ROUTE_TERMS
    )
    report["windows_detects_microphone_now"] = bool(report["matched_available_virtual_microphones"])
    report["windows_detects_compatible_microphone_route_now"] = bool(report["matched_compatible_microphone_routes"])
    report["normal_app_microphone_visible"] = report["windows_detects_microphone_now"]
    report["ok"] = True
    return report


def inspect_microphone_route_status(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    media = inspect_media_devices(project_root)

    from bridgeclient.microphone import inspect_microphone_install_plan, inspect_microphone_install_status
    from bridgeclient.microphone_feeder import inspect_microphone_pcm_feeder

    install_status = inspect_microphone_install_status(project_root)
    install_plan = inspect_microphone_install_plan(project_root)
    feeder = inspect_microphone_pcm_feeder()
    verification = install_status.get("verification") if isinstance(install_status.get("verification"), dict) else {}
    audio_endpoint_count = int(verification.get("audio_endpoint_count", 0) or 0)
    endpoint_visible = bool(media.get("normal_app_microphone_visible"))
    endpoint_present = audio_endpoint_count > 0 or bool(media.get("matched_virtual_microphones"))
    return {
        "ok": bool(media.get("ok")) and bool(install_plan.get("ok")),
        "command": "microphone_route_status",
        "changes_system": False,
        "device_enumerated": endpoint_present,
        "audio_endpoint_present": endpoint_present,
        "audio_endpoint_count": audio_endpoint_count,
        "normal_app_visible": endpoint_visible,
        "latest_pcm_handoff_ready": bool(feeder.can_feed_driver),
        "install_stage": install_plan.get("stage"),
        "next_step": "ready" if endpoint_visible else install_plan.get("next_step"),
        "next_command": None if endpoint_visible else install_plan.get("next_command"),
        "requires_reboot": bool(install_plan.get("requires_reboot")),
        "media_devices": media,
        "install_status": install_status,
        "install_plan": install_plan,
        "feeder": feeder.to_json(),
        "completion_rule": "Complete only when Windows exposes SensorBridge Microphone as a recording endpoint visible to normal apps.",
    }


def _probe_command(project: Path) -> tuple[list[str] | None, str]:
    built = sorted(project.parent.glob("bin/Debug/net*-windows*/MediaDeviceProbe.exe"))
    if built:
        return [str(built[-1])], "built_exe"
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return None, "missing_dotnet"
    return [dotnet, "run", "--no-restore", "--project", str(project)], "dotnet_run"


def _inspect_pnp_audio_devices(report: dict[str, Any], *, reason: str) -> dict[str, Any]:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    report["fallback_reason"] = reason
    report["fallback_method"] = "Get-PnpDevice AudioEndpoint/MEDIA"
    if not powershell:
        report.setdefault("error", {"code": "powershell_missing", "message": "PowerShell was not found."})
        return report
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$devices=@();"
        "foreach($class in @('AudioEndpoint','MEDIA')){"
        "Get-PnpDevice -Class $class | ForEach-Object {"
        "$devices += [ordered]@{id=$_.InstanceId; name=$_.FriendlyName; class=$_.Class; status=$_.Status; isEnabled=($_.Status -eq 'OK')}"
        "}"
        "};"
        "[ordered]@{ok=$true; audioCapture=$devices; audioRender=@()} | ConvertTo-Json -Depth 5"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report["error"] = {"code": "pnp_probe_failed", "message": str(exc)}
        return report
    if result.returncode != 0:
        report["error"] = {
            "code": "pnp_probe_failed",
            "message": (result.stderr or result.stdout or "").strip()[:2000],
        }
        return report
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        report["error"] = {"code": "pnp_probe_non_json", "message": "PowerShell PnP probe returned non-JSON output."}
        return report
    audio_capture = payload.get("audioCapture") if isinstance(payload, dict) else []
    if isinstance(audio_capture, dict):
        audio_capture = [audio_capture]
    report["audioCapture"] = audio_capture if isinstance(audio_capture, list) else []
    report["audioRender"] = []
    report["audio_capture_count"] = len(report["audioCapture"])
    report["audio_render_count"] = 0
    report["matched_virtual_microphones"] = _matching_devices(report["audioCapture"], VIRTUAL_MICROPHONE_TERMS)
    report["matched_available_virtual_microphones"] = _available_audio_endpoints(report["matched_virtual_microphones"])
    report["matched_compatible_microphone_routes"] = _matching_devices(
        report["audioCapture"], COMPATIBLE_MICROPHONE_ROUTE_TERMS
    )
    report["windows_detects_microphone_now"] = any(
        device.get("class") == "AudioEndpoint" for device in report["matched_available_virtual_microphones"]
    )
    report["driver_node_present"] = bool(report["matched_virtual_microphones"])
    report["windows_detects_compatible_microphone_route_now"] = bool(report["matched_compatible_microphone_routes"])
    report["normal_app_microphone_visible"] = bool(report["windows_detects_microphone_now"])
    report["ok"] = True
    return report


def _matching_devices(devices: list[Any], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        name = str(device.get("name") or "")
        if any(term in name.lower() for term in terms):
            matches.append(device)
    return matches


def _available_audio_endpoints(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        device
        for device in devices
        if device.get("class") == "AudioEndpoint"
        and _is_capture_endpoint_id(str(device.get("id") or device.get("instance_id") or ""))
        and bool(device.get("isEnabled"))
        and str(device.get("status") or "").lower() == "ok"
    ]


def _is_capture_endpoint_id(instance_id: str) -> bool:
    return "{0.0.1." in instance_id.upper()
