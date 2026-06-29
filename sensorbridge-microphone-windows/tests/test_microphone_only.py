from __future__ import annotations

import base64
import json
import re
import time
import zipfile
from pathlib import Path

import numpy as np

import bridge
from bridgeclient import HttpTransport, SensorBridgeClient, analyze_audio_frame
from bridgeclient.models import AudioFrame
from bridgeclient.vbcable import check_vbcable_loopback, inspect_vbcable
from bridgeclient.webrtc_microphone import (
    WebRTCMicrophoneResult,
    _InputCaptureBuffer,
    _PlaybackBuffer,
    _AudioReceiverState,
    _apply_low_cut_filter,
    _apply_noise_gate,
    _apply_output_gain,
    _apply_push_to_talk_gate,
    _audio_frame_to_s16le,
    _capture_level_status,
    _close_diagnostic_capture_writers,
    _diagnostic_capture_paths,
    _diagnostic_capture_status,
    _frames_to_ms,
    _layered_quality_attribution,
    _ms_to_frames,
    _quality_status,
    _record_loopback_samples,
    _record_output_samples,
    _write_diagnostic_capture,
    _write_capture_files,
)


class FakeTransport:
    base_url = "http://fake-ipad:27180"

    def __init__(self) -> None:
        self.sequence = 0
        self.calls: list[tuple[str, str]] = []

    def request_json(self, method: str, path: str, body=None, *, timeout=None):
        self.calls.append((method, path))
        if path == "/api/v1/audio/start":
            return {"ok": True, "running": True}
        if path == "/api/v1/audio/stop":
            return {"ok": True, "running": False}
        if path == "/api/v1/sample/audio-frame":
            self.sequence += 1
            pcm = (1000).to_bytes(2, "little", signed=True) * 160
            return {
                "ok": True,
                "audio_frame": {
                    "sequence": self.sequence,
                    "timestamp_ns": time.time_ns(),
                    "sample_rate_hz": 16000,
                    "channel_count": 1,
                    "sample_format": "S16LE",
                    "data_base64": base64.b64encode(pcm).decode("ascii"),
                    "source": "ipad-microphone",
                },
            }
        return {"ok": True}


def test_command_aliases_are_microphone_only() -> None:
    commands = set(bridge.COMMAND_ALIASES.values())
    assert "microphone_product_status" in commands
    assert "vbcable_product_status" in commands
    assert "pump_vbcable" in commands
    assert "vbcable_loopback_check" in commands
    assert "start_audio" in commands
    assert not any("camera" in command for command in commands)
    assert not any("speaker" in command for command in commands)
    assert not any("acceleration" in command for command in commands)
    assert "webrtc_microphone" in commands
    assert "webrtc_loopback_check" in commands
    assert "vbcable_output_capture" in commands
    assert "vbcable_output_record" in commands
    assert "diagnostic_summary" in commands
    assert "connection_check" in commands
    assert "gain_tune" in commands
    assert "desktop_shortcut_status" in commands
    assert "diagnostic_bundle" in commands
    assert "short_term_status" in commands


def test_windows_app_localized_text_has_no_duplicate_keys() -> None:
    source = Path("windows-app/SensorBridge.Microphone.App/Program.cs").read_text(encoding="utf-8")
    for table_name in ("En", "Zh"):
        match = re.search(
            r"private static readonly Dictionary<string, string> "
            + table_name
            + r"\s*=\s*new Dictionary<string, string>\s*\{(.*?)\n\s*\};",
            source,
            re.S,
        )
        assert match, f"missing localized text table {table_name}"
        keys = re.findall(r'\{\s*"([^"]+)"\s*,', match.group(1))
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        assert duplicates == []


def test_build_parser_accepts_playback_buffer_options() -> None:
    args = bridge.build_parser().parse_args(
        ["--playback-prebuffer-ms", "2500", "--playback-max-buffer-ms", "6000", "webrtc-microphone"]
    )
    assert args.playback_prebuffer_ms == 2500
    assert args.playback_max_buffer_ms == 6000


def test_build_parser_accepts_gain_tune_options() -> None:
    args = bridge.build_parser().parse_args(
        ["--gain-values", "0.75,1.0,1.25", "--tune-dir", "captures/gain_tune", "gain-tune"]
    )
    assert bridge.normalize_command(args.command) == "gain_tune"
    assert args.gain_values == "0.75,1.0,1.25"
    assert args.tune_dir == "captures/gain_tune"


def test_parse_gain_values_defaults_and_rejects_invalid_values() -> None:
    assert bridge._parse_gain_values("") == [0.75, 1.0, 1.25]
    assert bridge._parse_gain_values("0.5; 1 ;2") == [0.5, 1.0, 2.0]

    try:
        bridge._parse_gain_values("0,1")
    except bridge.BridgeClientError as exc:
        assert exc.code == "invalid_gain_values"
    else:
        raise AssertionError("expected invalid gain values to fail")


def test_diagnostic_summary_extracts_webrtc_smoke_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "smoke.json"
    report_path.write_text(json.dumps({
        "ok": True,
        "readiness": {
            "state": "route_ready_quality_not_ready",
            "message": "route ok",
            "nextAction": "fix_ipad_source",
            "nextActionMessage": "fix source",
            "audioRouteReady": True,
            "loopbackQualityReady": False,
            "windowsQualityReady": False,
            "fullQualityReady": False,
        },
        "windows_receiver": {
            "receiverRmsDbfs": -63.69,
            "outputRmsDbfs": -63.9,
            "receiverPeakDbfs": -40.65,
            "outputPeakDbfs": -40.77,
            "playbackUnderflows": 0,
            "playbackDroppedFrames": 0,
            "audioPacketsReceived": 376,
        },
        "windows_loopback_capture": {"rmsDbfs": -65.62, "peakDbfs": -42.96},
        "quality": {
            "primaryIssue": "source_too_quiet",
            "safeMicGainAction": "raise_modestly",
            "safeMicGainCeiling": 3.0,
            "safeMicGainCanReachTarget": False,
            "recommendedSourceLiftDb": 0.0,
        },
        "diagnostic_captures": {
            "qualityAttribution": {"stage": "ipad_source_too_quiet"},
            "layers": {
                "receiver_raw": {"path": "raw.wav"},
                "processed": {"path": "processed.wav"},
                "cable_output": {"path": "cable.wav"},
            },
        },
        "ipad_upstream": {
            "microphoneUpstreamState": "sending_webrtc_opus",
            "microphoneUpstreamPacketsSent": 385,
            "microphoneUpstreamStatsFresh": True,
        },
        "ipad_webrtc_status": {
            "microphoneInputRmsDbfs": -61.67,
            "microphoneProcessedRmsDbfs": -13.38,
            "microphoneVoiceProcessingEnabled": True,
            "microphoneEchoCancellationEnabled": True,
            "microphoneAutomaticGainControlEnabled": True,
            "microphoneNoiseSuppressionEnabled": True,
            "microphoneAudioSessionMode": "AVAudioSessionModeVoiceChat",
            "realIpadMicrophone": True,
        },
    }), encoding="utf-8")

    summary = bridge.summarize_diagnostic_json(str(report_path))

    assert summary["command"] == "diagnostic_summary"
    assert summary["readiness"]["nextAction"] == "fix_ipad_source"
    assert summary["levels"]["windowsRawRmsDbfs"] == -63.69
    assert summary["levels"]["ipadProcessedRmsDbfs"] == -13.38
    assert summary["quality"]["qualityAttributionStage"] == "ipad_source_too_quiet"
    assert summary["continuity"]["upstreamPacketsSent"] == 385
    assert summary["ipadProcessing"]["echoCancellationEnabled"] is True
    assert summary["files"]["cableOutput"] == "cable.wav"
    assert "SensorBridge Microphone diagnostic summary" in summary["textReport"]
    assert "Windows raw RMS: -63.69 dBFS" in summary["textReport"]
    assert "voiceProcessing/AEC/AGC/NS: True / True / True / True" in summary["textReport"]


def test_diagnostic_summary_accepts_utf16_json(tmp_path: Path) -> None:
    report_path = tmp_path / "smoke_utf16.json"
    report_path.write_text(json.dumps({"ok": False, "readiness": {"nextAction": "check_transport"}}), encoding="utf-16")

    summary = bridge.summarize_diagnostic_json(str(report_path))

    assert summary["ok"] is False
    assert summary["readiness"]["nextAction"] == "check_transport"


def test_diagnostic_summary_derives_next_action_for_old_reports(tmp_path: Path) -> None:
    report_path = tmp_path / "old_smoke.json"
    report_path.write_text(json.dumps({
        "ok": True,
        "readiness": {"audioRouteReady": True, "loopbackQualityReady": False},
        "quality": {"primaryIssue": "level_low", "safeMicGainAction": "raise_modestly"},
    }), encoding="utf-8")

    summary = bridge.summarize_diagnostic_json(str(report_path))

    assert summary["readiness"]["nextAction"] == "fix_meeting_loopback_level"


def test_diagnostic_summary_does_not_recommend_gain_when_full_quality_ready(tmp_path: Path) -> None:
    report_path = tmp_path / "ready_smoke.json"
    report_path.write_text(json.dumps({
        "ok": True,
        "readiness": {
            "state": "full_quality_ready",
            "nextAction": "raise_windows_gain_modestly",
            "audioRouteReady": True,
            "loopbackQualityReady": True,
            "windowsQualityReady": True,
            "fullQualityReady": True,
        },
        "quality": {"primaryIssue": "level_low", "safeMicGainAction": "raise_modestly"},
    }), encoding="utf-8")

    summary = bridge.summarize_diagnostic_json(str(report_path))

    assert summary["readiness"]["nextAction"] == "ready_or_monitor"


def test_write_latest_webrtc_diagnostics_persists_status_summary_and_text(tmp_path: Path) -> None:
    payload = {
        "ok": True,
        "readiness": {
            "state": "route_ready_quality_not_ready",
            "audioRouteReady": True,
            "loopbackQualityReady": False,
            "windowsQualityReady": False,
            "fullQualityReady": False,
        },
        "windows_receiver": {
            "receiverRmsDbfs": -59.42,
            "outputRmsDbfs": -53.46,
            "audioPacketsReceived": 576,
        },
        "windows_loopback_capture": {"activeRmsDbfs": -52.64},
        "quality": {"primaryIssue": "level_low", "safeMicGainAction": "raise_modestly"},
        "ipad_webrtc_status": {
            "microphoneVoiceProcessingEnabled": True,
            "microphoneEchoCancellationEnabled": True,
            "microphoneAutomaticGainControlEnabled": True,
            "microphoneNoiseSuppressionEnabled": True,
        },
    }

    paths = bridge.write_latest_webrtc_diagnostics(payload, root=tmp_path)

    status = json.loads(Path(paths["statusPath"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(paths["summaryPath"]).read_text(encoding="utf-8"))
    text = Path(paths["textPath"]).read_text(encoding="utf-8")
    assert status["ok"] is True
    assert summary["levels"]["windowsRawRmsDbfs"] == -59.42
    assert summary["readiness"]["nextAction"] == "fix_meeting_loopback_level"
    assert "Windows raw RMS: -59.42 dBFS" in text


def test_connection_check_prefers_ready_relay(monkeypatch) -> None:
    def fake_probe(base_url: str, path: str, *, timeout: float):
        if "relay" in base_url:
            return {"ok": True, "path": path, "payload": {"ok": True}}
        return {"ok": False, "path": path, "error": "offline"}

    monkeypatch.setattr(bridge, "_probe_json_endpoint", fake_probe)

    payload = bridge.check_backend_connections("direct.local:27180", "relay.local:27181", timeout=1)

    assert payload["ok"] is True
    assert payload["preferredBaseUrl"] == "http://relay.local:27181"
    assert payload["backendSelectionReason"] == "relay_ready_direct_unavailable"
    assert payload["recommendedNextAction"] == "run_webrtc_smoke"


def test_connection_check_reports_restart_when_all_targets_fail(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_probe_json_endpoint", lambda base_url, path, *, timeout: {
        "ok": False,
        "path": path,
        "error": "connection failed",
    })

    payload = bridge.check_backend_connections("direct.local:27180", "relay.local:27181", timeout=1)

    assert payload["ok"] is False
    assert payload["preferredBaseUrl"] is None
    assert payload["backendSelectionReason"] == "no_backend_ready"
    assert payload["recommendedNextAction"] == "restart_ipad_app_or_mac_relay"


def test_backend_selection_uses_direct_when_relay_is_unavailable() -> None:
    preferred, reason = bridge._select_preferred_backend([
        {"name": "direct", "base_url": "http://direct.local:27180", "ready": True},
        {"name": "relay", "base_url": "http://relay.local:27181", "ready": False},
    ])

    assert preferred["base_url"] == "http://direct.local:27180"
    assert reason == "direct_ready_relay_unavailable"


def test_backend_selection_prefers_relay_when_both_targets_are_ready() -> None:
    preferred, reason = bridge._select_preferred_backend([
        {"name": "direct", "base_url": "http://direct.local:27180", "ready": True},
        {"name": "relay", "base_url": "http://relay.local:27181", "ready": True},
    ])

    assert preferred["base_url"] == "http://relay.local:27181"
    assert reason == "relay_ready_preferred_for_stability"


def test_backend_selection_uses_relay_when_direct_is_unavailable() -> None:
    preferred, reason = bridge._select_preferred_backend([
        {"name": "direct", "base_url": "http://direct.local:27180", "ready": False},
        {"name": "relay", "base_url": "http://relay.local:27181", "ready": True},
    ])

    assert preferred["base_url"] == "http://relay.local:27181"
    assert reason == "relay_ready_direct_unavailable"


def test_desktop_shortcut_status_reports_ready_shortcut(monkeypatch) -> None:
    root = Path(bridge.__file__).resolve().parent
    exe = root / "windows-app" / "SensorBridge.Microphone.App" / "bin" / "Release" / "SensorBridge.Microphone.App.exe"
    arguments = (
        f'--project-root "{root}" --base-url "http://192.168.0.24:27180" '
        f'--relay-url "http://192.168.0.23:27181" --output-device "CABLE Input"'
    )

    monkeypatch.setattr(bridge, "_read_windows_shortcut", lambda path: {
        "exists": True,
        "target": str(exe),
        "arguments": arguments,
        "workingDirectory": str(root),
        "icon": str(exe) + ",0",
        "errors": [],
    })

    payload = bridge.inspect_desktop_shortcut(
        "SensorBridge Microphone.lnk",
        "http://192.168.0.24:27180",
        "http://192.168.0.23:27181",
        "CABLE Input",
    )

    assert payload["ok"] is True
    assert payload["relayUrlArgumentOk"] is True
    assert payload["recommendedNextAction"] == "ready_or_monitor"


def test_desktop_shortcut_status_recommends_reinstall_without_relay(monkeypatch) -> None:
    root = Path(bridge.__file__).resolve().parent
    exe = root / "windows-app" / "SensorBridge.Microphone.App" / "bin" / "Release" / "SensorBridge.Microphone.App.exe"
    arguments = f'--project-root "{root}" --base-url "http://192.168.0.24:27180" --output-device "CABLE Input"'

    monkeypatch.setattr(bridge, "_read_windows_shortcut", lambda path: {
        "exists": True,
        "target": str(exe),
        "arguments": arguments,
        "workingDirectory": str(root),
        "icon": str(exe) + ",0",
        "errors": [],
    })

    payload = bridge.inspect_desktop_shortcut(
        "SensorBridge Microphone.lnk",
        "http://192.168.0.24:27180",
        "http://192.168.0.23:27181",
        "CABLE Input",
    )

    assert payload["ok"] is False
    assert payload["relayUrlArgumentOk"] is False
    assert payload["recommendedNextAction"] == "reinstall_shortcut"


def test_diagnostic_bundle_includes_latest_files_and_manifest(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    captures = root / "captures"
    captures.mkdir()
    (captures / "latest_webrtc_status.json").write_text('{"ok": true}', encoding="utf-8")
    (captures / "latest_webrtc_summary.txt").write_text("summary", encoding="utf-8")
    (captures / "sample.wav").write_bytes(b"RIFF")
    bundle_dir = captures / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "old.zip").write_bytes(b"old")
    monkeypatch.setattr(bridge, "__file__", str(root / "bridge.py"))
    monkeypatch.setattr(bridge, "inspect_desktop_shortcut", lambda *args: {"ok": True, "command": "desktop_shortcut_status"})
    monkeypatch.setattr(bridge, "inspect_vbcable", lambda output_device: {
        "ok": True,
        "command": "vbcable_status",
        "output_device_found": True,
        "meeting_input_device_found": True,
    })

    output = root / "bundle.zip"
    payload = bridge.create_diagnostic_bundle(str(output), max_files=10)

    assert payload["ok"] is True
    assert payload["filesIncluded"] == 3
    assert payload["environment"]["desktop_shortcut_status"]["ok"] is True
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "environment/desktop_shortcut_status.json" in names
        assert "environment/vbcable_status.json" in names
        assert "captures/latest_webrtc_status.json" in names
        assert "captures/latest_webrtc_summary.txt" in names
        assert "captures/sample.wav" in names
        assert "captures/bundles/old.zip" not in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["fileCount"] == 3
    assert manifest["environment"]["desktopShortcutOk"] is True
    assert manifest["environment"]["vbcableOutputFound"] is True


def test_short_term_status_summarizes_local_and_backend_checks(tmp_path: Path, monkeypatch) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "latest_webrtc_summary.json").write_text(json.dumps({
        "readiness": {
            "fullQualityReady": False,
            "nextAction": "fix_meeting_loopback_level",
        }
    }), encoding="utf-8")
    monkeypatch.setattr(bridge, "__file__", str(tmp_path / "bridge.py"))
    monkeypatch.setattr(bridge, "inspect_desktop_shortcut", lambda *args: {"ok": True})
    monkeypatch.setattr(bridge, "inspect_vbcable", lambda output_device: {
        "output_device_found": True,
        "meeting_input_device_found": True,
    })
    monkeypatch.setattr(bridge, "check_backend_connections", lambda *args, **kwargs: {"ok": True})

    payload = bridge.inspect_short_term_status(
        "http://direct.local:27180",
        "http://relay.local:27181",
        "CABLE Input",
        "SensorBridge Microphone.lnk",
    )

    assert payload["ok"] is True
    assert payload["checks"]["desktopShortcutReady"] is True
    assert payload["checks"]["vbcableReady"] is True
    assert payload["checks"]["backendReady"] is True
    assert payload["checks"]["latestWebRtcSummaryPresent"] is True
    assert payload["recommendedNextAction"] == "fix_meeting_loopback_level"


def test_short_term_status_prioritizes_missing_vbcable(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "inspect_desktop_shortcut", lambda *args: {"ok": True})
    monkeypatch.setattr(bridge, "inspect_vbcable", lambda output_device: {
        "output_device_found": False,
        "meeting_input_device_found": False,
    })
    monkeypatch.setattr(bridge, "check_backend_connections", lambda *args, **kwargs: {"ok": True})

    payload = bridge.inspect_short_term_status(
        "http://direct.local:27180",
        "http://relay.local:27181",
        "CABLE Input",
        "SensorBridge Microphone.lnk",
    )

    assert payload["ok"] is False
    assert payload["recommendedNextAction"] == "install_or_fix_vbcable"


def test_gain_tune_selects_best_meeting_quality_gain(tmp_path: Path, monkeypatch) -> None:
    class FakeWebRtcResult:
        def __init__(self, payload):
            self.payload = payload

        def to_json(self):
            return self.payload

    def fake_receiver(**kwargs):
        gain = kwargs["output_gain"]
        if gain == 0.75:
            payload = _fake_gain_tune_payload(
                state="route_ready_quality_not_ready",
                cable_active=-60.0,
                peak=-28.0,
                stage="route_level_too_low",
                action="raise_modestly",
            )
        elif gain == 1.0:
            payload = _fake_gain_tune_payload(
                state="full_quality_ready",
                cable_active=-52.5,
                peak=-24.0,
                stage="audio_level_route_ok",
                action="raise_modestly",
            )
        else:
            payload = _fake_gain_tune_payload(
                state="full_quality_ready",
                cable_active=-48.0,
                peak=-9.0,
                stage="audio_level_route_ok",
                action="lower_gain",
            )
        return FakeWebRtcResult(payload)

    monkeypatch.setattr(bridge, "run_webrtc_microphone_receiver", fake_receiver)
    args = bridge.build_parser().parse_args([
        "--gain-values",
        "0.75,1.0,1.25",
        "--duration-seconds",
        "1",
        "--tune-dir",
        str(tmp_path),
        "gain-tune",
    ])

    payload = bridge.run_gain_tune(args)

    assert payload["ok"] is True
    assert payload["recommendedGain"] == 1.0
    assert payload["best"]["readiness"] == "full_quality_ready"
    assert len(payload["runs"]) == 3
    assert all(Path(run["jsonPath"]).exists() for run in payload["runs"])


def _fake_gain_tune_payload(*, state: str, cable_active: float, peak: float, stage: str, action: str):
    return {
        "ok": True,
        "readiness": {
            "state": state,
            "audioRouteReady": True,
            "nextAction": "ready_or_monitor" if state == "full_quality_ready" else "fix_meeting_loopback_level",
        },
        "windows_receiver": {
            "receiverRmsDbfs": cable_active - 1,
            "outputRmsDbfs": cable_active,
            "outputPeakDbfs": peak,
            "playbackUnderflows": 0,
            "playbackDroppedFrames": 0,
            "audioPacketsReceived": 100,
        },
        "windows_loopback_capture": {"activeRmsDbfs": cable_active},
        "quality": {"primaryIssue": "none", "safeMicGainAction": action},
        "diagnostic_captures": {"qualityAttribution": {"stage": stage}},
    }


def test_analyze_audio_frame_reports_volume() -> None:
    pcm = (2000).to_bytes(2, "little", signed=True) * 4
    frame = AudioFrame(
        audio_sample_sequence=1,
        sample_rate_hz=48000,
        channel_count=1,
        sample_format="S16LE",
        data_base64=base64.b64encode(pcm).decode("ascii"),
    )
    analysis = analyze_audio_frame(frame)
    assert analysis.valid_pcm is True
    assert analysis.peak_abs == 2000
    assert analysis.rms == 2000


def test_product_status_with_fake_ipad_audio(tmp_path: Path, monkeypatch) -> None:
    client = SensorBridgeClient(FakeTransport())
    args = bridge.build_parser().parse_args(
        [
            "--base-url",
            "http://fake-ipad:27180",
            "--frames",
            "2",
            "--pcm-dir",
            str(tmp_path),
            "microphone-product-status",
        ]
    )
    monkeypatch.setattr(bridge, "inspect_microphone_route_status", lambda root: {
        "ok": True,
        "device_enumerated": False,
        "audio_endpoint_present": False,
        "audio_endpoint_count": 0,
        "normal_app_visible": False,
        "next_step": "install_driver",
    })
    monkeypatch.setattr(bridge, "inspect_windows_endpoint_capture", lambda duration_s=0.75: {
        "ok": False,
        "ordinary_apps_receive_audio_from_endpoint": False,
        "ipad_pcm_injected_into_virtual_endpoint": False,
        "endpoint_audio_looks_like_sysvad_test_tone": False,
    })
    payload = bridge.microphone_product_status(client, args)
    assert payload["ok"] is False
    assert payload["frames_received"] == 2
    assert payload["real_ipad_microphone_data"] is True
    assert payload["normal_app_visible"] is False
    assert payload["windows_apps_can_select_sensorbridge_microphone"] is False
    assert (tmp_path / "latest.pcm").is_file()
    assert json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))["source"] == "ipad-microphone"


def test_product_status_requires_ipad_pcm_in_virtual_endpoint(tmp_path: Path, monkeypatch) -> None:
    client = SensorBridgeClient(FakeTransport())
    args = bridge.build_parser().parse_args(
        [
            "--base-url",
            "http://fake-ipad:27180",
            "--frames",
            "1",
            "--pcm-dir",
            str(tmp_path),
            "microphone-product-status",
        ]
    )
    monkeypatch.setattr(bridge, "inspect_microphone_route_status", lambda root: {
        "ok": True,
        "device_enumerated": True,
        "audio_endpoint_present": True,
        "audio_endpoint_count": 1,
        "normal_app_visible": True,
    })
    monkeypatch.setattr(bridge, "inspect_windows_endpoint_capture", lambda duration_s=0.75: {
        "ok": True,
        "ordinary_apps_receive_audio_from_endpoint": True,
        "ipad_pcm_injected_into_virtual_endpoint": False,
        "endpoint_audio_looks_like_sysvad_test_tone": True,
    })
    payload = bridge.microphone_product_status(client, args)
    assert payload["ok"] is False
    assert payload["windows_apps_can_select_sensorbridge_microphone"] is True
    assert payload["ordinary_apps_receive_audio_from_endpoint"] is True
    assert payload["ipad_pcm_injected_into_virtual_endpoint"] is False


def test_vbcable_status_detects_cable_devices(monkeypatch) -> None:
    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return [
                {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
                {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000},
            ]

    monkeypatch.setattr("bridgeclient.vbcable._load_sounddevice", lambda: {"ok": True, "sounddevice": FakeSoundDevice})
    payload = inspect_vbcable()
    assert payload["ok"] is True
    assert payload["output_device_found"] is True
    assert payload["meeting_input_device_found"] is True
    assert payload["meeting_input_device"] == "CABLE Output"


def test_vbcable_loopback_requires_cable_pair(monkeypatch) -> None:
    client = SensorBridgeClient(FakeTransport())

    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return []

    monkeypatch.setattr("bridgeclient.vbcable._load_sounddevice", lambda: {"ok": True, "numpy": None, "sounddevice": FakeSoundDevice})
    payload = check_vbcable_loopback(client, frame_count=1).to_json()
    assert payload["ok"] is False
    assert payload["output_device_found"] is False
    assert payload["meeting_input_device_found"] is False
    assert payload["ordinary_apps_can_record_cable_output"] is False


def test_vbcable_product_status_requires_cable_output(tmp_path: Path, monkeypatch) -> None:
    client = SensorBridgeClient(FakeTransport())
    args = bridge.build_parser().parse_args(
        [
            "--base-url",
            "http://fake-ipad:27180",
            "--frames",
            "1",
            "--output-device",
            "CABLE Input",
            "vbcable-product-status",
        ]
    )
    monkeypatch.setattr(bridge, "inspect_vbcable", lambda output_device="CABLE Input": {
        "ok": False,
        "output_device_found": False,
        "meeting_input_device": "CABLE Output",
        "meeting_input_device_found": False,
    })
    payload = bridge.vbcable_product_status(client, args)
    assert payload["ok"] is False
    assert payload["real_ipad_microphone_data"] is True
    assert payload["vbcable_output_found"] is False
    assert payload["ready_for_tencent_meeting"] is False


def test_http_transport_normalizes_base_url() -> None:
    transport = HttpTransport("fake-ipad.local:27180")
    assert transport.base_url == "http://fake-ipad.local:27180"


def test_webrtc_microphone_result_separates_windows_and_ipad_evidence() -> None:
    payload = WebRTCMicrophoneResult(
        ok=True,
        audio_packets_received=13,
        audio_bytes_received=952,
        audio_frames_written=9600,
        audio_buffer_ms=20.0,
        receiver_state="receiving_webrtc_opus",
        meeting_input_device_found=True,
        virtual_microphone_ready=True,
        normal_app_microphone_visible=True,
        loopback_enabled=True,
        loopback_frame_count=960,
        loopback_peak_abs=1200,
        loopback_rms=300.0,
        loopback_active_rms=300.0,
        loopback_active_frame_count=960,
        loopback_nonzero_samples=900,
        ordinary_apps_receive_audio_from_endpoint=True,
        ipad_microphone_upstream_state="sending_webrtc_opus",
        ipad_microphone_upstream_packets_sent=49,
        ipad_microphone_upstream_bytes_sent=3486,
        ipad_microphone_upstream_stats_fresh=True,
        extra={
            "output_peak_abs": 2400,
            "output_rms": 600.0,
            "playbackPrebufferMs": 2000.0,
            "playbackMaxBufferMs": 5000.0,
            "quality": {
                "windowsShortTermReady": True,
                "fullShortTermReady": False,
                "levelState": "ok",
                "continuityState": "ok",
                "echoCancellationState": "unverified",
                "primaryIssue": "aec_unverified",
                "primaryRecommendation": "use_headphones_or_enable_ipad_aec",
            },
        },
    ).to_json()
    assert payload["transport"] == "webrtc_opus_microphone_upstream"
    assert payload["readiness"]["state"] == "windows_quality_ready"
    assert "Windows loopback quality are ready" in payload["readiness"]["message"]
    assert payload["readiness"]["okMeans"] == "transport_or_route_ready_not_quality"
    assert payload["readiness"]["transportOk"] is True
    assert payload["readiness"]["audioRouteReady"] is True
    assert payload["readiness"]["loopbackQualityReady"] is True
    assert payload["readiness"]["windowsQualityReady"] is True
    assert payload["readiness"]["fullQualityReady"] is False
    assert payload["windows_receiver"]["audioPacketsReceived"] == 13
    assert payload["windows_receiver"]["audioBufferMs"] == 20.0
    assert payload["windows_receiver"]["virtualMicrophoneReady"] is True
    assert payload["windows_receiver"]["outputPeakAbs"] == 2400
    assert payload["windows_receiver"]["outputRms"] == 600.0
    assert payload["windows_receiver"]["outputPeakDbfs"] == -22.7
    assert payload["windows_receiver"]["outputRmsDbfs"] == -34.75
    assert payload["windows_receiver"]["playbackPrebufferMs"] == 2000.0
    assert payload["windows_receiver"]["playbackMaxBufferMs"] == 5000.0
    assert payload["windows_loopback_capture"]["ordinaryAppsReceiveAudioFromEndpoint"] is True
    assert payload["windows_loopback_capture"]["peakAbs"] == 1200
    assert payload["windows_loopback_capture"]["peakDbfs"] == -28.73
    assert payload["windows_loopback_capture"]["rmsDbfs"] == -40.77
    assert payload["windows_loopback_capture"]["activeRmsDbfs"] == -40.77
    assert payload["windows_loopback_capture"]["levelState"] == "ok"
    assert payload["windows_loopback_capture"]["primaryIssue"] == "none"
    assert payload["windows_loopback_capture"]["recommendedSourceLiftDb"] == 0.0
    assert payload["tencent_meeting"]["state"] == "verified_audio"
    assert payload["tencent_meeting"]["readyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["audioRouteReadyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["windowsQualityReadyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["fullQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["loopbackQualityReadyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["loopbackLevelState"] == "ok"
    assert payload["tencent_meeting"]["loopbackPrimaryIssue"] == "none"
    assert payload["tencent_meeting"]["qualityLevelState"] == "ok"
    assert payload["tencent_meeting"]["qualityEchoCancellationState"] == "unverified"
    assert payload["tencent_meeting"]["qualityPrimaryIssue"] == "aec_unverified"
    assert payload["tencent_meeting"]["qualityPrimaryRecommendation"] == "use_headphones_or_enable_ipad_aec"
    assert payload["ipad_upstream"]["microphoneUpstreamPacketsSent"] == 49
    assert payload["ipad_upstream"]["microphoneUpstreamStatsFresh"] is True


def test_diagnostic_capture_paths_split_webrtc_layers(tmp_path: Path) -> None:
    base = tmp_path / "diag.wav"
    paths = _diagnostic_capture_paths(str(base))
    assert paths["receiver_raw"].endswith("diag_receiver_raw.wav")
    assert paths["processed"].endswith("diag_processed.wav")
    assert paths["cable_output"].endswith("diag_cable_output.wav")


def test_diagnostic_capture_writes_receiver_and_processed_wavs(tmp_path: Path) -> None:
    state = _AudioReceiverState(capture_path=str(tmp_path / "diag.wav"))
    warnings: list[str] = []
    samples = np.array([[100, -100], [200, -200], [300, -300]], dtype=np.int16)

    _write_diagnostic_capture(np, state, "receiver_raw", samples)
    _write_diagnostic_capture(np, state, "processed", samples)
    _close_diagnostic_capture_writers(state, warnings)

    status = _diagnostic_capture_status(state)
    raw = status["layers"]["receiver_raw"]
    processed = status["layers"]["processed"]
    assert warnings == []
    assert raw["exists"] is True
    assert raw["frames"] == 3
    assert processed["exists"] is True
    assert processed["frames"] == 3


def test_layered_quality_attribution_flags_quiet_ipad_source() -> None:
    state = _AudioReceiverState(loopback_capture=True)
    state.receiver_peak_abs = 300
    state.receiver_rms = 12.0
    state.output_peak_abs = 450
    state.output_rms = 18.0
    state.loopback_peak_abs = 350
    state.loopback_rms = 14.0

    payload = _layered_quality_attribution(state)

    assert payload["stage"] == "ipad_source_too_quiet"
    assert payload["receiverRaw"]["levelState"] == "low"
    assert payload["processedMinusRawRmsDb"] == 3.53


def test_layered_quality_attribution_flags_cable_loopback_loss() -> None:
    state = _AudioReceiverState(loopback_capture=True)
    state.receiver_peak_abs = 3000
    state.receiver_rms = 500.0
    state.output_peak_abs = 3000
    state.output_rms = 500.0
    state.loopback_peak_abs = 900
    state.loopback_rms = 100.0

    payload = _layered_quality_attribution(state)

    assert payload["stage"] == "cable_loopback_loss"
    assert payload["processed"]["levelState"] == "ok"
    assert payload["cableOutput"]["levelState"] == "ok"
    assert payload["cableMinusProcessedRmsDb"] == -13.98


def test_layered_quality_attribution_uses_active_loopback_rms_for_startup_silence() -> None:
    state = _AudioReceiverState(loopback_capture=True)
    state.receiver_peak_abs = 3000
    state.receiver_rms = 500.0
    state.output_peak_abs = 3000
    state.output_rms = 500.0
    state.loopback_peak_abs = 3000
    state.loopback_rms = 100.0
    state.loopback_active_rms = 500.0
    state.loopback_active_frame_count = 48000

    payload = _layered_quality_attribution(state)

    assert payload["stage"] == "audio_level_route_ok"
    assert payload["cableMinusProcessedRmsDb"] == 0.0
    assert payload["cableFullCaptureRmsDbfs"] == -50.31
    assert payload["cableActiveRmsDbfs"] == -36.33


def test_record_loopback_samples_tracks_active_rms_separately() -> None:
    state = _AudioReceiverState(loopback_capture=True)
    silence = np.zeros((480, 2), dtype=np.int16)
    voiced = np.full((480, 2), 500, dtype=np.int16)

    _record_loopback_samples(np, state, silence)
    _record_loopback_samples(np, state, voiced)

    assert state.loopback_frame_count == 960
    assert state.loopback_active_frame_count == 480
    assert state.loopback_rms == 353.553
    assert state.loopback_active_rms == 500.0


def test_webrtc_microphone_result_uses_loopback_level_for_meeting_quality() -> None:
    payload = WebRTCMicrophoneResult(
        ok=True,
        meeting_input_device_found=True,
        virtual_microphone_ready=True,
        normal_app_microphone_visible=True,
        loopback_enabled=True,
        loopback_frame_count=960,
        loopback_peak_abs=300,
        loopback_rms=17.994,
        loopback_nonzero_samples=900,
        ordinary_apps_receive_audio_from_endpoint=True,
        extra={
            "quality": {
                "windowsShortTermReady": True,
                "fullShortTermReady": True,
                "levelState": "ok",
                "continuityState": "ok",
                "echoCancellationState": "verified",
                "primaryIssue": "none",
                "primaryRecommendation": "none",
            },
        },
    ).to_json()

    assert payload["tencent_meeting"]["state"] == "verified_audio"
    assert payload["tencent_meeting"]["audioRouteReadyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["loopbackQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["windowsQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["fullQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["loopbackLevelState"] == "low"
    assert payload["tencent_meeting"]["loopbackPrimaryIssue"] == "source_too_quiet"
    assert payload["tencent_meeting"]["loopbackRecommendedSourceLiftDb"] == 24.44
    assert "ordinary-app loopback capture is too quiet" in payload["tencent_meeting"]["message"]
    assert payload["readiness"]["state"] == "route_ready_quality_not_ready"
    assert payload["readiness"]["message"] == "Audio route is verified, but meeting-quality audio is not ready."
    assert payload["readiness"]["transportOk"] is True
    assert payload["readiness"]["audioRouteReady"] is True
    assert payload["readiness"]["loopbackQualityReady"] is False
    assert payload["readiness"]["windowsQualityReady"] is False
    assert payload["readiness"]["nextAction"] == "fix_meeting_loopback_level"


def test_webrtc_microphone_result_distinguishes_route_ready_from_quality_ready() -> None:
    payload = WebRTCMicrophoneResult(
        ok=True,
        meeting_input_device_found=True,
        virtual_microphone_ready=True,
        normal_app_microphone_visible=True,
        loopback_enabled=True,
        loopback_peak_abs=1200,
        loopback_rms=300.0,
        ordinary_apps_receive_audio_from_endpoint=True,
        extra={
            "quality": {
                "windowsShortTermReady": False,
                "fullShortTermReady": False,
                "levelState": "low",
                "continuityState": "ok",
                "echoCancellationState": "unverified",
                "sourceTooQuietForGainOnly": True,
                "gainOnlyLikelyToAmplifyNoise": True,
                "safeMicGainAction": "hold_source_first",
                "recommendedSourceLiftDb": 18.5,
                "primaryIssue": "source_too_quiet",
                "primaryRecommendation": "move_ipad_closer",
            }
        },
    ).to_json()

    assert payload["tencent_meeting"]["state"] == "verified_audio"
    assert payload["tencent_meeting"]["readyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["audioRouteReadyForTencentMeeting"] is True
    assert payload["tencent_meeting"]["windowsQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["fullQualityReadyForTencentMeeting"] is False
    assert payload["tencent_meeting"]["qualityLevelState"] == "low"
    assert payload["tencent_meeting"]["qualityPrimaryIssue"] == "source_too_quiet"
    assert payload["tencent_meeting"]["qualityPrimaryRecommendation"] == "move_ipad_closer"
    assert payload["tencent_meeting"]["sourceTooQuietForGainOnly"] is True
    assert payload["tencent_meeting"]["gainOnlyLikelyToAmplifyNoise"] is True
    assert payload["tencent_meeting"]["recommendedSourceLiftDb"] == 18.5
    assert "still needs tuning" in payload["tencent_meeting"]["message"]
    assert payload["readiness"]["nextAction"] == "fix_ipad_source"
    assert "iPad-side microphone level" in payload["readiness"]["nextActionMessage"]


def test_webrtc_microphone_result_recommends_lower_gain_when_too_hot() -> None:
    payload = WebRTCMicrophoneResult(
        ok=True,
        meeting_input_device_found=True,
        virtual_microphone_ready=True,
        normal_app_microphone_visible=True,
        loopback_enabled=True,
        loopback_peak_abs=4000,
        loopback_rms=600.0,
        ordinary_apps_receive_audio_from_endpoint=True,
        extra={
            "quality": {
                "windowsShortTermReady": False,
                "fullShortTermReady": False,
                "levelState": "too_hot",
                "continuityState": "ok",
                "echoCancellationState": "verified",
                "safeMicGainAction": "lower_gain",
                "primaryIssue": "level_too_hot",
                "primaryRecommendation": "lower_mic_gain",
            }
        },
    ).to_json()

    assert payload["readiness"]["state"] == "route_ready_quality_not_ready"
    assert payload["readiness"]["nextAction"] == "lower_windows_gain"
    assert "lower gain" in payload["readiness"]["message"].lower()


def test_webrtc_microphone_result_marks_meeting_audio_unverified_without_loopback() -> None:
    payload = WebRTCMicrophoneResult(
        ok=True,
        meeting_input_device_found=True,
        virtual_microphone_ready=True,
        normal_app_microphone_visible=True,
        loopback_enabled=False,
        ordinary_apps_receive_audio_from_endpoint=False,
    ).to_json()

    assert payload["tencent_meeting"]["state"] == "selectable_unverified_audio"
    assert payload["tencent_meeting"]["selectable"] is True
    assert payload["tencent_meeting"]["audioVerifiedByLoopback"] is False
    assert payload["tencent_meeting"]["readyForTencentMeeting"] is False


def test_audio_frame_to_s16le_preserves_packed_stereo_interleaving() -> None:
    class FakeChannels:
        def __len__(self) -> int:
            return 2

    class FakeLayout:
        channels = FakeChannels()

    class FakeFrame:
        sample_rate = 48000
        samples = 3
        layout = FakeLayout()

        @staticmethod
        def to_ndarray():
            return np.array([[1, 10, 2, 20, 3, 30]], dtype=np.int16)

    samples, sample_rate_hz, channel_count = _audio_frame_to_s16le(np, FakeFrame())
    assert sample_rate_hz == 48000
    assert channel_count == 2
    assert samples.tolist() == [[1, 10], [2, 20], [3, 30]]


def test_write_capture_files_creates_raw_and_monitor_wav(tmp_path: Path) -> None:
    audio = np.array([[[10, -10], [20, -20], [30, -30]]], dtype=np.int16)
    payload = _write_capture_files(
        np,
        [audio.reshape(3, 2)],
        sample_rate_hz=48000,
        channels=2,
        capture_path=str(tmp_path / "sample.wav"),
        monitor_gain=2.0,
    )
    assert Path(payload["captureFile"]).is_file()
    assert Path(payload["monitorFile"]).is_file()
    assert payload["playbackFile"] == payload["monitorFile"]
    assert payload["monitorGain"] == 2.0
    assert payload["monitorPeakAbs"] == 60
    assert payload["monitorPeakDbfs"] == -54.75
    assert payload["monitorRmsDbfs"] == -57.6
    assert payload["monitorClippedSamples"] == 0
    assert payload["monitorClippedRatio"] == 0.0
    assert payload["monitorClipped"] is False


def test_write_capture_files_reports_monitor_wav_clipping(tmp_path: Path) -> None:
    payload = _write_capture_files(
        np,
        [np.array([[20000, -20000], [100, -100]], dtype=np.int16)],
        sample_rate_hz=48000,
        channels=2,
        capture_path=str(tmp_path / "sample.wav"),
        monitor_gain=2.0,
    )

    assert Path(payload["monitorFile"]).is_file()
    assert payload["monitorPeakAbs"] >= 32760
    assert payload["monitorPeakDbfs"] == -0.0
    assert payload["monitorClippedSamples"] == 2
    assert payload["monitorClippedRatio"] == 0.5
    assert payload["monitorClipped"] is True


def test_capture_level_status_reports_quiet_recording() -> None:
    payload = _capture_level_status(peak_abs=300, rms=17.994)

    assert payload["levelState"] == "low"
    assert payload["primaryIssue"] == "source_too_quiet"
    assert payload["sustainedOutputTooQuiet"] is True
    assert payload["targetSustainedRmsDbfs"] == -40.77
    assert payload["recommendedSourceLiftDb"] == 24.44


def test_capture_level_status_reports_usable_recording() -> None:
    payload = _capture_level_status(peak_abs=1200, rms=300)

    assert payload["levelState"] == "ok"
    assert payload["primaryIssue"] == "none"
    assert payload["recommendedSourceLiftDb"] == 0.0


def test_playback_buffer_normalizes_int16_samples_for_float_output() -> None:
    buffer = _PlaybackBuffer(np, channels=2, max_frames=10)
    buffer.push(np.array([[32767, -32768], [16384, -16384]], dtype=np.int16))
    outdata = np.zeros((2, 2), dtype=np.float32)

    buffer.callback(outdata, 2, None, None)

    assert np.allclose(outdata[0], [32767 / 32768.0, -1.0])
    assert np.allclose(outdata[1], [0.5, -0.5])
    assert buffer.last_segment_peak_abs == 32768


def test_playback_buffer_can_ignore_shutdown_underflows() -> None:
    buffer = _PlaybackBuffer(np, channels=2, max_frames=10)
    outdata = np.empty((4, 2), dtype=np.int16)

    buffer.count_underflows = False
    buffer.callback(outdata, 4, None, None)

    assert buffer.underflows == 0
    assert buffer.requested_frames == 0
    assert buffer.silent_frames == 0


def test_playback_buffer_tracks_silent_frame_ratio() -> None:
    buffer = _PlaybackBuffer(np, channels=1, max_frames=10)
    buffer.push(np.array([[1], [2]], dtype=np.int16))
    outdata = np.zeros((5, 1), dtype=np.int16)

    buffer.callback(outdata, 5, None, None)

    assert buffer.callbacks == 1
    assert buffer.requested_frames == 5
    assert buffer.delivered_frames == 2
    assert buffer.silent_frames == 3
    assert buffer.underflows == 1


def test_playback_buffer_trims_only_overflow_frames() -> None:
    buffer = _PlaybackBuffer(np, channels=1, max_frames=5)
    buffer.push(np.arange(1, 5, dtype=np.int16).reshape((-1, 1)))
    buffer.push(np.arange(5, 9, dtype=np.int16).reshape((-1, 1)))
    outdata = np.zeros((5, 1), dtype=np.int16)

    buffer.callback(outdata, 5, None, None)

    assert buffer.overflow_dropped_frames == 3
    assert buffer.dropped_frames == 3
    assert outdata.reshape((-1,)).tolist() == [4, 5, 6, 7, 8]


def test_playback_buffer_does_not_drop_for_latency_catchup() -> None:
    buffer = _PlaybackBuffer(np, channels=1, max_frames=20, target_frames=4)
    buffer.push(np.arange(10, dtype=np.int16).reshape((-1, 1)))
    outdata = np.zeros((4, 1), dtype=np.int16)

    buffer.callback(outdata, 4, None, None)

    assert buffer.catchup_dropped_frames == 0
    assert buffer.dropped_frames == 0
    assert outdata.reshape((-1,)).tolist() == [0, 1, 2, 3]


def test_playback_buffer_ms_frame_helpers_clamp_and_round() -> None:
    assert _ms_to_frames(2000, 48000, minimum=4800, maximum=240000) == 96000
    assert _ms_to_frames(10, 48000, minimum=4800, maximum=240000) == 4800
    assert _ms_to_frames(10000, 48000, minimum=4800, maximum=240000) == 240000
    assert _frames_to_ms(96000, 48000) == 2000.0


def test_input_capture_buffer_converts_float_capture_to_int16() -> None:
    buffer = _InputCaptureBuffer(np)

    buffer.callback(np.array([[1.0, -1.0], [0.5, -0.5]], dtype=np.float32), 2, None, None)
    chunks = buffer.pop_all()

    assert len(chunks) == 1
    assert chunks[0].dtype == np.int16
    assert chunks[0].tolist() == [[32767, -32767], [16384, -16384]]


def test_output_gain_scales_and_soft_limits_clipping() -> None:
    state = _AudioReceiverState()
    state.output_gain = 3.0

    scaled = _apply_output_gain(np, np.array([[1000, -12000], [15000, -20000]], dtype=np.int16), state)

    assert scaled[0, 0] == 3000
    assert -32768 < scaled[0, 1] < -28000
    assert 28000 < scaled[1, 0] < 32767
    assert -32768 < scaled[1, 1] < -32000
    assert state.output_clipped_samples == 3
    assert state.output_limited_samples == 3


def test_low_cut_filter_attenuates_dc_offset() -> None:
    state = _AudioReceiverState()
    state.low_cut_hz = 80.0
    samples = np.full((4800, 1), 1000, dtype=np.int16)

    filtered = _apply_low_cut_filter(np, samples, state, 48000)

    assert abs(int(filtered[-1, 0])) < 10
    assert filtered[0, 0] > filtered[-1, 0]


def test_low_cut_filter_can_be_disabled() -> None:
    state = _AudioReceiverState()
    state.low_cut_hz = 0.0
    samples = np.array([[1000, -1000], [1000, -1000]], dtype=np.int16)

    filtered = _apply_low_cut_filter(np, samples, state, 48000)

    assert filtered.tolist() == samples.tolist()


def test_record_output_samples_tracks_processed_level() -> None:
    state = _AudioReceiverState()
    samples = np.array([[100, -200], [300, -400]], dtype=np.int16)

    _record_output_samples(np, state, samples)

    assert state.output_peak_abs == 400
    assert state.output_rms > 0


def test_push_to_talk_gate_defaults_to_silence_until_control_file_allows_audio(tmp_path: Path) -> None:
    state = _AudioReceiverState()
    state.push_to_talk_control_path = str(tmp_path / "push_to_talk.json")
    state.push_to_talk_default_muted = True
    samples = np.array([[100, -200], [300, -400]], dtype=np.int16)

    muted = _apply_push_to_talk_gate(np, samples, state)

    assert muted.tolist() == [[0, 0], [0, 0]]
    assert state._push_to_talk_muted_frames == 2

    Path(state.push_to_talk_control_path).write_bytes(b'\xef\xbb\xbf{"talking": true}')
    state._push_to_talk_last_check_at = 0.0

    open_audio = _apply_push_to_talk_gate(np, samples, state)

    assert open_audio.tolist() == samples.tolist()


def test_noise_gate_attenuates_low_level_frames() -> None:
    state = _AudioReceiverState()
    state.noise_gate_threshold = 20.0
    state.noise_gate_attenuation = 0.1

    gated = _apply_noise_gate(np, np.array([[5, -5], [10, -10]], dtype=np.int16), state)

    assert gated.tolist() == [[4, -4], [8, -8]]
    assert state.noise_gate_frames == 1
    assert state.noise_gate_samples == 2
    assert 0.1 < state.noise_gate_gain < 1.0


def test_noise_gate_opens_immediately_for_loud_frames() -> None:
    state = _AudioReceiverState()
    state.noise_gate_threshold = 20.0
    state.noise_gate_attenuation = 0.1
    _apply_noise_gate(np, np.array([[5, -5]], dtype=np.int16), state)

    opened = _apply_noise_gate(np, np.array([[200, -200]], dtype=np.int16), state)

    assert opened.tolist() == [[200, -200]]
    assert state.noise_gate_gain == 1.0


def test_noise_gate_leaves_loud_frames_unchanged() -> None:
    state = _AudioReceiverState()
    state.noise_gate_threshold = 20.0
    samples = np.array([[200, -200]], dtype=np.int16)

    gated = _apply_noise_gate(np, samples, state)

    assert gated.tolist() == samples.tolist()
    assert state.noise_gate_frames == 0


def test_quality_status_reports_unverified_aec_and_continuity() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 300
    state.playback_underflows = 12
    state.playback_buffer = _PlaybackBuffer(np, channels=2, max_frames=48000)
    state.playback_buffer.callbacks = 100
    state.playback_buffer.requested_frames = 96000
    state.playback_buffer.silent_frames = 12000
    state.output_gain = 3.0

    payload = _quality_status(state, {})

    assert payload["levelState"] == "low"
    assert payload["continuityState"] == "underflowing"
    assert payload["playbackUnderflowRatio"] == 0.12
    assert payload["playbackUnderflowFrameRatio"] == 0.125
    assert payload["echoCancellationState"] == "unverified"
    assert payload["echoRiskState"] == "unknown"
    assert payload["windowsShortTermReady"] is False
    assert payload["fullShortTermReady"] is False
    assert payload["primaryIssue"] == "source_too_quiet"
    assert payload["primaryRecommendation"] == "move_ipad_closer"
    assert payload["recommendedMicGain"] == 3.0
    assert payload["recommendedMicGainStep"] == 3.0
    assert payload["sourceTooQuietForGainOnly"] is True
    assert payload["gainOnlyLikelyToAmplifyNoise"] is True
    assert "amplify room noise" in payload["gainRiskMessage"]
    assert payload["estimatedNextGainPeakAbs"] == 300
    assert payload["recommendedMonitorGain"] == 12.0
    assert any("Source level is extremely low" in item for item in payload["recommendations"])


def test_quality_status_uses_underflow_ratio_for_long_runs() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.playback_underflows = 12
    state.playback_buffer = _PlaybackBuffer(np, channels=2, max_frames=48000)
    state.playback_buffer.callbacks = 1000
    state.playback_buffer.requested_frames = 960000
    state.playback_buffer.silent_frames = 9600

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["playbackUnderflowRatio"] == 0.012
    assert payload["playbackUnderflowFrameRatio"] == 0.01
    assert payload["continuityState"] == "ok"


def test_quality_status_reports_high_latency_tradeoff() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.audio_buffer_ms = 1800.0

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["latencyState"] == "high_latency"
    assert payload["effectivePlaybackLatencyMs"] == 1800.0
    assert payload["recommendedPlaybackPrebufferMs"] == 1500.0
    assert payload["recommendedPlaybackPrebufferReason"] == "lower_after_stable"
    assert any("stable but delayed" in item for item in payload["recommendations"])


def test_quality_status_reports_low_latency_buffer() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.audio_buffer_ms = 120.0

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["latencyState"] == "low_latency"
    assert payload["continuityState"] == "ok"
    assert payload["recommendedPlaybackPrebufferReason"] == "keep_current"


def test_quality_status_recommends_raising_prebuffer_for_underflows() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.audio_buffer_ms = 100.0
    state.playback_underflows = 10
    state.playback_buffer = _PlaybackBuffer(np, channels=2, max_frames=240000, target_frames=72000)
    state.playback_buffer.callbacks = 100
    state.playback_buffer.requested_frames = 96000
    state.playback_buffer.silent_frames = 12000
    state.playback_prebuffer_frames = 72000

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["continuityState"] == "underflowing"
    assert payload["primaryIssue"] == "continuity_unstable"
    assert payload["primaryRecommendation"] == "raise_prebuffer_or_restart_bridge"
    assert payload["recommendedPlaybackPrebufferMs"] == 2500.0
    assert payload["recommendedPlaybackPrebufferReason"] == "increase_for_continuity"
    assert any("Raise playback prebuffer" in item for item in payload["recommendations"])


def test_quality_status_tolerates_small_catchup_drops() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.output_peak_abs = 2000
    state.audio_frames_written = 10000
    state.playback_dropped_frames = 200
    state.playback_buffer = _PlaybackBuffer(np, channels=2, max_frames=96000, target_frames=24000)
    state.playback_buffer.catchup_dropped_frames = 200

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["playbackDroppedRatio"] == 0.0196
    assert payload["continuityState"] == "ok"


def test_quality_status_reports_overflow_drops() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.output_peak_abs = 2000
    state.audio_frames_written = 10000
    state.playback_dropped_frames = 1200
    state.playback_buffer = _PlaybackBuffer(np, channels=2, max_frames=96000, target_frames=24000)
    state.playback_buffer.overflow_dropped_frames = 1200

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["playbackOverflowDroppedFrames"] == 1200
    assert payload["continuityState"] == "dropping"
    assert payload["primaryIssue"] == "continuity_unstable"


def test_quality_status_uses_processed_output_level() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 300
    state.output_peak_abs = 1200
    state.output_rms = 250.0

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["inputPeakAbs"] == 300
    assert payload["inputPeakDbfs"] == -40.77
    assert payload["outputPeakAbs"] == 1200
    assert payload["outputPeakDbfs"] == -28.73
    assert payload["outputRms"] == 250.0
    assert payload["outputRmsDbfs"] == -42.35
    assert payload["targetPeakDbfs"] == -18.27
    assert payload["targetSustainedRmsDbfs"] == -40.77
    assert payload["recommendedSourceLiftDb"] == 0.0
    assert payload["levelState"] == "ok"
    assert payload["recommendedMonitorGain"] == 3.33


def test_quality_status_uses_sustained_rms_for_low_level() -> None:
    state = _AudioReceiverState()
    state.output_gain = 1.5
    state.output_peak_abs = 634
    state.output_rms = 27.854

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["outputPeakDbfs"] == -34.27
    assert payload["outputRmsDbfs"] == -61.41
    assert payload["estimatedNextGainRms"] == 56
    assert payload["targetSustainedRmsDbfs"] == -40.77
    assert payload["recommendedSourceLiftDb"] == 20.64
    assert payload["safeMicGainCeiling"] == 3.0
    assert payload["safeMicGainAction"] == "hold_source_first"
    assert payload["safeMicGainCanReachTarget"] is False
    assert payload["estimatedSafeGainRmsDbfs"] == -55.35
    assert payload["sustainedOutputTooQuiet"] is True
    assert payload["levelState"] == "low"
    assert payload["primaryIssue"] == "source_too_quiet"
    assert payload["sourceTooQuietForGainOnly"] is True
    assert payload["gainOnlyLikelyToAmplifyNoise"] is True
    assert any("20.64 dB" in item for item in payload["recommendations"])


def test_quality_status_recommends_incremental_gain_step() -> None:
    state = _AudioReceiverState()
    state.output_gain = 1.0
    state.output_peak_abs = 300

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["recommendedMicGain"] == 3.0
    assert payload["recommendedMicGainStep"] == 2.0
    assert payload["safeMicGainCeiling"] == 3.0
    assert payload["safeMicGainAction"] == "raise_modestly"
    assert payload["estimatedNextGainPeakAbs"] == 600
    assert payload["sourceTooQuietForGainOnly"] is False
    assert payload["gainOnlyLikelyToAmplifyNoise"] is False
    assert any("Mic gain around 2" in item for item in payload["recommendations"])


def test_quality_status_flags_gain_limited_low_source() -> None:
    state = _AudioReceiverState()
    state.output_gain = 1.5
    state.output_peak_abs = 69

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["levelState"] == "low"
    assert payload["primaryIssue"] == "source_too_quiet"
    assert payload["recommendedMicGainStep"] == 3.0
    assert payload["estimatedNextGainPeakAbs"] == 138
    assert payload["sourceTooQuietForGainOnly"] is True
    assert payload["gainOnlyLikelyToAmplifyNoise"] is True
    assert payload["recommendedMonitorGain"] == 12.0
    assert any("Source level is extremely low" in item for item in payload["recommendations"])


def test_quality_status_reports_clipping_and_verified_aec() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 12000
    state.output_gain = 4.0
    state.output_clipped_samples = 4

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["levelState"] == "too_hot"
    assert payload["continuityState"] == "ok"
    assert payload["echoCancellationState"] == "verified"
    assert payload["primaryIssue"] == "level_too_hot"
    assert payload["primaryRecommendation"] == "lower_mic_gain"
    assert payload["recommendedMicGain"] == 2.0
    assert any("Lower Mic gain" in item for item in payload["recommendations"])


def test_quality_status_reports_soft_limiter_activity() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 9000
    state.output_gain = 3.0
    state.output_limited_samples = 2

    payload = _quality_status(state, {"voiceProcessingEnabled": True})

    assert payload["levelState"] == "ok"
    assert payload["outputLimitedSamples"] == 2
    assert payload["primaryIssue"] == "limiter_active"
    assert any("Soft limiter" in item for item in payload["recommendations"])


def test_quality_status_distinguishes_windows_and_full_short_term_ready() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000
    state.output_gain = 3.0

    without_aec = _quality_status(state, {})
    with_aec = _quality_status(state, {"echoCancellationEnabled": True})

    assert without_aec["windowsShortTermReady"] is True
    assert without_aec["fullShortTermReady"] is False
    assert without_aec["echoRiskState"] == "unknown"
    assert without_aec["primaryIssue"] == "aec_unverified"
    assert without_aec["primaryRecommendation"] == "use_headphones_or_enable_ipad_aec"
    assert with_aec["fullShortTermReady"] is True
    assert with_aec["echoRiskState"] == "controlled"
    assert with_aec["primaryIssue"] == "none"


def test_quality_status_reports_high_echo_risk_when_aec_disabled() -> None:
    state = _AudioReceiverState()
    state.receiver_peak_abs = 2000

    payload = _quality_status(state, {"voiceProcessingEnabled": False})

    assert payload["windowsShortTermReady"] is True
    assert payload["fullShortTermReady"] is False
    assert payload["echoCancellationState"] == "disabled"
    assert payload["echoRiskState"] == "high"
