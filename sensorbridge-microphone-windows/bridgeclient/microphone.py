from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _program_files_x86() -> Path:
    return Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))


def find_msbuild() -> str | None:
    vswhere = _program_files_x86() / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere.is_file():
        queries = (
            [
                "-latest",
                "-products",
                "*",
                "-requiresAny",
                "-requires",
                "Microsoft.Component.MSBuild",
                "-find",
                r"MSBuild\**\Bin\amd64\MSBuild.exe",
            ],
            ["-latest", "-products", "*", "-find", r"MSBuild\**\Bin\amd64\MSBuild.exe"],
            ["-latest", "-products", "*", "-find", r"MSBuild\**\Bin\MSBuild.exe"],
        )
        for query in queries:
            try:
                result = subprocess.run(
                    [str(vswhere), *query],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                for line in (result.stdout or "").splitlines():
                    if line.strip():
                        return line.strip()
            except (OSError, subprocess.SubprocessError):
                pass

    for candidate in (
        _program_files_x86() / "Microsoft Visual Studio" / "2022" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "amd64" / "MSBuild.exe",
        _program_files_x86() / "Microsoft Visual Studio" / "2022" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
        _program_files_x86() / "Microsoft Visual Studio" / "2019" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "amd64" / "MSBuild.exe",
        _program_files_x86() / "Microsoft Visual Studio" / "2019" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
    ):
        if candidate.is_file():
            return str(candidate)

    return shutil.which("msbuild.exe")


def wdk_available() -> bool:
    kit_root = _program_files_x86() / "Windows Kits" / "10"
    return (kit_root / "Include").is_dir() and (kit_root / "Lib").is_dir()


def _visual_studio_roots() -> list[Path]:
    roots: list[Path] = []
    for year in ("2022", "2019"):
        base = _program_files_x86() / "Microsoft Visual Studio" / year
        for edition in ("BuildTools", "Community", "Professional", "Enterprise"):
            candidate = base / edition
            if candidate.is_dir():
                roots.append(candidate)
    return roots


def _first_existing(paths: list[Path]) -> str | None:
    for path in paths:
        if path.exists():
            return str(path)
    return None


def inspect_driver_build_prerequisites(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    source_root = project_root / "third_party" / "src" / "Windows-driver-samples"
    sysvad_dir = source_root / "audio" / "sysvad"
    package_dir = sysvad_dir / "x64" / "Debug" / "package"
    package_files = [
        "TabletAudioSample.sys",
        "ComponentizedAudioSample.inf",
        "ComponentizedAudioSampleExtension.inf",
        "ComponentizedApoSample.inf",
        "sysvad.cat",
    ]

    vs_roots = _visual_studio_roots()
    toolset_candidates: list[dict[str, Path]] = []
    atl_paths: list[Path] = []
    spectre_paths: list[Path] = []
    for vs_root in vs_roots:
        toolsets = vs_root / "MSBuild" / "Microsoft" / "VC" / "v170" / "Platforms" / "x64" / "PlatformToolsets"
        toolset_candidates.append(
            {
                "kernel": toolsets / "WindowsKernelModeDriver10.0",
                "application": toolsets / "WindowsApplicationForDrivers10.0",
            }
        )
        msvc_root = vs_root / "VC" / "Tools" / "MSVC"
        if msvc_root.is_dir():
            for version_dir in msvc_root.iterdir():
                if version_dir.is_dir():
                    atl_paths.append(version_dir / "atlmfc" / "include" / "atlbase.h")
                    spectre_paths.append(version_dir / "lib" / "spectre" / "x64" / "vcruntime.lib")

    missing_package_files = [
        name for name in package_files if not (package_dir / name).is_file()
    ]
    available_toolset = next(
        (
            candidate
            for candidate in toolset_candidates
            if candidate["kernel"].is_dir() and candidate["application"].is_dir()
        ),
        None,
    )
    driver_toolset_available = available_toolset is not None
    atl_header = _first_existing(atl_paths)
    spectre_lib = _first_existing(spectre_paths)
    wil_header = source_root / "wil" / "include" / "wil" / "com.h"
    package_built = package_dir.is_dir() and not missing_package_files
    package_text = ""
    for name in (
        "ComponentizedAudioSample.inf",
        "ComponentizedAudioSampleExtension.inf",
        "ComponentizedApoSample.inf",
    ):
        inf = package_dir / name
        if inf.is_file():
            try:
                package_text += "\n" + inf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    sensorbridge_package = "SensorBridge" in package_text and "Root\\SensorBridge_VirtualMicrophone" in package_text
    root_hardware_id = "Root\\SensorBridge_VirtualMicrophone" if sensorbridge_package else "Root\\Sysvad_ComponentizedAudioSample"

    return {
        "visual_studio_roots": [str(path) for path in vs_roots],
        "driver_toolset_available": driver_toolset_available,
        "driver_toolset_paths": {
            key: str(path) for key, path in (available_toolset or {}).items()
        },
        "atl_available": atl_header is not None,
        "atl_header": atl_header,
        "spectre_libs_available": spectre_lib is not None,
        "spectre_lib": spectre_lib,
        "wil_available": wil_header.is_file(),
        "wil_header": str(wil_header),
        "package_dir": str(package_dir),
        "package_built": package_built,
        "missing_package_files": missing_package_files,
        "sensorbridge_package": sensorbridge_package,
        "root_hardware_id": root_hardware_id,
        "certificate": str(sysvad_dir / "x64" / "Debug" / "package.cer"),
        "certificate_exists": (sysvad_dir / "x64" / "Debug" / "package.cer").is_file(),
    }


def is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def test_signing_status() -> dict[str, Any]:
    bcdedit = shutil.which("bcdedit.exe")
    if not bcdedit:
        return {"checked": False, "enabled": False, "reason": "bcdedit.exe was not found."}
    try:
        result = subprocess.run(
            [bcdedit, "/enum", "{current}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"checked": False, "enabled": False, "reason": str(exc)}

    text = f"{result.stdout}\n{result.stderr}".lower()
    enabled = "testsigning" in text and (" yes" in text or "\tyes" in text or "true" in text)
    return {
        "checked": result.returncode == 0,
        "enabled": enabled,
        "exit_code": result.returncode,
        "requires_admin_to_change": True,
    }


def _run_powershell_json(script: Path, args: list[str], *, command: str) -> dict[str, Any]:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": "powershell_missing",
                "message": "powershell.exe was not found.",
            },
        }
    if not script.is_file():
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": "script_missing",
                "message": f"Script not found: {script}",
            },
        }
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": "script_failed_to_start",
                "message": str(exc),
            },
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "command": command,
            "exit_code": result.returncode,
            "error": {
                "code": "script_failed",
                "message": (result.stderr or result.stdout or "").strip(),
            },
        }
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "command": command,
            "exit_code": result.returncode,
            "error": {
                "code": "non_json_output",
                "message": "PowerShell script did not return JSON.",
            },
            "stdout": result.stdout,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": "unexpected_output_shape",
                "message": "PowerShell script returned non-object JSON.",
            },
            "payload": payload,
        }
    payload.setdefault("ok", True)
    payload["command"] = command
    payload["script"] = str(script)
    payload["changes_system"] = bool(payload.get("changes_system", False))
    return payload


def inspect_microphone_install_status(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    script = project_root / "drivers" / "audio" / "install-dev.ps1"
    payload = _run_powershell_json(script, ["-VerifyOnly"], command="microphone_install_status")
    payload.setdefault("installs_driver_or_microphone", False)
    payload.setdefault("changes_system", False)
    return payload


def inspect_microphone_test_signing_status(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    script = project_root / "drivers" / "audio" / "test-signing.ps1"
    payload = _run_powershell_json(script, ["-Status"], command="microphone_test_signing_status")
    payload.setdefault("changes_system", False)
    return payload


def inspect_microphone_install_plan(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    readiness = inspect_microphone_readiness(project_root)
    install_status = inspect_microphone_install_status(project_root)
    verification = install_status.get("verification") if isinstance(install_status.get("verification"), dict) else {}
    package = install_status.get("package") if isinstance(install_status.get("package"), dict) else {}
    install_blocks = install_status.get("install_blocks") if isinstance(install_status.get("install_blocks"), list) else []
    next_commands = install_status.get("next_commands") if isinstance(install_status.get("next_commands"), list) else []
    test_signing = install_status.get("test_signing") if isinstance(install_status.get("test_signing"), dict) else {}

    if verification.get("audio_endpoint_count", 0):
        stage = "installed"
        next_step = "verify"
        next_command = "dotnet run --project .\\tools\\MediaDeviceProbe\\MediaDeviceProbe.csproj"
        summary = "SensorBridge microphone endpoint is present."
    elif not package.get("complete") or not install_status.get("sensorbridge_package"):
        stage = "build_required"
        next_step = "build_package"
        next_command = "powershell -ExecutionPolicy Bypass -File .\\drivers\\audio\\build-dev.ps1 -ApplySensorBridgePatch -Build"
        summary = "Build the SensorBridge-patched SysVAD development package."
    elif not test_signing.get("enabled"):
        stage = "test_signing_required"
        next_step = "enable_test_signing_and_reboot"
        next_command = "powershell -ExecutionPolicy Bypass -File .\\drivers\\audio\\test-signing.ps1 -Enable"
        summary = "Enable Windows test signing from an administrator shell, then reboot."
    elif install_status.get("can_install_now"):
        stage = "ready_to_install"
        next_step = "install_driver"
        next_command = "powershell -ExecutionPolicy Bypass -File .\\drivers\\audio\\install-dev.ps1 -Install"
        summary = "Install the SensorBridge virtual microphone development driver from an administrator shell."
    else:
        stage = "blocked"
        next_step = "resolve_blocks"
        next_command = str(next_commands[0]) if next_commands else ""
        summary = "Resolve the listed microphone installation blocks."

    return {
        "ok": True,
        "command": "microphone_install_plan",
        "mode": "development-driver-install-plan",
        "stage": stage,
        "next_step": next_step,
        "next_command": next_command,
        "summary": summary,
        "changes_system": False,
        "installs_driver_or_microphone": False,
        "plan_only": True,
        "requires_admin_for_install": True,
        "requires_test_signing_for_development": True,
        "requires_reboot": stage == "test_signing_required",
        "current_blocks": install_blocks,
        "next_commands": next_commands,
        "readiness": readiness,
        "install_status": install_status,
        "verification": verification,
        "notes": [
            "This is a plan-only report. It does not enable test signing, install a driver, reboot, or create a microphone endpoint.",
            "Run the next command only when you are ready for the described Windows system change.",
        ],
    }


def inspect_microphone_readiness(root: Path | None = None) -> dict[str, Any]:
    project_root = root or Path(__file__).resolve().parents[1]
    source_dir = project_root / "third_party" / "src" / "Windows-driver-samples" / "audio" / "sysvad"
    project = None
    if source_dir.is_dir():
        candidates = sorted(source_dir.rglob("*.sln")) + sorted(source_dir.rglob("*.vcxproj"))
        if candidates:
            project = str(candidates[0])

    msbuild = find_msbuild()
    wdk = wdk_available()
    prerequisites = inspect_driver_build_prerequisites(project_root)
    source_exists = source_dir.is_dir()
    admin = is_user_admin()
    test_signing = test_signing_status()
    can_build = bool(
        source_exists
        and msbuild
        and wdk
        and project
        and prerequisites["driver_toolset_available"]
        and prerequisites["atl_available"]
        and prerequisites["spectre_libs_available"]
        and prerequisites["wil_available"]
    )
    can_install_dev = bool(can_build and admin and test_signing.get("enabled"))

    return {
        "ok": True,
        "command": "microphone_readiness",
        "mode": "sysvad-development-driver",
        "source_dir": str(source_dir),
        "source_exists": source_exists,
        "project": project,
        "msbuild": msbuild,
        "msbuild_available": msbuild is not None,
        "wdk_available": wdk,
        "build_prerequisites": prerequisites,
        "admin": admin,
        "test_signing": test_signing,
        "can_build_driver": can_build,
        "development_package_built": prerequisites["package_built"],
        "can_stage_development_package": bool(prerequisites["package_built"] and prerequisites["certificate_exists"]),
        "can_install_development_driver": can_install_dev,
        "installs_driver_or_microphone": False,
        "requires_admin_for_install": True,
        "requires_test_signing_for_development": True,
        "requires_driver_signing_for_release": True,
        "creates_windows_microphone_device_now": False,
        "next_steps": [
            "Fetch Windows-driver-samples with third_party\\fetch-third-party.ps1 -Component Windows-driver-samples.",
            "Install Visual Studio C++ build tools, DriverKit build tools, ATL, Spectre libraries, and the Windows Driver Kit if missing.",
            "Build the SensorBridge-named SysVAD package with drivers\\audio\\build-dev.ps1 -ApplySensorBridgePatch -Build.",
            "Enable Windows test signing with drivers\\audio\\test-signing.ps1 -Enable and reboot before installing the development driver package.",
            "Install the SensorBridge-patched and test-signed INF from an administrator shell.",
            "Verify enumeration with drivers\\audio\\install-dev.ps1 -VerifyOnly.",
        ],
        "notes": [
            "This readiness report does not enable test signing, install an INF, reboot, or create a microphone endpoint.",
            "Windows will not enumerate a SensorBridge microphone until a signed driver package is installed.",
        ],
    }
