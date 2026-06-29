from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from bridgeclient import (
    BridgeClientError,
    HttpTransport,
    NullAudioSink,
    PcmFileAudioSink,
    SensorBridgeClient,
    UsbMuxTransport,
    analyze_audio_frame,
    capture_vbcable_output,
    check_vbcable_loopback,
    check_microphone_pipeline,
    error_json,
    inspect_media_devices,
    inspect_microphone_install_plan,
    inspect_microphone_install_status,
    inspect_microphone_pcm_feeder,
    inspect_microphone_readiness,
    inspect_microphone_route_status,
    inspect_microphone_test_signing_status,
    inspect_windows_endpoint_capture,
    inspect_vbcable,
    pump_audio_frames,
    pump_vbcable_frames,
    record_vbcable_output_until_stop,
    run_webrtc_microphone_receiver,
)


COMMAND_ALIASES = {
    "health": "health",
    "status": "status",
    "capabilities": "capabilities",
    "startaudio": "start_audio",
    "start_audio": "start_audio",
    "stopaudio": "stop_audio",
    "stop_audio": "stop_audio",
    "sampleaudio": "sample_audio",
    "sample_audio": "sample_audio",
    "pumpaudio": "pump_audio",
    "pump_audio": "pump_audio",
    "microphonepipelinecheck": "microphone_pipeline_check",
    "microphone_pipeline_check": "microphone_pipeline_check",
    "micpipelinecheck": "microphone_pipeline_check",
    "microphonefeedercheck": "microphone_feeder_check",
    "microphone_feeder_check": "microphone_feeder_check",
    "micfeedercheck": "microphone_feeder_check",
    "mediadevices": "media_devices",
    "media_devices": "media_devices",
    "microphoneroutestatus": "microphone_route_status",
    "microphone_route_status": "microphone_route_status",
    "microutestatus": "microphone_route_status",
    "microphonereadiness": "microphone_readiness",
    "microphone_readiness": "microphone_readiness",
    "microphoneinstallplan": "microphone_install_plan",
    "microphone_install_plan": "microphone_install_plan",
    "microphoneinstallstatus": "microphone_install_status",
    "microphone_install_status": "microphone_install_status",
    "microphonetestsigningstatus": "microphone_test_signing_status",
    "microphone_test_signing_status": "microphone_test_signing_status",
    "microphoneproductstatus": "microphone_product_status",
    "microphone_product_status": "microphone_product_status",
    "productstatus": "microphone_product_status",
    "product_status": "microphone_product_status",
    "windowsendpointcapturecheck": "windows_endpoint_capture_check",
    "windows_endpoint_capture_check": "windows_endpoint_capture_check",
    "endpointcapturecheck": "windows_endpoint_capture_check",
    "endpoint_capture_check": "windows_endpoint_capture_check",
    "vbcablestatus": "vbcable_status",
    "vbcable_status": "vbcable_status",
    "cablestatus": "vbcable_status",
    "cable_status": "vbcable_status",
    "pumpvbcable": "pump_vbcable",
    "pump_vbcable": "pump_vbcable",
    "vbcablepump": "pump_vbcable",
    "vbcableloopbackcheck": "vbcable_loopback_check",
    "vbcable_loopback_check": "vbcable_loopback_check",
    "cableloopbackcheck": "vbcable_loopback_check",
    "cable_loopback_check": "vbcable_loopback_check",
    "vbcable_product_status": "vbcable_product_status",
    "vbcableproductstatus": "vbcable_product_status",
    "safe_product_status": "vbcable_product_status",
    "safeproductstatus": "vbcable_product_status",
    "webrtcmicrophone": "webrtc_microphone",
    "webrtc_microphone": "webrtc_microphone",
    "webrtcmic": "webrtc_microphone",
    "webrtc_mic": "webrtc_microphone",
    "webrtcreceiver": "webrtc_microphone",
    "webrtc_receiver": "webrtc_microphone",
    "webrtcloopbackcheck": "webrtc_loopback_check",
    "webrtc_loopback_check": "webrtc_loopback_check",
    "webrtcmicrophoneloopback": "webrtc_loopback_check",
    "webrtc_microphone_loopback": "webrtc_loopback_check",
    "vbcableoutputcapture": "vbcable_output_capture",
    "vbcable_output_capture": "vbcable_output_capture",
    "cableoutputcapture": "vbcable_output_capture",
    "cable_output_capture": "vbcable_output_capture",
    "vbcableoutputrecord": "vbcable_output_record",
    "vbcable_output_record": "vbcable_output_record",
    "cableoutputrecord": "vbcable_output_record",
    "cable_output_record": "vbcable_output_record",
    "diagnosticsummary": "diagnostic_summary",
    "diagnostic_summary": "diagnostic_summary",
    "webrtcdiagnosticsummary": "diagnostic_summary",
    "webrtc_diagnostic_summary": "diagnostic_summary",
    "connectioncheck": "connection_check",
    "connection_check": "connection_check",
    "backendcheck": "connection_check",
    "backend_check": "connection_check",
    "gaintune": "gain_tune",
    "gain_tune": "gain_tune",
    "mictune": "gain_tune",
    "mic_tune": "gain_tune",
    "microphonegaintune": "gain_tune",
    "microphone_gain_tune": "gain_tune",
    "desktopshortcutstatus": "desktop_shortcut_status",
    "desktop_shortcut_status": "desktop_shortcut_status",
    "shortcutstatus": "desktop_shortcut_status",
    "shortcut_status": "desktop_shortcut_status",
    "diagnosticbundle": "diagnostic_bundle",
    "diagnostic_bundle": "diagnostic_bundle",
    "bundle_diagnostics": "diagnostic_bundle",
    "diagnosticsbundle": "diagnostic_bundle",
    "shorttermstatus": "short_term_status",
    "short_term_status": "short_term_status",
    "shortterm_status": "short_term_status",
    "short-term-status": "short_term_status",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SensorBridge Microphone Windows client.")
    parser.add_argument("command", nargs="?", default="microphone-product-status")
    parser.add_argument("--base-url", default="http://192.168.0.24:27180")
    parser.add_argument("--relay-url", default="http://192.168.0.23:27181")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--frame-delay", type=float, default=0.0)
    parser.add_argument("--pcm-dir", default="")
    parser.add_argument("--output-device", default="CABLE Input")
    parser.add_argument("--transport", choices=("http", "usbmux"), default="http")
    parser.add_argument("--usbmux-local-port", type=int, default=27181)
    parser.add_argument("--usbmux-device-port", type=int, default=27180)
    parser.add_argument("--usbmux-start-proxy", action="store_true")
    parser.add_argument("--iproxy-path", default="")
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--no-video-recvonly", action="store_true")
    parser.add_argument("--skip-normal-app-probe", action="store_true")
    parser.add_argument("--loopback-capture", action="store_true")
    parser.add_argument("--no-start-ipad-microphone", action="store_true")
    parser.add_argument("--capture-path", default="")
    parser.add_argument("--monitor-gain", type=float, default=1.0)
    parser.add_argument("--output-gain", type=float, default=1.0)
    parser.add_argument("--low-cut-hz", type=float, default=80.0)
    parser.add_argument("--noise-gate-threshold", type=float, default=0.0)
    parser.add_argument("--gain-values", default="")
    parser.add_argument("--tune-dir", default="")
    parser.add_argument("--playback-prebuffer-ms", type=float, default=1500.0)
    parser.add_argument("--playback-max-buffer-ms", type=float, default=5000.0)
    parser.add_argument("--push-to-talk-control", default="")
    parser.add_argument("--push-to-talk-default-muted", action="store_true")
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--tail-seconds", type=float, default=0.0)
    parser.add_argument("--shortcut-name", default="SensorBridge Microphone.lnk")
    parser.add_argument("--bundle-path", default="")
    parser.add_argument("--bundle-max-files", type=int, default=24)
    return parser


def normalize_command(raw: str) -> str:
    key = raw.strip().lower().replace("-", "_")
    compact = key.replace("_", "")
    return COMMAND_ALIASES.get(key) or COMMAND_ALIASES.get(compact) or key


def make_client(args: argparse.Namespace) -> SensorBridgeClient:
    if args.transport == "usbmux":
        transport = UsbMuxTransport(
            local_port=args.usbmux_local_port,
            device_port=args.usbmux_device_port,
            iproxy_path=args.iproxy_path or None,
            start_proxy=args.usbmux_start_proxy,
            timeout=args.timeout,
        )
    else:
        transport = HttpTransport(args.base_url, timeout=args.timeout)
    return SensorBridgeClient(transport)


def microphone_product_status(client: SensorBridgeClient, args: argparse.Namespace) -> dict[str, Any]:
    started = None
    stop = None
    frames = []
    errors: list[str] = []
    warnings: list[str] = []
    sink = PcmFileAudioSink(args.pcm_dir or None)
    start_wall = time.time()
    try:
        started = client.start_audio().to_json()
        for index in range(max(1, args.frames)):
            frame = client.sample_audio_frame()
            analysis = analyze_audio_frame(frame)
            sink_error = None
            try:
                sink.write_frame(frame)
            except Exception as exc:
                sink_error = str(exc)
                warnings.append(f"sequence {frame.audio_sample_sequence}: {sink_error}")
            frames.append(
                {
                    "analysis": analysis.to_json(),
                    "source": frame.raw.get("source") if isinstance(frame.raw, dict) else None,
                    "timestamp_ns": frame.timestamp_ns,
                    "latency_ms": _estimate_latency_ms(frame.timestamp_ns),
                    "pcm_handoff_error": sink_error,
                }
            )
            if args.frame_delay > 0 and index < args.frames - 1:
                time.sleep(args.frame_delay)
    except Exception as exc:
        errors.append(str(exc))
    finally:
        try:
            stop = client.stop_audio().to_json()
        except Exception as exc:
            errors.append(f"stop_audio: {exc}")

    analyses = [item["analysis"] for item in frames]
    latest = analyses[-1] if analyses else {}
    valid_frames = [item for item in frames if item["analysis"].get("valid_pcm")]
    latencies = [item["latency_ms"] for item in frames if item.get("latency_ms") is not None]
    sources = [str(item.get("source") or "") for item in frames]
    real_ipad_audio = any(
        item["analysis"].get("valid_pcm") and not _looks_synthetic(str(item.get("source") or ""))
        for item in frames
    )
    received_frames = len(frames)

    route = inspect_microphone_route_status(Path(__file__).resolve().parent)
    feeder = inspect_microphone_pcm_feeder(args.pcm_dir or None)
    endpoint_capture = inspect_windows_endpoint_capture(duration_s=0.35)
    elapsed_ms = round((time.time() - start_wall) * 1000.0, 3)
    endpoint_present = bool(route.get("audio_endpoint_present"))
    endpoint_visible = bool(route.get("normal_app_visible"))
    handoff_ready = bool(feeder.can_feed_driver)
    ipad_injected = bool(endpoint_capture.get("ipad_pcm_injected_into_virtual_endpoint"))
    product_ready = (
        bool(valid_frames)
        and real_ipad_audio
        and endpoint_present
        and endpoint_visible
        and handoff_ready
        and ipad_injected
        and not errors
    )
    return {
        "ok": product_ready,
        "command": "microphone_product_status",
        "base_url": getattr(client.transport, "base_url", args.base_url),
        "changes_system": False,
        "started": started,
        "stop": stop,
        "frames_requested": max(1, args.frames),
        "frames_received": received_frames,
        "valid_pcm_frames": len(valid_frames),
        "latest_audio": latest,
        "peak_abs": latest.get("peak_abs"),
        "rms": latest.get("rms"),
        "volume_percent": _volume_percent(latest.get("rms")),
        "latency_ms": _percentile(latencies, 50),
        "latency_p90_ms": _percentile(latencies, 90),
        "elapsed_ms": elapsed_ms,
        "real_ipad_microphone_data": real_ipad_audio,
        "synthetic_or_mock_source_detected": any(_looks_synthetic(source) for source in sources if source),
        "sources": sources,
        "device_enumerated": bool(route.get("device_enumerated")),
        "audio_endpoint_present": endpoint_present,
        "audio_endpoint_count": route.get("audio_endpoint_count"),
        "normal_app_visible": endpoint_visible,
        "windows_apps_can_select_sensorbridge_microphone": endpoint_visible,
        "ordinary_apps_receive_audio_from_endpoint": bool(endpoint_capture.get("ordinary_apps_receive_audio_from_endpoint")),
        "ipad_pcm_injected_into_virtual_endpoint": ipad_injected,
        "endpoint_audio_looks_like_sysvad_test_tone": bool(endpoint_capture.get("endpoint_audio_looks_like_sysvad_test_tone")),
        "latest_pcm_handoff_ready": handoff_ready,
        "pcm_handoff": feeder.to_json(),
        "windows_endpoint_capture": endpoint_capture,
        "route": route,
        "errors": errors,
        "warnings": warnings,
        "completion_rule": "Ready only when normal apps can select SensorBridge Microphone and the virtual endpoint is confirmed to carry iPad microphone PCM.",
    }


def vbcable_product_status(client: SensorBridgeClient, args: argparse.Namespace) -> dict[str, Any]:
    started = None
    stop = None
    frames = []
    errors: list[str] = []
    warnings: list[str] = []
    start_wall = time.time()
    try:
        started = client.start_audio().to_json()
        for index in range(max(1, args.frames)):
            frame = client.sample_audio_frame()
            analysis = analyze_audio_frame(frame)
            frames.append(
                {
                    "analysis": analysis.to_json(),
                    "source": frame.raw.get("source") if isinstance(frame.raw, dict) else None,
                    "timestamp_ns": frame.timestamp_ns,
                    "latency_ms": _estimate_latency_ms(frame.timestamp_ns),
                }
            )
            if args.frame_delay > 0 and index < args.frames - 1:
                time.sleep(args.frame_delay)
    except Exception as exc:
        errors.append(str(exc))
    finally:
        try:
            stop = client.stop_audio().to_json()
        except Exception as exc:
            errors.append(f"stop_audio: {exc}")

    analyses = [item["analysis"] for item in frames]
    latest = analyses[-1] if analyses else {}
    valid_frames = [item for item in frames if item["analysis"].get("valid_pcm")]
    latencies = [item["latency_ms"] for item in frames if item.get("latency_ms") is not None]
    sources = [str(item.get("source") or "") for item in frames]
    real_ipad_audio = any(
        item["analysis"].get("valid_pcm") and not _looks_synthetic(str(item.get("source") or ""))
        for item in frames
    )
    cable = inspect_vbcable(args.output_device)
    cable_ready = bool(cable.get("output_device_found")) and bool(cable.get("meeting_input_device_found"))
    return {
        "ok": bool(valid_frames) and real_ipad_audio and cable_ready and not errors,
        "command": "vbcable_product_status",
        "base_url": getattr(client.transport, "base_url", args.base_url),
        "changes_system": False,
        "mode": "user_mode_vbcable_audio_bridge",
        "started": started,
        "stop": stop,
        "frames_requested": max(1, args.frames),
        "frames_received": len(frames),
        "valid_pcm_frames": len(valid_frames),
        "latest_audio": latest,
        "peak_abs": latest.get("peak_abs"),
        "rms": latest.get("rms"),
        "volume_percent": _volume_percent(latest.get("rms")),
        "latency_ms": _percentile(latencies, 50),
        "latency_p90_ms": _percentile(latencies, 90),
        "elapsed_ms": round((time.time() - start_wall) * 1000.0, 3),
        "real_ipad_microphone_data": real_ipad_audio,
        "synthetic_or_mock_source_detected": any(_looks_synthetic(source) for source in sources if source),
        "sources": sources,
        "vbcable": cable,
        "vbcable_output_device": args.output_device,
        "vbcable_output_found": bool(cable.get("output_device_found")),
        "meeting_microphone_device": cable.get("meeting_input_device", "CABLE Output"),
        "meeting_microphone_found": bool(cable.get("meeting_input_device_found")),
        "ready_for_tencent_meeting": cable_ready and real_ipad_audio,
        "errors": errors,
        "warnings": warnings,
        "completion_rule": "Ready when iPad microphone PCM is real and VB-CABLE exposes CABLE Input/CABLE Output. Tencent Meeting should select CABLE Output.",
    }


def run_command(client: SensorBridgeClient, args: argparse.Namespace) -> dict[str, Any]:
    command = normalize_command(args.command)
    root = Path(__file__).resolve().parent
    if command == "health":
        return client.health()
    if command == "status":
        return client.status()
    if command == "capabilities":
        return client.capabilities()
    if command == "connection_check":
        return check_backend_connections(args.base_url, args.relay_url, timeout=args.timeout)
    if command == "desktop_shortcut_status":
        return inspect_desktop_shortcut(args.shortcut_name, args.base_url, args.relay_url, args.output_device)
    if command == "diagnostic_bundle":
        return create_diagnostic_bundle(
            args.bundle_path,
            max_files=args.bundle_max_files,
            base_url=args.base_url,
            relay_url=args.relay_url,
            output_device=args.output_device,
            shortcut_name=args.shortcut_name,
        )
    if command == "short_term_status":
        return inspect_short_term_status(
            args.base_url,
            args.relay_url,
            args.output_device,
            args.shortcut_name,
            timeout=args.timeout,
        )
    if command == "gain_tune":
        return run_gain_tune(args)
    if command == "start_audio":
        return client.start_audio().to_json()
    if command == "stop_audio":
        return client.stop_audio().to_json()
    if command == "sample_audio":
        return {"ok": True, "command": "sample_audio", "audio_frame": client.sample_audio_frame().to_json()}
    if command == "pump_audio":
        sink = PcmFileAudioSink(args.pcm_dir or None)
        return pump_audio_frames(client, sink, frame_count=max(1, args.frames), frame_delay_s=args.frame_delay).to_json()
    if command == "pump_vbcable":
        return pump_vbcable_frames(
            client,
            frame_count=args.frames,
            frame_delay_s=args.frame_delay,
            output_device=args.output_device,
        ).to_json()
    if command == "vbcable_loopback_check":
        return check_vbcable_loopback(
            client,
            frame_count=max(1, args.frames),
            frame_delay_s=args.frame_delay,
            output_device=args.output_device,
        ).to_json()
    if command == "microphone_pipeline_check":
        return check_microphone_pipeline(
            client,
            frame_count=max(1, args.frames),
            frame_delay_s=args.frame_delay,
            directory=args.pcm_dir or None,
        ).to_json()
    if command == "microphone_feeder_check":
        return inspect_microphone_pcm_feeder(args.pcm_dir or None).to_json()
    if command == "media_devices":
        return inspect_media_devices(root)
    if command == "microphone_route_status":
        return inspect_microphone_route_status(root)
    if command == "microphone_readiness":
        return inspect_microphone_readiness(root)
    if command == "microphone_install_plan":
        return inspect_microphone_install_plan(root)
    if command == "microphone_install_status":
        return inspect_microphone_install_status(root)
    if command == "microphone_test_signing_status":
        return inspect_microphone_test_signing_status(root)
    if command == "windows_endpoint_capture_check":
        return inspect_windows_endpoint_capture()
    if command == "vbcable_status":
        return inspect_vbcable(args.output_device)
    if command == "vbcable_product_status":
        return vbcable_product_status(client, args)
    if command == "microphone_product_status":
        return microphone_product_status(client, args)
    if command == "diagnostic_summary":
        if not args.capture_path:
            raise BridgeClientError("--capture-path is required for diagnostic-summary", code="missing_capture_path")
        return summarize_diagnostic_json(args.capture_path)
    if command == "vbcable_output_capture":
        return capture_vbcable_output(
            duration_seconds=args.duration_seconds,
            capture_path=args.capture_path or None,
            monitor_gain=args.monitor_gain,
        )
    if command == "vbcable_output_record":
        if not args.capture_path:
            raise BridgeClientError("--capture-path is required for vbcable-output-record", code="missing_capture_path")
        if not args.stop_file:
            raise BridgeClientError("--stop-file is required for vbcable-output-record", code="missing_stop_file")
        return record_vbcable_output_until_stop(
            stop_file=args.stop_file,
            capture_path=args.capture_path,
            monitor_gain=args.monitor_gain,
            tail_seconds=args.tail_seconds,
        )
    if command in {"webrtc_microphone", "webrtc_loopback_check"}:
        result = run_webrtc_microphone_receiver(
            base_url=getattr(client.transport, "base_url", args.base_url),
            output_device=args.output_device,
            duration_seconds=args.duration_seconds,
            timeout=args.timeout,
            include_video_recvonly=not args.no_video_recvonly,
            normal_app_probe=not args.skip_normal_app_probe,
            loopback_capture=args.loopback_capture or command == "webrtc_loopback_check",
            start_ipad_microphone=not args.no_start_ipad_microphone,
            output_gain=args.output_gain,
            low_cut_hz=args.low_cut_hz,
            noise_gate_threshold=args.noise_gate_threshold,
            playback_prebuffer_ms=args.playback_prebuffer_ms,
            playback_max_buffer_ms=args.playback_max_buffer_ms,
            capture_path=args.capture_path or None,
            push_to_talk_control_path=args.push_to_talk_control or None,
            push_to_talk_default_muted=args.push_to_talk_default_muted,
        ).to_json()
        result["latest_diagnostics"] = write_latest_webrtc_diagnostics(result)
        return result
    raise BridgeClientError(f"Unknown command '{args.command}'", code="unknown_command", detail={"command": args.command})


def run_gain_tune(args: argparse.Namespace) -> dict[str, Any]:
    gains = _parse_gain_values(args.gain_values)
    tune_dir = Path(args.tune_dir) if args.tune_dir else Path(__file__).resolve().parent / "captures" / "gain_tune"
    tune_dir.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y%m%d_%H%M%S")
    runs = []
    for gain in gains:
        tag = str(gain).replace(".", "p").replace("-", "m")
        capture_path = tune_dir / f"{started}_gain_{tag}.wav"
        result = run_webrtc_microphone_receiver(
            base_url=args.base_url,
            output_device=args.output_device,
            duration_seconds=args.duration_seconds,
            timeout=args.timeout,
            include_video_recvonly=not args.no_video_recvonly,
            normal_app_probe=not args.skip_normal_app_probe,
            loopback_capture=True,
            start_ipad_microphone=not args.no_start_ipad_microphone,
            output_gain=gain,
            low_cut_hz=args.low_cut_hz,
            noise_gate_threshold=args.noise_gate_threshold,
            playback_prebuffer_ms=args.playback_prebuffer_ms,
            playback_max_buffer_ms=args.playback_max_buffer_ms,
            capture_path=str(capture_path),
        ).to_json()
        json_path = tune_dir / f"{started}_gain_{tag}.json"
        json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        runs.append(_gain_tune_run_summary(gain, result, capture_path, json_path))
    best = _select_gain_tune_best(runs)
    return {
        "ok": bool(best and best.get("ok")),
        "command": "gain_tune",
        "changes_system": False,
        "base_url": args.base_url,
        "durationSecondsPerGain": args.duration_seconds,
        "outputDevice": args.output_device,
        "gainValues": gains,
        "recommendedGain": best.get("gain") if best else None,
        "recommendedReason": best.get("reason") if best else "no usable gain run",
        "best": best,
        "runs": runs,
        "nextAction": "use_recommended_gain_and_retest" if best else "check_transport_or_cable_route",
    }


def _parse_gain_values(raw: str) -> list[float]:
    if not str(raw or "").strip():
        return [0.75, 1.0, 1.25]
    gains: list[float] = []
    for item in str(raw).replace(";", ",").split(","):
        value = item.strip()
        if not value:
            continue
        try:
            gain = float(value)
        except ValueError as exc:
            raise BridgeClientError(f"Invalid --gain-values entry: {value}", code="invalid_gain_values") from exc
        if gain <= 0 or gain > 6:
            raise BridgeClientError("--gain-values entries must be > 0 and <= 6", code="invalid_gain_values")
        gains.append(round(gain, 3))
    if not gains:
        raise BridgeClientError("--gain-values did not contain any numeric gains", code="invalid_gain_values")
    return gains


def _gain_tune_run_summary(gain: float, result: dict[str, Any], capture_path: Path, json_path: Path) -> dict[str, Any]:
    readiness = _dict_value(result, "readiness")
    receiver = _dict_value(result, "windows_receiver")
    loopback = _dict_value(result, "windows_loopback_capture")
    quality = _dict_value(result, "quality")
    captures = _dict_value(result, "diagnostic_captures")
    attribution = _dict_value(captures, "qualityAttribution")
    score, reason = _score_gain_tune_run(result)
    return {
        "gain": gain,
        "ok": bool(result.get("ok")),
        "score": score,
        "reason": reason,
        "readiness": readiness.get("state"),
        "nextAction": readiness.get("nextAction"),
        "primaryIssue": quality.get("primaryIssue"),
        "safeMicGainAction": quality.get("safeMicGainAction"),
        "qualityAttributionStage": attribution.get("stage"),
        "rawRmsDbfs": receiver.get("receiverRmsDbfs"),
        "processedRmsDbfs": receiver.get("outputRmsDbfs"),
        "processedPeakDbfs": receiver.get("outputPeakDbfs"),
        "cableActiveRmsDbfs": loopback.get("activeRmsDbfs"),
        "underflows": receiver.get("playbackUnderflows"),
        "drops": receiver.get("playbackDroppedFrames"),
        "packetsReceived": receiver.get("audioPacketsReceived"),
        "capturePath": str(capture_path.resolve()),
        "jsonPath": str(json_path.resolve()),
    }


def _select_gain_tune_best(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [run for run in runs if run.get("ok")]
    if not usable:
        return None
    return max(usable, key=lambda run: (float(run.get("score") or -9999), -abs(float(run.get("gain") or 1.0) - 1.0)))


def _score_gain_tune_run(result: dict[str, Any]) -> tuple[float, str]:
    readiness = _dict_value(result, "readiness")
    receiver = _dict_value(result, "windows_receiver")
    loopback = _dict_value(result, "windows_loopback_capture")
    quality = _dict_value(result, "quality")
    captures = _dict_value(result, "diagnostic_captures")
    attribution = _dict_value(captures, "qualityAttribution")
    score = 0.0
    reasons = []
    state = readiness.get("state")
    if state == "full_quality_ready":
        score += 100
        reasons.append("full quality ready")
    elif state == "windows_quality_ready":
        score += 70
        reasons.append("Windows quality ready")
    elif readiness.get("audioRouteReady") is True:
        score += 35
        reasons.append("route verified")
    if attribution.get("stage") == "audio_level_route_ok":
        score += 25
        reasons.append("route level ok")
    cable_active = _float_or_none(loopback.get("activeRmsDbfs"))
    if cable_active is not None:
        score += max(0.0, 30.0 - abs(cable_active - -52.0) * 3.0)
        reasons.append(f"CABLE active RMS {round(cable_active, 2)} dBFS")
    peak = _float_or_none(receiver.get("outputPeakDbfs"))
    if peak is not None and peak > -12.0:
        score -= 30
        reasons.append("peak too hot")
    underflows = _float_or_none(receiver.get("playbackUnderflows")) or 0.0
    drops = _float_or_none(receiver.get("playbackDroppedFrames")) or 0.0
    score -= min(40.0, (underflows + drops) * 4.0)
    if underflows or drops:
        reasons.append("continuity issues")
    safe_action = str(quality.get("safeMicGainAction") or "")
    if safe_action == "lower_gain":
        score -= 20
        reasons.append("gain should be lowered")
    elif safe_action == "raise_modestly":
        score -= 5
        reasons.append("may raise gain modestly")
    elif safe_action == "hold_source_first":
        score -= 25
        reasons.append("iPad source should be fixed first")
    return round(score, 3), "; ".join(reasons) if reasons else "no strong signal"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_backend_connections(base_url: str, relay_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    targets = [
        {"name": "direct", "base_url": _normalize_url(base_url)},
        {"name": "relay", "base_url": _normalize_url(relay_url)},
    ]
    results = []
    for target in targets:
        health = _probe_json_endpoint(target["base_url"], "/health", timeout=timeout)
        status = _probe_json_endpoint(target["base_url"], "/api/v2/webrtc/status", timeout=timeout) if health["ok"] else {
            "ok": False,
            "path": "/api/v2/webrtc/status",
            "skipped": True,
            "error": "health check failed",
        }
        results.append({
            "name": target["name"],
            "base_url": target["base_url"],
            "health": health,
            "webrtcStatus": status,
            "ready": bool(health["ok"] and status["ok"]),
        })
    preferred, selection_reason = _select_preferred_backend(results)
    return {
        "ok": preferred is not None,
        "command": "connection_check",
        "changes_system": False,
        "preferredBaseUrl": preferred["base_url"] if preferred else None,
        "backendSelectionReason": selection_reason,
        "recommendedNextAction": "run_webrtc_smoke" if preferred else "restart_ipad_app_or_mac_relay",
        "targets": results,
    }


def _select_preferred_backend(results: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    relay = next((item for item in results if item.get("name") == "relay"), None)
    direct = next((item for item in results if item.get("name") == "direct"), None)
    if relay and relay.get("ready"):
        if direct and direct.get("ready"):
            return relay, "relay_ready_preferred_for_stability"
        return relay, "relay_ready_direct_unavailable"
    if direct and direct.get("ready"):
        return direct, "direct_ready_relay_unavailable"
    ready = next((item for item in results if item.get("ready")), None)
    if ready:
        return ready, "first_ready_nonstandard_backend"
    return None, "no_backend_ready"


def _normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value.rstrip("/")


def _probe_json_endpoint(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    started = time.time()
    url = _normalize_url(base_url) + path
    try:
        with urllib.request.urlopen(url, timeout=max(0.5, float(timeout or 5.0))) as response:
            raw = response.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                payload = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                payload = {"raw": text[:500]}
            return {
                "ok": 200 <= int(response.status) < 300,
                "path": path,
                "status": int(response.status),
                "elapsedMs": round((time.time() - started) * 1000.0, 3),
                "payload": payload,
            }
    except Exception as exc:
        return {
            "ok": False,
            "path": path,
            "elapsedMs": round((time.time() - started) * 1000.0, 3),
            "error": str(exc),
        }


def inspect_desktop_shortcut(
    shortcut_name: str,
    base_url: str,
    relay_url: str,
    output_device: str,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    app_exe = root / "windows-app" / "SensorBridge.Microphone.App" / "bin" / "Release" / "SensorBridge.Microphone.App.exe"
    desktop = Path.home() / "Desktop"
    shortcut_path = desktop / (shortcut_name or "SensorBridge Microphone.lnk")
    shortcut = _read_windows_shortcut(shortcut_path)
    arguments = str(shortcut.get("arguments") or "")
    target = Path(str(shortcut.get("target") or "")) if shortcut.get("target") else None
    working_directory = Path(str(shortcut.get("workingDirectory") or "")) if shortcut.get("workingDirectory") else None
    target_matches = bool(target and _same_path(target, app_exe))
    root_matches = _quoted_arg_present(arguments, "--project-root", str(root))
    base_matches = _quoted_arg_present(arguments, "--base-url", _normalize_url(base_url))
    relay_matches = _quoted_arg_present(arguments, "--relay-url", _normalize_url(relay_url))
    output_matches = _quoted_arg_present(arguments, "--output-device", output_device)
    working_directory_matches = bool(working_directory and _same_path(working_directory, root))
    shortcut_ok = bool(
        shortcut.get("exists")
        and target_matches
        and root_matches
        and base_matches
        and relay_matches
        and output_matches
        and working_directory_matches
    )
    return {
        "ok": shortcut_ok,
        "command": "desktop_shortcut_status",
        "changes_system": False,
        "shortcut": str(shortcut_path),
        "shortcutExists": bool(shortcut.get("exists")),
        "target": shortcut.get("target"),
        "targetExists": bool(target and target.exists()),
        "expectedTarget": str(app_exe),
        "targetMatches": target_matches,
        "arguments": arguments,
        "projectRootArgumentOk": root_matches,
        "baseUrlArgumentOk": base_matches,
        "relayUrlArgumentOk": relay_matches,
        "outputDeviceArgumentOk": output_matches,
        "workingDirectory": shortcut.get("workingDirectory"),
        "workingDirectoryMatches": working_directory_matches,
        "icon": shortcut.get("icon"),
        "recommendedNextAction": "install_shortcut" if not shortcut.get("exists") else ("ready_or_monitor" if shortcut_ok else "reinstall_shortcut"),
        "errors": shortcut.get("errors") or [],
    }


def _read_windows_shortcut(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "errors": []}
    script = (
        "$path=[Environment]::GetEnvironmentVariable('SENSORBRIDGE_SHORTCUT_PATH'); "
        "$shell=New-Object -ComObject WScript.Shell; "
        "$s=$shell.CreateShortcut($path); "
        "[pscustomobject]@{exists=$true;target=$s.TargetPath;arguments=$s.Arguments;"
        "workingDirectory=$s.WorkingDirectory;icon=$s.IconLocation} | ConvertTo-Json -Compress"
    )
    try:
        env = dict(os.environ)
        env["SENSORBRIDGE_SHORTCUT_PATH"] = str(path)
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
            env=env,
        )
        if completed.returncode != 0:
            return {"exists": True, "errors": [completed.stderr.strip() or completed.stdout.strip() or "shortcut read failed"]}
        payload = json.loads(completed.stdout)
        payload["errors"] = []
        return payload
    except Exception as exc:
        return {"exists": True, "errors": [str(exc)]}


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve().as_posix().lower() == right.resolve().as_posix().lower()
    except Exception:
        return str(left).lower() == str(right).lower()


def _quoted_arg_present(arguments: str, name: str, expected: str) -> bool:
    text = str(arguments or "")
    if not expected:
        return False
    return f'{name} "{expected}"' in text or f"{name} {expected}" in text


def create_diagnostic_bundle(
    bundle_path: str = "",
    *,
    max_files: int = 24,
    base_url: str = "http://192.168.0.24:27180",
    relay_url: str = "http://192.168.0.23:27181",
    output_device: str = "CABLE Input",
    shortcut_name: str = "SensorBridge Microphone.lnk",
) -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    captures_dir = root / "captures"
    bundle_dir = captures_dir / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    if bundle_path:
        output = Path(bundle_path)
        if not output.is_absolute():
            output = root / output
    else:
        output = bundle_dir / f"sensorbridge_microphone_diagnostics_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)

    files = _select_diagnostic_bundle_files(captures_dir, max_files=max(1, int(max_files or 24)))
    environment = _diagnostic_bundle_environment(
        shortcut_name=shortcut_name,
        base_url=base_url,
        relay_url=relay_url,
        output_device=output_device,
    )
    manifest = {
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "capturesDir": str(captures_dir),
        "fileCount": len(files),
        "environment": {
            "desktopShortcutOk": _dict_value(environment, "desktop_shortcut_status").get("ok"),
            "vbcableOutputFound": _dict_value(environment, "vbcable_status").get("output_device_found"),
            "meetingInputFound": _dict_value(environment, "vbcable_status").get("meeting_input_device_found"),
        },
        "files": [
            {
                "path": str(path.relative_to(captures_dir)),
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
            for path in files
        ],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name, payload in environment.items():
            archive.writestr(f"environment/{name}.json", json.dumps(payload, indent=2, sort_keys=True))
        for path in files:
            archive.write(path, "captures/" + str(path.relative_to(captures_dir)).replace("\\", "/"))
    return {
        "ok": output.exists(),
        "command": "diagnostic_bundle",
        "changes_system": False,
        "bundlePath": str(output.resolve()),
        "bundleExists": output.exists(),
        "bundleSize": output.stat().st_size if output.exists() else 0,
        "filesIncluded": len(files),
        "capturesDir": str(captures_dir),
        "recommendedNextAction": "send_bundle_to_debugging_thread" if files else "run_record_or_gain_tune_first",
        "manifest": manifest,
        "environment": environment,
    }


def _diagnostic_bundle_environment(
    *,
    shortcut_name: str,
    base_url: str,
    relay_url: str,
    output_device: str,
) -> dict[str, Any]:
    return {
        "desktop_shortcut_status": _safe_status(
            lambda: inspect_desktop_shortcut(shortcut_name, base_url, relay_url, output_device),
            "desktop_shortcut_status",
        ),
        "vbcable_status": _safe_status(
            lambda: inspect_vbcable(output_device),
            "vbcable_status",
        ),
    }


def _safe_status(callback, command: str) -> dict[str, Any]:
    try:
        payload = callback()
        if isinstance(payload, dict):
            return payload
        return {"ok": False, "command": command, "error": "status did not return a JSON object"}
    except Exception as exc:
        return {"ok": False, "command": command, "error": str(exc)}


def inspect_short_term_status(
    base_url: str,
    relay_url: str,
    output_device: str,
    shortcut_name: str,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    shortcut = _safe_status(
        lambda: inspect_desktop_shortcut(shortcut_name, base_url, relay_url, output_device),
        "desktop_shortcut_status",
    )
    vbcable = _safe_status(lambda: inspect_vbcable(output_device), "vbcable_status")
    backend = _safe_status(lambda: check_backend_connections(base_url, relay_url, timeout=timeout), "connection_check")
    latest_summary = _read_latest_webrtc_summary(root)
    checks = {
        "desktopShortcutReady": bool(shortcut.get("ok")),
        "vbcableReady": bool(vbcable.get("output_device_found") and vbcable.get("meeting_input_device_found")),
        "backendReady": bool(backend.get("ok")),
        "latestWebRtcSummaryPresent": bool(latest_summary.get("exists")),
        "latestWebRtcQualityReady": bool(_dict_value(latest_summary, "readiness").get("fullQualityReady")),
    }
    next_action = _short_term_next_action(checks, latest_summary)
    return {
        "ok": bool(checks["desktopShortcutReady"] and checks["vbcableReady"] and checks["backendReady"]),
        "command": "short_term_status",
        "changes_system": False,
        "checks": checks,
        "recommendedNextAction": next_action,
        "desktopShortcut": shortcut,
        "vbcable": vbcable,
        "backend": backend,
        "latestWebRtcSummary": latest_summary,
    }


def _read_latest_webrtc_summary(root: Path) -> dict[str, Any]:
    path = root / "captures" / "latest_webrtc_summary.json"
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        payload = json.loads(_read_json_text(path))
        if isinstance(payload, dict):
            payload["exists"] = True
            payload["path"] = str(path)
            return payload
        return {"exists": True, "path": str(path), "error": "summary JSON was not an object"}
    except Exception as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}


def _short_term_next_action(checks: dict[str, bool], latest_summary: dict[str, Any]) -> str:
    if not checks.get("desktopShortcutReady"):
        return "install_or_reinstall_shortcut"
    if not checks.get("vbcableReady"):
        return "install_or_fix_vbcable"
    if not checks.get("backendReady"):
        return "start_ipad_app_or_mac_relay"
    if not checks.get("latestWebRtcSummaryPresent"):
        return "run_refresh_record_or_tune"
    readiness = _dict_value(latest_summary, "readiness")
    next_action = str(readiness.get("nextAction") or "")
    if next_action:
        return next_action
    return "ready_or_monitor" if checks.get("latestWebRtcQualityReady") else "run_refresh_record_or_tune"


def write_latest_webrtc_diagnostics(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    base = root or Path(__file__).resolve().parent
    captures_dir = base / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    status_path = captures_dir / "latest_webrtc_status.json"
    summary_path = captures_dir / "latest_webrtc_summary.json"
    text_path = captures_dir / "latest_webrtc_summary.txt"

    status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = summarize_diagnostic_json(str(status_path))
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    text_path.write_text(str(summary.get("textReport") or ""), encoding="utf-8")
    return {
        "statusPath": str(status_path.resolve()),
        "summaryPath": str(summary_path.resolve()),
        "textPath": str(text_path.resolve()),
    }


def _select_diagnostic_bundle_files(captures_dir: Path, *, max_files: int) -> list[Path]:
    if not captures_dir.exists():
        return []
    allowed_suffixes = {".json", ".txt", ".wav", ".log"}
    all_files = [
        path for path in captures_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in allowed_suffixes
        and "bundles" not in {part.lower() for part in path.relative_to(captures_dir).parts}
    ]
    priority_names = {
        "latest_webrtc_status.json",
        "latest_webrtc_summary.json",
        "latest_webrtc_summary.txt",
    }
    selected: list[Path] = []
    for path in sorted(all_files, key=lambda item: item.name.lower()):
        if path.name in priority_names:
            selected.append(path)
    recent = sorted(all_files, key=lambda item: item.stat().st_mtime, reverse=True)
    for path in recent:
        if path not in selected:
            selected.append(path)
        if len(selected) >= max_files:
            break
    return selected[:max_files]


def summarize_diagnostic_json(path: str) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise BridgeClientError(f"Diagnostic JSON not found: {path}", code="missing_diagnostic_json")
    try:
        payload = json.loads(_read_json_text(source))
    except json.JSONDecodeError as exc:
        raise BridgeClientError(f"Invalid diagnostic JSON: {exc}", code="invalid_diagnostic_json") from exc

    readiness = _dict_value(payload, "readiness")
    receiver = _dict_value(payload, "windows_receiver")
    loopback = _dict_value(payload, "windows_loopback_capture")
    quality = _dict_value(payload, "quality")
    captures = _dict_value(payload, "diagnostic_captures")
    attribution = _dict_value(captures, "qualityAttribution")
    ipad_status = _dict_value(payload, "ipad_webrtc_status")
    ipad_upstream = _dict_value(payload, "ipad_upstream")
    next_action, next_action_message = _summary_next_action(readiness, quality)
    summary = {
        "ok": bool(payload.get("ok")),
        "command": "diagnostic_summary",
        "changes_system": False,
        "sourceFile": str(source.resolve()),
        "readiness": {
            "state": readiness.get("state"),
            "message": readiness.get("message"),
            "nextAction": next_action,
            "nextActionMessage": next_action_message,
            "audioRouteReady": readiness.get("audioRouteReady"),
            "loopbackQualityReady": readiness.get("loopbackQualityReady"),
            "windowsQualityReady": readiness.get("windowsQualityReady"),
            "fullQualityReady": readiness.get("fullQualityReady"),
        },
        "levels": {
            "windowsRawRmsDbfs": receiver.get("receiverRmsDbfs"),
            "windowsProcessedRmsDbfs": receiver.get("outputRmsDbfs"),
            "cableOutputRmsDbfs": loopback.get("rmsDbfs"),
            "cableOutputActiveRmsDbfs": loopback.get("activeRmsDbfs"),
            "windowsRawPeakDbfs": receiver.get("receiverPeakDbfs"),
            "windowsProcessedPeakDbfs": receiver.get("outputPeakDbfs"),
            "cableOutputPeakDbfs": loopback.get("peakDbfs"),
            "ipadInputRmsDbfs": ipad_status.get("microphoneInputRmsDbfs"),
            "ipadProcessedRmsDbfs": ipad_status.get("microphoneProcessedRmsDbfs"),
            "ipadInputPeakDbfs": ipad_status.get("microphoneInputPeakDbfs"),
            "ipadProcessedPeakDbfs": ipad_status.get("microphoneProcessedPeakDbfs"),
        },
        "quality": {
            "primaryIssue": quality.get("primaryIssue"),
            "safeMicGainAction": quality.get("safeMicGainAction"),
            "safeMicGainCeiling": quality.get("safeMicGainCeiling"),
            "safeMicGainCanReachTarget": quality.get("safeMicGainCanReachTarget"),
            "recommendedSourceLiftDb": quality.get("recommendedSourceLiftDb"),
            "qualityAttributionStage": attribution.get("stage"),
        },
        "continuity": {
            "underflows": receiver.get("playbackUnderflows"),
            "drops": receiver.get("playbackDroppedFrames"),
            "packetsReceived": receiver.get("audioPacketsReceived"),
            "upstreamState": ipad_upstream.get("microphoneUpstreamState"),
            "upstreamPacketsSent": ipad_upstream.get("microphoneUpstreamPacketsSent"),
            "upstreamStatsFresh": ipad_upstream.get("microphoneUpstreamStatsFresh"),
        },
        "ipadProcessing": {
            "voiceProcessingEnabled": ipad_status.get("microphoneVoiceProcessingEnabled"),
            "echoCancellationEnabled": ipad_status.get("microphoneEchoCancellationEnabled"),
            "automaticGainControlEnabled": ipad_status.get("microphoneAutomaticGainControlEnabled"),
            "noiseSuppressionEnabled": ipad_status.get("microphoneNoiseSuppressionEnabled"),
            "audioSessionCategory": ipad_status.get("microphoneAudioSessionCategory"),
            "audioSessionMode": ipad_status.get("microphoneAudioSessionMode"),
            "audioSessionOptions": ipad_status.get("microphoneAudioSessionOptions"),
            "inputRoute": ipad_status.get("microphoneInputRoute"),
            "realIpadMicrophone": ipad_status.get("realIpadMicrophone"),
        },
        "files": _diagnostic_layer_files(captures),
    }
    summary["textReport"] = _diagnostic_text_report(summary)
    return summary


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _read_json_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.lstrip().startswith(("{", "[")):
            return text
    return data.decode("utf-8")


def _summary_next_action(readiness: dict[str, Any], quality: dict[str, Any]) -> tuple[Any, Any]:
    if readiness.get("fullQualityReady") is True or readiness.get("state") == "full_quality_ready":
        return "ready_or_monitor", "Route is usable; monitor level, echo, and continuity during meeting use."
    existing = readiness.get("nextAction")
    if existing:
        return existing, readiness.get("nextActionMessage")
    primary_issue = str(quality.get("primaryIssue") or "")
    safe_action = str(quality.get("safeMicGainAction") or "")
    if readiness.get("audioRouteReady") is not True:
        return "verify_cable_route", "Verify CABLE Output is visible and records audio before using Tencent Meeting."
    if safe_action == "hold_source_first" or primary_issue == "source_too_quiet":
        return "fix_ipad_source", "Improve iPad-side microphone level or WebRTC native send processing before adding more Windows gain."
    if readiness.get("loopbackQualityReady") is False:
        return "fix_meeting_loopback_level", "CABLE Output is verified but too quiet for ordinary meeting apps; improve source level or use a modest safe gain step."
    if safe_action == "lower_gain" or primary_issue in {"level_too_hot", "limiter_active"}:
        return "lower_windows_gain", "Lower Windows Mic gain and re-test layered captures."
    if safe_action == "raise_modestly" or primary_issue == "level_low":
        return "raise_windows_gain_modestly", "Try the recommended modest Mic gain step, then re-test CABLE Output."
    return "ready_or_monitor", "Route is usable; monitor level, echo, and continuity during meeting use."


def _diagnostic_layer_files(captures: dict[str, Any]) -> dict[str, Any]:
    layers = _dict_value(captures, "layers")
    return {
        "receiverRaw": _dict_value(layers, "receiver_raw").get("path"),
        "processed": _dict_value(layers, "processed").get("path"),
        "cableOutput": _dict_value(layers, "cable_output").get("path"),
    }


def _diagnostic_text_report(summary: dict[str, Any]) -> str:
    readiness = _dict_value(summary, "readiness")
    levels = _dict_value(summary, "levels")
    quality = _dict_value(summary, "quality")
    continuity = _dict_value(summary, "continuity")
    ipad = _dict_value(summary, "ipadProcessing")
    files = _dict_value(summary, "files")
    lines = [
        "SensorBridge Microphone diagnostic summary",
        f"ok: {summary.get('ok')}",
        f"readiness: {readiness.get('state')}",
        f"nextAction: {readiness.get('nextAction')}",
        f"nextActionMessage: {readiness.get('nextActionMessage')}",
        "",
        "Levels:",
        f"- Windows raw RMS: {levels.get('windowsRawRmsDbfs')} dBFS",
        f"- Windows processed RMS: {levels.get('windowsProcessedRmsDbfs')} dBFS",
        f"- CABLE Output RMS: {levels.get('cableOutputRmsDbfs')} dBFS",
        f"- CABLE Output active RMS: {levels.get('cableOutputActiveRmsDbfs')} dBFS",
        f"- iPad input RMS: {levels.get('ipadInputRmsDbfs')} dBFS",
        f"- iPad processed RMS: {levels.get('ipadProcessedRmsDbfs')} dBFS",
        "",
        "Quality:",
        f"- primaryIssue: {quality.get('primaryIssue')}",
        f"- attribution: {quality.get('qualityAttributionStage')}",
        f"- safeMicGainAction: {quality.get('safeMicGainAction')}",
        f"- safeMicGainCeiling: {quality.get('safeMicGainCeiling')}",
        f"- safeMicGainCanReachTarget: {quality.get('safeMicGainCanReachTarget')}",
        "",
        "Continuity:",
        f"- underflows/drops: {continuity.get('underflows')} / {continuity.get('drops')}",
        f"- packetsReceived: {continuity.get('packetsReceived')}",
        f"- upstream: {continuity.get('upstreamState')} packets={continuity.get('upstreamPacketsSent')} fresh={continuity.get('upstreamStatsFresh')}",
        "",
        "iPad processing:",
        f"- voiceProcessing/AEC/AGC/NS: {ipad.get('voiceProcessingEnabled')} / {ipad.get('echoCancellationEnabled')} / {ipad.get('automaticGainControlEnabled')} / {ipad.get('noiseSuppressionEnabled')}",
        f"- session: {ipad.get('audioSessionCategory')} / {ipad.get('audioSessionMode')} / {ipad.get('audioSessionOptions')}",
        f"- inputRoute: {ipad.get('inputRoute')}",
        f"- realIpadMicrophone: {ipad.get('realIpadMicrophone')}",
        "",
        "Files:",
        f"- receiverRaw: {files.get('receiverRaw')}",
        f"- processed: {files.get('processed')}",
        f"- cableOutput: {files.get('cableOutput')}",
    ]
    return "\n".join(lines)


def _estimate_latency_ms(timestamp_ns: int | None) -> float | None:
    if not timestamp_ns:
        return None
    latency_ms = (time.time_ns() - int(timestamp_ns)) / 1_000_000.0
    if latency_ms < -5000 or latency_ms > 60 * 60 * 1000:
        return None
    return round(max(0.0, latency_ms), 3)


def _looks_synthetic(source: str) -> bool:
    text = source.lower()
    return any(term in text for term in ("mock", "demo", "synthetic", "generated", "simulated", "simulator"))


def _volume_percent(rms: Any) -> float | None:
    if rms is None:
        return None
    try:
        return round(min(100.0, max(0.0, (float(rms) / 32768.0) * 100.0)), 3)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((percentile / 100.0) * (len(values) - 1))))
    return round(values[index], 3)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = make_client(args)
        payload = run_command(client, args)
    except BridgeClientError as exc:
        payload = exc.to_json()
    except Exception as exc:
        payload = {"ok": False, "error": {"code": "unexpected_error", "message": str(exc)}}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
