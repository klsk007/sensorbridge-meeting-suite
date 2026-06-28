from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unified_meeting_app_targets_all_three_meeting_devices() -> None:
    source = ROOT / "meeting-suite" / "windows-app" / "SensorBridge.Meeting.App" / "Program.cs"
    text = source.read_text(encoding="utf-8")

    assert "Start-SensorBridgeMeeting.ps1" in text
    assert "Test-SensorBridgeMeeting.ps1" in text
    assert "SensorBridge Camera" in text
    assert "CABLE Output" in text
    assert "CABLE Input" in text
    assert "Camera" in text
    assert "Microphone" in text
    assert "Speaker" in text


def test_unified_launcher_starts_camera_microphone_and_speaker_components() -> None:
    launcher = ROOT / "meeting-suite" / "Start-SensorBridgeMeeting.ps1"
    text = launcher.read_text(encoding="utf-8")

    assert "sensorbridge-windows-clean" in text
    assert "sensorbridge-microphone-windows" in text
    assert "sensorbridge-speaker-windows" in text
    assert "sensorbridge.py" in text
    assert "bridge.py" in text
    assert "speaker_bridge.py" in text
    assert "webrtc-microphone" in text
    assert "webrtc-speaker" in text


def test_readme_exposes_single_app_build_and_run_path() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "SensorBridge Meeting Suite" in text
    assert "SensorBridge.Meeting.App.exe" in text
    assert "meeting-suite/windows-app" in text
    assert "Tencent Meeting" in text
