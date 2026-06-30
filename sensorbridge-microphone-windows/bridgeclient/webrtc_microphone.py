from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bridgeclient.media_devices import inspect_media_devices
from bridgeclient.vbcable import DEFAULT_CABLE_OUTPUT_DEVICE, DEFAULT_MEETING_INPUT_DEVICE


JsonDict = dict[str, Any]


@dataclass
class WebRTCMicrophoneResult:
    ok: bool
    command: str = "webrtc_microphone"
    base_url: str = "http://192.168.0.24:27180"
    output_device: str = DEFAULT_CABLE_OUTPUT_DEVICE
    output_device_found: bool = False
    meeting_input_device: str = DEFAULT_MEETING_INPUT_DEVICE
    meeting_input_device_found: bool = False
    duration_seconds: float = 10.0
    audio_packets_received: int = 0
    audio_bytes_received: int = 0
    audio_frames_written: int = 0
    audio_buffer_ms: float = 0.0
    last_frame_age_ms: float | None = None
    receiver_state: str = "idle"
    virtual_microphone_ready: bool = False
    normal_app_microphone_visible: bool = False
    loopback_enabled: bool = False
    loopback_frame_count: int = 0
    loopback_peak_abs: int | None = None
    loopback_rms: float | None = None
    loopback_active_rms: float | None = None
    loopback_active_frame_count: int = 0
    loopback_nonzero_samples: int = 0
    ordinary_apps_receive_audio_from_endpoint: bool = False
    ipad_microphone_upstream_state: str | None = None
    ipad_microphone_upstream_packets_sent: int | None = None
    ipad_microphone_upstream_bytes_sent: int | None = None
    ipad_microphone_upstream_stats_fresh: bool | None = None
    ipad_microphone_upstream_stats_age_ms: float | None = None
    windows_peer_connection_state: str | None = None
    windows_ice_connection_state: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extra: JsonDict = field(default_factory=dict)

    def to_json(self) -> JsonDict:
        quality = self.extra.get("quality") if isinstance(self.extra.get("quality"), dict) else {}
        tencent_meeting = self._tencent_meeting_status(quality)
        readiness = _readiness_summary(self.ok, tencent_meeting, quality)
        return {
            "ok": self.ok,
            "readiness": readiness,
            "command": self.command,
            "changes_system": False,
            "transport": "webrtc_opus_microphone_upstream",
            "base_url": self.base_url,
            "output_device": self.output_device,
            "output_device_found": self.output_device_found,
            "meeting_input_device": self.meeting_input_device,
            "meeting_input_device_found": self.meeting_input_device_found,
            "duration_seconds": self.duration_seconds,
            "windows_receiver": {
                "receiverState": self.receiver_state,
                "audioPacketsReceived": self.audio_packets_received,
                "audioBytesReceived": self.audio_bytes_received,
                "audioFramesWritten": self.audio_frames_written,
                "audioBufferMs": self.audio_buffer_ms,
                "lastFrameAgeMs": self.last_frame_age_ms,
                "outputSampleRateHz": self.extra.get("output_sample_rate_hz"),
                "outputChannels": self.extra.get("output_channels"),
                "outputGain": self.extra.get("output_gain"),
                "lowCutHz": self.extra.get("low_cut_hz"),
                "outputClippedSamples": self.extra.get("output_clipped_samples"),
                "outputLimitedSamples": self.extra.get("output_limited_samples"),
                "noiseGateThreshold": self.extra.get("noise_gate_threshold"),
                "noiseGateFrames": self.extra.get("noise_gate_frames"),
                "noiseGateSamples": self.extra.get("noise_gate_samples"),
                "playbackUnderflows": self.extra.get("playback_underflows"),
                "playbackDroppedFrames": self.extra.get("playback_dropped_frames"),
                "playbackOverflowDroppedFrames": self.extra.get("playbackOverflowDroppedFrames"),
                "playbackCatchupDroppedFrames": self.extra.get("playbackCatchupDroppedFrames"),
                "playbackUnderflowRatio": self.extra.get("playbackUnderflowRatio"),
                "playbackUnderflowFrameRatio": self.extra.get("playbackUnderflowFrameRatio"),
                "playbackRequestedFrames": self.extra.get("playbackRequestedFrames"),
                "playbackDeliveredFrames": self.extra.get("playbackDeliveredFrames"),
                "playbackSilentFrames": self.extra.get("playbackSilentFrames"),
                "playbackPrebufferMs": self.extra.get("playbackPrebufferMs"),
                "playbackMaxBufferMs": self.extra.get("playbackMaxBufferMs"),
                "playbackDroppedRatio": self.extra.get("playbackDroppedRatio"),
                "receiverPeakAbs": self.extra.get("receiver_peak_abs"),
                "receiverRms": self.extra.get("receiver_rms"),
                "outputPeakAbs": self.extra.get("output_peak_abs"),
                "outputRms": self.extra.get("output_rms"),
                "playbackCallbacks": self.extra.get("playbackCallbacks"),
                "playbackOutputDtype": self.extra.get("playbackOutputDtype"),
                "playbackSegmentPeakAbs": self.extra.get("playbackSegmentPeakAbs"),
                "receiverPeakDbfs": _dbfs(self.extra.get("receiver_peak_abs")),
                "receiverRmsDbfs": _dbfs(self.extra.get("receiver_rms")),
                "outputPeakDbfs": _dbfs(self.extra.get("output_peak_abs")),
                "outputRmsDbfs": _dbfs(self.extra.get("output_rms")),
                "virtualMicrophoneReady": self.virtual_microphone_ready,
                "normalAppMicrophoneVisible": self.normal_app_microphone_visible,
                "peerConnectionState": self.windows_peer_connection_state,
                "iceConnectionState": self.windows_ice_connection_state,
            },
            "windows_loopback_capture": {
                "enabled": self.loopback_enabled,
                "captureDevice": self.meeting_input_device,
                "recordedFrameCount": self.loopback_frame_count,
                "peakAbs": self.loopback_peak_abs,
                "rms": self.loopback_rms,
                "activeRms": self.loopback_active_rms,
                "peakDbfs": _dbfs(self.loopback_peak_abs),
                "rmsDbfs": _dbfs(self.loopback_rms),
                "activeRmsDbfs": _dbfs(self.loopback_active_rms),
                "activeFrameCount": self.loopback_active_frame_count,
                "nonzeroSamples": self.loopback_nonzero_samples,
                "ordinaryAppsReceiveAudioFromEndpoint": self.ordinary_apps_receive_audio_from_endpoint,
                **_capture_level_status(self.loopback_peak_abs, self.loopback_active_rms if self.loopback_active_rms is not None else self.loopback_rms),
            },
            "tencent_meeting": tencent_meeting,
            "ipad_upstream": {
                "microphoneUpstreamState": self.ipad_microphone_upstream_state,
                "microphoneUpstreamPacketsSent": self.ipad_microphone_upstream_packets_sent,
                "microphoneUpstreamBytesSent": self.ipad_microphone_upstream_bytes_sent,
                "microphoneUpstreamStatsFresh": self.ipad_microphone_upstream_stats_fresh,
                "microphoneUpstreamStatsAgeMs": self.ipad_microphone_upstream_stats_age_ms,
            },
            "virtual_microphone_ready": self.virtual_microphone_ready,
            "normal_app_microphone_visible": self.normal_app_microphone_visible,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            **self.extra,
        }

    def _tencent_meeting_status(self, quality: JsonDict | None = None) -> JsonDict:
        selectable = bool(self.meeting_input_device_found and self.normal_app_microphone_visible)
        audio_verified = bool(self.loopback_enabled and self.ordinary_apps_receive_audio_from_endpoint)
        route_ready = bool(selectable and audio_verified)
        quality = quality or {}
        loopback_rms_for_quality = self.loopback_active_rms if self.loopback_active_rms is not None else self.loopback_rms
        loopback_quality = _capture_level_status(self.loopback_peak_abs, loopback_rms_for_quality) if self.loopback_enabled else {}
        loopback_quality_ready = bool((not self.loopback_enabled) or loopback_quality.get("levelState") == "ok")
        windows_quality_ready = bool(route_ready and quality.get("windowsShortTermReady") is True and loopback_quality_ready)
        full_quality_ready = bool(route_ready and quality.get("fullShortTermReady") is True and loopback_quality_ready)
        if not selectable:
            state = "not_selectable"
            message = "CABLE Output is not visible as a normal microphone input."
        elif audio_verified:
            state = "verified_audio"
            if windows_quality_ready:
                message = "CABLE Output route is verified and Windows-side short-term quality is ready."
            elif not loopback_quality_ready:
                message = "CABLE Output route is verified, but ordinary-app loopback capture is too quiet for meeting quality."
            else:
                message = "CABLE Output route is verified, but current level/continuity quality still needs tuning."
        elif self.loopback_enabled:
            state = "no_loopback_audio"
            message = "CABLE Output is selectable, but loopback capture did not verify audio."
        else:
            state = "selectable_unverified_audio"
            message = "CABLE Output is selectable; run Test Cable or Record to verify audio before Tencent Meeting."
        return {
            "state": state,
            "message": message,
            "selectable": selectable,
            "audioVerifiedByLoopback": audio_verified,
            "audioRouteReadyForTencentMeeting": route_ready,
            "readyForTencentMeeting": route_ready,
            "windowsQualityReadyForTencentMeeting": windows_quality_ready,
            "fullQualityReadyForTencentMeeting": full_quality_ready,
            "qualityLevelState": quality.get("levelState"),
            "qualityContinuityState": quality.get("continuityState"),
            "qualityEchoCancellationState": quality.get("echoCancellationState"),
            "qualityPrimaryIssue": quality.get("primaryIssue"),
            "qualityPrimaryRecommendation": quality.get("primaryRecommendation"),
            "loopbackQualityReadyForTencentMeeting": loopback_quality_ready,
            "loopbackLevelState": loopback_quality.get("levelState"),
            "loopbackPrimaryIssue": loopback_quality.get("primaryIssue"),
            "loopbackRecommendedSourceLiftDb": loopback_quality.get("recommendedSourceLiftDb"),
            "sourceTooQuietForGainOnly": bool(quality.get("sourceTooQuietForGainOnly") is True),
            "gainOnlyLikelyToAmplifyNoise": bool(quality.get("gainOnlyLikelyToAmplifyNoise") is True),
            "recommendedSourceLiftDb": quality.get("recommendedSourceLiftDb"),
            "manualSelectionDevice": self.meeting_input_device,
        }


class WebRTCMicrophoneClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.timeout = timeout

    def request_json(self, method: str, path: str, payload: JsonDict | None = None) -> JsonDict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{path} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach {self.base_url}{path}: {exc}") from exc
        return json.loads(body) if body.strip() else {"ok": True}

    def post_offer(self, offer: JsonDict) -> JsonDict:
        return self.request_json("POST", "/api/v2/webrtc/offer", offer)

    def start_audio(self) -> JsonDict:
        return self.request_json("POST", "/api/v1/audio/start", {})

    def local_ice_candidates(self) -> JsonDict:
        return self.request_json("GET", "/api/v2/webrtc/local-ice-candidates")

    def post_receiver_stats(self, stats: JsonDict) -> JsonDict:
        return self.request_json("POST", "/api/v2/webrtc/receiver-stats", stats)

    def webrtc_status(self) -> JsonDict:
        return self.request_json("GET", "/api/v2/webrtc/status")


def _readiness_summary(ok: bool, meeting: JsonDict, quality: JsonDict) -> JsonDict:
    route_ready = bool(meeting.get("audioRouteReadyForTencentMeeting") is True)
    loopback_quality_ready = bool(meeting.get("loopbackQualityReadyForTencentMeeting") is True)
    windows_quality_ready = bool(meeting.get("windowsQualityReadyForTencentMeeting") is True)
    full_quality_ready = bool(meeting.get("fullQualityReadyForTencentMeeting") is True)
    next_action, next_action_message = _readiness_next_action(ok, meeting, quality)
    if full_quality_ready:
        state = "full_quality_ready"
        message = "Audio route, Windows loopback quality, and iPad AEC evidence are ready for meeting use."
    elif windows_quality_ready:
        state = "windows_quality_ready"
        message = "Audio route and Windows loopback quality are ready; iPad AEC is not fully verified."
    elif route_ready:
        state = "route_ready_quality_not_ready"
        if next_action == "fix_ipad_source":
            message = "Audio route is verified, but the WebRTC microphone source is too quiet; improve the iPad-side source before adding Windows gain."
        elif next_action == "lower_windows_gain":
            message = "Audio route is verified, but Windows Mic gain is too hot; lower gain before meeting use."
        elif next_action == "raise_windows_gain_modestly":
            message = "Audio route is verified, but level is still low; try a modest Windows Mic gain step."
        else:
            message = "Audio route is verified, but meeting-quality audio is not ready."
    elif ok:
        state = "transport_ready_route_not_verified"
        message = "WebRTC transport is running, but the ordinary-app microphone route is not verified."
    else:
        state = "not_ready"
        message = "WebRTC microphone bridge is not ready."
    return {
        "state": state,
        "message": message,
        "okMeans": "transport_or_route_ready_not_quality",
        "transportOk": bool(ok),
        "audioRouteReady": route_ready,
        "loopbackQualityReady": loopback_quality_ready,
        "windowsQualityReady": windows_quality_ready,
        "fullQualityReady": full_quality_ready,
        "nextAction": next_action,
        "nextActionMessage": next_action_message,
        "primaryIssue": quality.get("primaryIssue"),
        "meetingState": meeting.get("state"),
    }


def _readiness_next_action(ok: bool, meeting: JsonDict, quality: JsonDict) -> tuple[str, str]:
    safe_gain_action = str(quality.get("safeMicGainAction") or "")
    primary_issue = str(quality.get("primaryIssue") or "")
    if not ok:
        return "check_transport", "Start or repair the WebRTC microphone bridge."
    if meeting.get("audioRouteReadyForTencentMeeting") is not True:
        return "verify_cable_route", "Verify CABLE Output is visible and records audio before using Tencent Meeting."
    if safe_gain_action == "hold_source_first" or primary_issue == "source_too_quiet":
        return "fix_ipad_source", "Improve iPad-side microphone level or WebRTC native send processing before adding more Windows gain."
    if meeting.get("loopbackQualityReadyForTencentMeeting") is False:
        return "fix_meeting_loopback_level", "CABLE Output is verified but too quiet for ordinary meeting apps; improve source level or use a modest safe gain step."
    if safe_gain_action == "lower_gain" or primary_issue in {"level_too_hot", "limiter_active"}:
        return "lower_windows_gain", "Lower Windows Mic gain and re-test layered captures."
    if safe_gain_action == "raise_modestly" or primary_issue == "level_low":
        return "raise_windows_gain_modestly", "Try the recommended modest Mic gain step, then re-test CABLE Output."
    if quality.get("continuityState") not in {"", None, "ok"}:
        return "stabilize_buffer", "Increase prebuffer or restart the bridge if underflows or drops keep rising."
    if quality.get("echoCancellationState") not in {"", None, "verified"}:
        return "verify_aec", "Use headphones or verify iPad-side AEC before relying on speakerphone meeting use."
    return "ready_or_monitor", "Route is usable; monitor level, echo, and continuity during meeting use."


async def run_webrtc_microphone_receiver_async(
    *,
    base_url: str = "http://192.168.0.24:27180",
    output_device: str = DEFAULT_CABLE_OUTPUT_DEVICE,
    duration_seconds: float = 10.0,
    timeout: float = 10.0,
    include_video_recvonly: bool = False,
    normal_app_probe: bool = True,
    loopback_capture: bool = False,
    start_ipad_microphone: bool = True,
    output_gain: float = 1.0,
    low_cut_hz: float = 80.0,
    noise_gate_threshold: float = 0.0,
    playback_prebuffer_ms: float = 1500.0,
    playback_max_buffer_ms: float = 5000.0,
    capture_path: str | None = None,
    push_to_talk_control_path: str | None = None,
    push_to_talk_default_muted: bool = False,
) -> WebRTCMicrophoneResult:
    backend = _load_audio_backend()
    if not backend["ok"]:
        return WebRTCMicrophoneResult(ok=False, base_url=base_url, output_device=output_device, errors=[backend["error"]["message"]])

    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from aiortc import RTCRtpSender

    sd = backend["sounddevice"]
    np = backend["numpy"]
    devices = _device_list(sd)
    output = _find_device(devices, output_device, is_output=True)
    meeting_input = _find_device(devices, DEFAULT_MEETING_INPUT_DEVICE, is_input=True)
    output_found = output is not None
    meeting_found = meeting_input is not None
    virtual_ready = bool(output_found and meeting_found)
    normal_visible = _normal_app_microphone_visible(normal_app_probe)
    if not output_found:
        return WebRTCMicrophoneResult(
            ok=False,
            base_url=base_url,
            output_device=output_device,
            output_device_found=False,
            meeting_input_device_found=meeting_found,
            virtual_microphone_ready=False,
            normal_app_microphone_visible=normal_visible,
            errors=[f"VB-CABLE playback device not found: {output_device}"],
        )

    client = WebRTCMicrophoneClient(base_url, timeout=timeout)
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
    receiver = _AudioReceiverState(
        loopback_capture=loopback_capture or bool(capture_path),
        loopback_input_index=int(meeting_input["index"]) if meeting_input else None,
        capture_path=capture_path,
    )
    receiver.output_gain = max(0.05, min(20.0, float(output_gain or 1.0)))
    receiver.low_cut_hz = max(0.0, min(300.0, float(low_cut_hz or 0.0)))
    receiver.noise_gate_threshold = max(0.0, min(5000.0, float(noise_gate_threshold or 0.0)))
    receiver.playback_prebuffer_frames = _ms_to_frames(playback_prebuffer_ms, 48000, minimum=4800, maximum=240000)
    receiver.playback_max_buffer_frames = _ms_to_frames(playback_max_buffer_ms, 48000, minimum=receiver.playback_prebuffer_frames, maximum=480000)
    receiver.push_to_talk_control_path = push_to_talk_control_path or ""
    receiver.push_to_talk_default_muted = bool(push_to_talk_default_muted)
    warnings: list[str] = []
    errors: list[str] = []
    final_status: JsonDict = {}
    peer_connection_state: str | None = None
    ice_connection_state: str | None = None
    stats_posted = False
    start_audio_result: JsonDict | None = None

    @pc.on("track")
    def on_track(track: Any) -> None:
        if getattr(track, "kind", None) == "audio":
            asyncio.create_task(_consume_audio_track(track, receiver, sd, np, int(output["index"]), warnings))

    try:
        if receiver.loopback_capture and meeting_found:
            _start_loopback_capture_process(receiver, duration_seconds)
        if start_ipad_microphone:
            start_audio_result = client.start_audio()
        if include_video_recvonly:
            pc.addTransceiver("video", direction="recvonly")
        audio_transceiver = pc.addTransceiver("audio", direction="recvonly")
        _prefer_codec(audio_transceiver, RTCRtpSender.getCapabilities("audio").codecs, "opus")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await _wait_for_ice_gathering_complete(pc, timeout_seconds=5.0)
        local = pc.localDescription
        answer_payload = client.post_offer({"type": local.type, "sdp": local.sdp})
        answer = _extract_description(answer_payload)
        if answer is None:
            raise RuntimeError(f"WebRTC offer response did not include localDescription answer: {answer_payload}")
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        await _apply_polled_ice_candidates(pc, client, warnings)

        deadline = None
        audio_wait_deadline = None if duration_seconds <= 0 else time.monotonic() + max(10.0, timeout + 5.0)
        last_post_at = 0.0
        while True:
            await asyncio.sleep(0.25)
            now = time.monotonic()
            if duration_seconds > 0 and receiver.output_stream is not None and deadline is None:
                deadline = now + max(1.0, duration_seconds)
            if deadline is not None and now >= deadline:
                break
            if deadline is None and audio_wait_deadline is not None and now >= audio_wait_deadline:
                warnings.append("timed out waiting for first WebRTC microphone audio frame")
                break
            peer_connection_state = str(pc.connectionState)
            ice_connection_state = str(pc.iceConnectionState)
            stats = await pc.getStats()
            packets, bytes_received = _inbound_audio_totals(stats)
            receiver.audio_packets_received = max(receiver.audio_packets_received, packets)
            receiver.audio_bytes_received = max(receiver.audio_bytes_received, bytes_received)
            if now - last_post_at >= 1.0:
                last_post_at = now
                stats_payload = _receiver_stats_payload(receiver, virtual_ready, normal_visible, pc)
                try:
                    client.post_receiver_stats(stats_payload)
                    stats_posted = True
                except Exception as exc:
                    warnings.append(f"receiver stats post failed: {exc}")
                try:
                    final_status = client.webrtc_status()
                except Exception as exc:
                    warnings.append(f"webrtc status poll failed: {exc}")
        if receiver.playback_buffer is not None:
            receiver.playback_buffer.count_underflows = False
        try:
            client.post_receiver_stats(_receiver_stats_payload(receiver, virtual_ready, normal_visible, pc))
            stats_posted = True
        except Exception as exc:
            warnings.append(f"final receiver stats post failed: {exc}")
        try:
            final_status = client.webrtc_status()
        except Exception as exc:
            warnings.append(f"final webrtc status poll failed: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        receiver.stopping = True
        if receiver.playback_buffer is not None:
            receiver.playback_buffer.count_underflows = False
        if receiver.output_stream is not None:
            try:
                await asyncio.to_thread(receiver.output_stream.stop)
                await asyncio.to_thread(receiver.output_stream.close)
            except Exception as exc:
                warnings.append(f"closing VB-CABLE output stream: {exc}")
        if receiver.loopback_input_stream is not None:
            try:
                await asyncio.to_thread(receiver.loopback_input_stream.stop)
                await asyncio.to_thread(receiver.loopback_input_stream.close)
            except Exception as exc:
                warnings.append(f"closing CABLE Output loopback stream: {exc}")
        if receiver.loopback_process is not None:
            _finish_loopback_capture_process(receiver, warnings)
        _close_diagnostic_capture_writers(receiver, warnings)
        try:
            await pc.close()
        except Exception as exc:
            warnings.append(f"peer close: {exc}")

    upstream = _microphone_upstream_status(final_status)
    if receiver.playback_buffer is not None:
        receiver.playback_underflows = receiver.playback_buffer.underflows
        receiver.playback_dropped_frames = receiver.playback_buffer.dropped_frames
        receiver.extra_playback_stats = {
            "playbackCallbacks": receiver.playback_buffer.callbacks,
            "playbackOutputDtype": receiver.playback_buffer.output_dtype,
            "playbackSegmentPeakAbs": receiver.playback_buffer.last_segment_peak_abs,
            "playbackUnderflowRatio": _playback_underflow_ratio(receiver),
            "playbackUnderflowFrameRatio": _playback_underflow_frame_ratio(receiver),
            "playbackRequestedFrames": receiver.playback_buffer.requested_frames,
            "playbackDeliveredFrames": receiver.playback_buffer.delivered_frames,
            "playbackSilentFrames": receiver.playback_buffer.silent_frames,
            "playbackPrebufferMs": _frames_to_ms(receiver.playback_prebuffer_frames, 48000),
            "playbackMaxBufferMs": _frames_to_ms(receiver.playback_max_buffer_frames, 48000),
            "playbackDroppedRatio": _playback_dropped_ratio(receiver),
            "playbackOverflowDroppedFrames": receiver.playback_buffer.overflow_dropped_frames,
            "playbackCatchupDroppedFrames": receiver.playback_buffer.catchup_dropped_frames,
        }
    ok = bool(
        not errors
        and receiver.audio_packets_received > 0
        and _int_value(upstream.get("microphoneUpstreamPacketsSent")) > 0
        and upstream.get("microphoneUpstreamStatsFresh") is True
        and virtual_ready
        and (not receiver.loopback_capture or receiver.ordinary_apps_receive_audio_from_endpoint)
    )
    return WebRTCMicrophoneResult(
        ok=ok,
        command="webrtc_loopback_check" if loopback_capture else "webrtc_microphone",
        base_url=base_url,
        output_device=output_device,
        output_device_found=output_found,
        meeting_input_device_found=meeting_found,
        duration_seconds=duration_seconds,
        audio_packets_received=receiver.audio_packets_received,
        audio_bytes_received=receiver.audio_bytes_received,
        audio_frames_written=receiver.audio_frames_written,
        audio_buffer_ms=receiver.audio_buffer_ms,
        last_frame_age_ms=receiver.last_frame_age_ms(),
        receiver_state=receiver.receiver_state,
        virtual_microphone_ready=virtual_ready,
        normal_app_microphone_visible=normal_visible,
        loopback_enabled=receiver.loopback_capture,
        loopback_frame_count=receiver.loopback_frame_count,
        loopback_peak_abs=receiver.loopback_peak_abs,
        loopback_rms=receiver.loopback_rms,
        loopback_active_rms=receiver.loopback_active_rms,
        loopback_active_frame_count=receiver.loopback_active_frame_count,
        loopback_nonzero_samples=receiver.loopback_nonzero_samples,
        ordinary_apps_receive_audio_from_endpoint=receiver.ordinary_apps_receive_audio_from_endpoint,
        ipad_microphone_upstream_state=_str_or_none(upstream.get("microphoneUpstreamState")),
        ipad_microphone_upstream_packets_sent=_int_or_none(upstream.get("microphoneUpstreamPacketsSent")),
        ipad_microphone_upstream_bytes_sent=_int_or_none(upstream.get("microphoneUpstreamBytesSent")),
        ipad_microphone_upstream_stats_fresh=_bool_or_none(upstream.get("microphoneUpstreamStatsFresh")),
        ipad_microphone_upstream_stats_age_ms=_float_or_none(upstream.get("microphoneUpstreamStatsAgeMs")),
        windows_peer_connection_state=peer_connection_state or str(pc.connectionState),
        windows_ice_connection_state=ice_connection_state or str(pc.iceConnectionState),
        errors=errors,
        warnings=warnings,
        extra={
            "output_device_info": output,
            "meeting_input_device_info": meeting_input,
            "receiver_stats_posted": stats_posted,
            "start_audio": start_audio_result,
            "ipad_webrtc_status": final_status,
            "mode": "webrtc_opus_to_vbcable",
            "output_sample_rate_hz": receiver.output_sample_rate_hz,
            "output_channels": receiver.output_channels,
            "output_gain": receiver.output_gain,
            "low_cut_hz": receiver.low_cut_hz,
            "output_clipped_samples": receiver.output_clipped_samples,
            "output_limited_samples": receiver.output_limited_samples,
            "noise_gate_threshold": receiver.noise_gate_threshold,
            "noise_gate_frames": receiver.noise_gate_frames,
            "noise_gate_samples": receiver.noise_gate_samples,
            "playback_underflows": receiver.playback_underflows,
            "playback_dropped_frames": receiver.playback_dropped_frames,
            "receiver_peak_abs": receiver.receiver_peak_abs,
            "receiver_rms": receiver.receiver_rms,
            "output_peak_abs": receiver.output_peak_abs,
            "output_rms": receiver.output_rms,
            "quality": _quality_status(receiver, final_status),
            "diagnostic_captures": _diagnostic_capture_status(receiver),
            **receiver.extra_playback_stats,
            "notes": [
                "Receives iPad microphone over WebRTC/Opus and writes it to CABLE Input.",
                "Normal Windows apps should select CABLE Output as the microphone.",
                "Loopback capture records CABLE Output, the same direction ordinary meeting apps open.",
                "HTTP audio sample/chunk endpoints are diagnostic fallback only.",
            ],
        },
    )


def run_webrtc_microphone_receiver(**kwargs: Any) -> WebRTCMicrophoneResult:
    return asyncio.run(run_webrtc_microphone_receiver_async(**kwargs))


class _AudioReceiverState:
    def __init__(
        self,
        *,
        loopback_capture: bool = False,
        loopback_input_index: int | None = None,
        capture_path: str | None = None,
    ) -> None:
        self.audio_packets_received = 0
        self.audio_bytes_received = 0
        self.audio_frames_written = 0
        self.audio_buffer_ms = 0.0
        self.receiver_state = "waiting_for_track"
        self.output_stream: Any | None = None
        self.loopback_input_stream: Any | None = None
        self.loopback_capture = loopback_capture
        self.loopback_input_index = loopback_input_index
        self.diagnostic_capture_paths = _diagnostic_capture_paths(capture_path)
        self.diagnostic_capture_writers: dict[str, Any] = {}
        self.diagnostic_capture_frames: dict[str, int] = {"receiver_raw": 0, "processed": 0}
        self.loopback_frame_count = 0
        self.loopback_peak_abs: int | None = None
        self.loopback_rms: float | None = None
        self.loopback_active_rms: float | None = None
        self.loopback_active_frame_count = 0
        self.loopback_nonzero_samples = 0
        self.ordinary_apps_receive_audio_from_endpoint = False
        self._loopback_sum_squares = 0.0
        self._loopback_sample_count = 0
        self._loopback_active_sum_squares = 0.0
        self._loopback_active_sample_count = 0
        self.loopback_process: subprocess.Popen[str] | None = None
        self.output_sample_rate_hz: int | None = None
        self.output_channels: int | None = None
        self.output_gain = 1.0
        self.low_cut_hz = 80.0
        self._low_cut_previous_input: Any | None = None
        self._low_cut_previous_output: Any | None = None
        self.output_clipped_samples = 0
        self.output_limited_samples = 0
        self.noise_gate_threshold = 0.0
        self.noise_gate_attenuation = 0.15
        self.noise_gate_gain = 1.0
        self.noise_gate_frames = 0
        self.noise_gate_samples = 0
        self.playback_underflows = 0
        self.playback_dropped_frames = 0
        self.playback_buffer: _PlaybackBuffer | None = None
        self.playback_prebuffer_frames = 96000
        self.playback_max_buffer_frames = 240000
        self.receiver_peak_abs: int | None = None
        self.receiver_rms: float | None = None
        self._receiver_sum_squares = 0.0
        self._receiver_sample_count = 0
        self.output_peak_abs: int | None = None
        self.output_rms: float | None = None
        self._output_sum_squares = 0.0
        self._output_sample_count = 0
        self.extra_playback_stats: JsonDict = {}
        self._last_frame_at: float | None = None
        self.stopping = False

    def last_frame_age_ms(self) -> float | None:
        if self._last_frame_at is None:
            return None
        return round(max(0.0, (time.monotonic() - self._last_frame_at) * 1000.0), 3)


def _push_to_talk_allows_audio(state: _AudioReceiverState) -> bool:
    control_path = str(getattr(state, "push_to_talk_control_path", "") or "")
    if not control_path:
        return True

    default_allowed = not bool(getattr(state, "push_to_talk_default_muted", False))
    now = time.monotonic()
    last_check = float(getattr(state, "_push_to_talk_last_check_at", 0.0) or 0.0)
    if now - last_check < 0.05:
        return bool(getattr(state, "_push_to_talk_allowed", default_allowed))

    allowed = default_allowed
    try:
        text = Path(control_path).read_text(encoding="utf-8-sig").strip()
        if text:
            try:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    allowed = bool(payload.get("talking", payload.get("enabled", default_allowed)))
                else:
                    allowed = bool(payload)
            except json.JSONDecodeError:
                allowed = text.lower() in {"1", "true", "yes", "on", "talk", "talking", "unmuted"}
    except FileNotFoundError:
        allowed = default_allowed
    except Exception:
        allowed = default_allowed

    setattr(state, "_push_to_talk_last_check_at", now)
    setattr(state, "_push_to_talk_allowed", allowed)
    return allowed


def _apply_push_to_talk_gate(np: Any, samples: Any, state: _AudioReceiverState) -> Any:
    if _push_to_talk_allows_audio(state):
        setattr(state, "_push_to_talk_talking", True)
        return samples

    setattr(state, "_push_to_talk_talking", False)
    muted_frames = int(getattr(state, "_push_to_talk_muted_frames", 0) or 0)
    setattr(state, "_push_to_talk_muted_frames", muted_frames + int(samples.shape[0]))
    return np.zeros_like(samples)


async def _consume_audio_track(track: Any, state: _AudioReceiverState, sd: Any, np: Any, output_index: int, warnings: list[str]) -> None:
    stream = None
    resampler = None
    try:
        while not state.stopping:
            frame = await track.recv()
            if resampler is None:
                from av.audio.resampler import AudioResampler
                resampler = AudioResampler(format="s16", layout="stereo", rate=48000)
            for output_frame in resampler.resample(frame):
                samples, sample_rate_hz, channel_count = _audio_frame_to_s16le(np, output_frame)
                _record_receiver_samples(np, state, samples)
                _write_diagnostic_capture(np, state, "receiver_raw", samples)
                samples = _apply_low_cut_filter(np, samples, state, sample_rate_hz)
                samples = _apply_output_gain(np, samples, state)
                samples = _apply_noise_gate(np, samples, state)
                samples = _apply_push_to_talk_gate(np, samples, state)
                _record_output_samples(np, state, samples)
                _write_diagnostic_capture(np, state, "processed", samples)
                if state.playback_buffer is None:
                    state.playback_buffer = _PlaybackBuffer(
                        np,
                        channels=2,
                        max_frames=state.playback_max_buffer_frames,
                        target_frames=state.playback_prebuffer_frames,
                    )
                    state.output_sample_rate_hz = 48000
                    state.output_channels = 2
                state.playback_buffer.push(samples)
                if stream is None and state.playback_buffer.queued_frames >= state.playback_prebuffer_frames:
                    stream = sd.OutputStream(
                        samplerate=48000,
                        channels=2,
                        dtype="int16",
                        device=output_index,
                        blocksize=960,
                        latency=0.12,
                        callback=state.playback_buffer.callback,
                    )
                    stream.start()
                    state.output_stream = stream
                state.audio_frames_written += int(samples.shape[0])
                state.playback_underflows = state.playback_buffer.underflows
                state.playback_dropped_frames = state.playback_buffer.dropped_frames
                state.extra_playback_stats = {
                    "playbackCallbacks": state.playback_buffer.callbacks,
                    "playbackOutputDtype": state.playback_buffer.output_dtype,
                    "playbackSegmentPeakAbs": state.playback_buffer.last_segment_peak_abs,
                    "playbackUnderflowRatio": _playback_underflow_ratio(state),
                    "playbackUnderflowFrameRatio": _playback_underflow_frame_ratio(state),
                    "playbackRequestedFrames": state.playback_buffer.requested_frames,
                    "playbackDeliveredFrames": state.playback_buffer.delivered_frames,
                    "playbackSilentFrames": state.playback_buffer.silent_frames,
                    "playbackPrebufferMs": _frames_to_ms(state.playback_prebuffer_frames, 48000),
                    "playbackMaxBufferMs": _frames_to_ms(state.playback_max_buffer_frames, 48000),
                    "playbackDroppedRatio": _playback_dropped_ratio(state),
                    "playbackOverflowDroppedFrames": state.playback_buffer.overflow_dropped_frames,
                    "playbackCatchupDroppedFrames": state.playback_buffer.catchup_dropped_frames,
                    "pushToTalkEnabled": bool(getattr(state, "push_to_talk_control_path", "")),
                    "pushToTalkTalking": bool(getattr(state, "_push_to_talk_talking", True)),
                    "pushToTalkMutedFrames": int(getattr(state, "_push_to_talk_muted_frames", 0) or 0),
                }
                state.audio_buffer_ms = round((state.playback_buffer.queued_frames / float(sample_rate_hz)) * 1000.0, 3)
                state._last_frame_at = time.monotonic()
                state.receiver_state = "receiving_webrtc_opus"
    except Exception as exc:
        if not state.stopping:
            state.receiver_state = "error"
            message = str(exc)
            summary = f"{exc.__class__.__name__}: {message}" if message else f"{exc.__class__.__name__}: {exc!r}"
            warnings.append(f"audio track consume failed: {summary}")


class _PlaybackBuffer:
    def __init__(self, np: Any, *, channels: int, max_frames: int, target_frames: int | None = None) -> None:
        self.np = np
        self.channels = channels
        self.max_frames = max_frames
        self.target_frames = int(target_frames or max_frames)
        self._chunks: deque[Any] = deque()
        self._queued_frames = 0
        self._lock = threading.Lock()
        self.underflows = 0
        self.count_underflows = True
        self.dropped_frames = 0
        self.overflow_dropped_frames = 0
        self.catchup_dropped_frames = 0
        self.requested_frames = 0
        self.delivered_frames = 0
        self.silent_frames = 0
        self.callbacks = 0
        self.output_dtype: str | None = None
        self.last_segment_peak_abs: int | None = None

    @property
    def queued_frames(self) -> int:
        with self._lock:
            return int(self._queued_frames)

    def push(self, samples: Any) -> None:
        if samples is None or samples.size == 0:
            return
        if samples.shape[1] != self.channels:
            if samples.shape[1] == 1 and self.channels == 2:
                samples = self.np.repeat(samples, 2, axis=1)
            else:
                samples = samples[:, : self.channels]
        chunk = samples.astype(self.np.int16, copy=True)
        with self._lock:
            self._chunks.append(chunk)
            self._queued_frames += int(chunk.shape[0])
            overflow = self._queued_frames - self.max_frames
            if overflow > 0:
                dropped = self._discard_oldest_frames(overflow)
                self.overflow_dropped_frames += dropped
                self.dropped_frames += dropped

    def callback(self, outdata: Any, frames: int, time_info: Any, status: Any) -> None:
        del time_info, status
        count_stats = self.count_underflows
        if count_stats:
            self.callbacks += 1
            self.requested_frames += int(frames)
        self.output_dtype = str(outdata.dtype)
        outdata.fill(0)
        offset = 0
        with self._lock:
            while offset < frames and self._chunks:
                chunk = self._chunks[0]
                take = min(frames - offset, int(chunk.shape[0]))
                segment = chunk[:take, :]
                peak = int(self.np.max(self.np.abs(segment.astype(self.np.int32)))) if segment.size else 0
                self.last_segment_peak_abs = peak if self.last_segment_peak_abs is None else max(self.last_segment_peak_abs, peak)
                if getattr(outdata.dtype, "kind", "") == "f":
                    outdata[offset:offset + take, :] = segment.astype(self.np.float32) / 32768.0
                else:
                    outdata[offset:offset + take, :] = segment
                offset += take
                if take == int(chunk.shape[0]):
                    self._chunks.popleft()
                else:
                    self._chunks[0] = chunk[take:, :]
                self._queued_frames -= take
        if offset < frames:
            missing = int(frames - offset)
            if count_stats:
                self.silent_frames += missing
                self.underflows += 1
        if count_stats:
            self.delivered_frames += int(offset)

    def _discard_oldest_frames(self, frames: int) -> int:
        remaining = max(0, int(frames))
        dropped_total = 0
        while remaining > 0 and self._chunks:
            chunk = self._chunks[0]
            take = min(remaining, int(chunk.shape[0]))
            if take == int(chunk.shape[0]):
                self._chunks.popleft()
            else:
                self._chunks[0] = chunk[take:, :]
            self._queued_frames -= take
            dropped_total += take
            remaining -= take
        return dropped_total


class _InputCaptureBuffer:
    def __init__(self, np: Any) -> None:
        self.np = np
        self._chunks: deque[Any] = deque()
        self._lock = threading.Lock()
        self.overflow_count = 0

    def callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info
        chunk = indata.copy()
        if getattr(chunk.dtype, "kind", "") == "f":
            chunk = self.np.clip(chunk, -1.0, 1.0) * 32767.0
            chunk = self.np.rint(chunk).astype(self.np.int16)
        with self._lock:
            if status:
                self.overflow_count += 1
            self._chunks.append(chunk)

    def pop_all(self) -> list[Any]:
        with self._lock:
            chunks = list(self._chunks)
            self._chunks.clear()
        return chunks


def _diagnostic_capture_paths(capture_path: str | None) -> dict[str, str]:
    if not capture_path:
        return {}
    path = Path(capture_path)
    suffix = path.suffix or ".wav"
    stem_path = path.with_suffix("") if path.suffix else path
    return {
        "receiver_raw": str(stem_path.with_name(stem_path.name + "_receiver_raw").with_suffix(suffix)),
        "processed": str(stem_path.with_name(stem_path.name + "_processed").with_suffix(suffix)),
        "cable_output": str(stem_path.with_name(stem_path.name + "_cable_output").with_suffix(suffix)),
    }


def _write_diagnostic_capture(np: Any, state: _AudioReceiverState, layer: str, samples: Any) -> None:
    path = state.diagnostic_capture_paths.get(layer)
    if not path or samples is None or samples.size == 0:
        return
    audio = samples
    if audio.ndim == 1:
        audio = audio.reshape((-1, 1))
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    writer = state.diagnostic_capture_writers.get(layer)
    if writer is None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = wave.open(str(target), "wb")
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(48000)
        state.diagnostic_capture_writers[layer] = writer
    writer.writeframes(audio.astype(np.int16, copy=False).tobytes())
    state.diagnostic_capture_frames[layer] = int(state.diagnostic_capture_frames.get(layer, 0)) + int(audio.shape[0])


def _close_diagnostic_capture_writers(state: _AudioReceiverState, warnings: list[str]) -> None:
    for layer, writer in list(state.diagnostic_capture_writers.items()):
        try:
            writer.close()
        except Exception as exc:
            warnings.append(f"closing {layer} diagnostic capture: {exc}")
    state.diagnostic_capture_writers.clear()


def _merge_cable_capture_file_status(state: _AudioReceiverState, capture: JsonDict) -> None:
    path = capture.get("captureFile") or state.diagnostic_capture_paths.get("cable_output")
    if path:
        state.diagnostic_capture_paths["cable_output"] = str(path)
    frame_count = int(capture.get("recordedFrameCount") or capture.get("frameCount") or 0)
    if frame_count:
        state.diagnostic_capture_frames["cable_output"] = frame_count


def _diagnostic_capture_status(state: _AudioReceiverState) -> JsonDict:
    captures: JsonDict = {"enabled": bool(state.diagnostic_capture_paths)}
    if not state.diagnostic_capture_paths:
        return captures
    layers: JsonDict = {}
    for layer, path in state.diagnostic_capture_paths.items():
        target = Path(path)
        layers[layer] = {
            "path": str(target.resolve()) if target.exists() else str(target),
            "exists": target.exists(),
            "frames": int(state.diagnostic_capture_frames.get(layer, 0)),
        }
    captures["layers"] = layers
    captures["comparison"] = [
        "receiver_raw is decoded WebRTC/Opus before Windows filtering, gain, and VB-CABLE.",
        "processed is the PCM written toward CABLE Input after low-cut, gain, limiter, and gate.",
        "cable_output is what ordinary apps record from CABLE Output.",
    ]
    captures["qualityAttribution"] = _layered_quality_attribution(state)
    return captures


def _layered_quality_attribution(state: _AudioReceiverState) -> JsonDict:
    raw = _layer_level("receiver_raw", state.receiver_peak_abs, state.receiver_rms)
    processed = _layer_level("processed", state.output_peak_abs, state.output_rms)
    cable_rms = state.loopback_active_rms if state.loopback_active_rms is not None else state.loopback_rms
    cable = _layer_level("cable_output", state.loopback_peak_abs, cable_rms)
    raw_status = raw["levelState"]
    processed_status = processed["levelState"]
    cable_status = cable["levelState"]
    processed_minus_raw_db = _dbfs_delta(processed.get("rmsDbfs"), raw.get("rmsDbfs"))
    cable_minus_processed_db = _dbfs_delta(cable.get("rmsDbfs"), processed.get("rmsDbfs"))

    if raw_status == "silent":
        stage = "ipad_or_webrtc_silent"
        message = "No useful decoded WebRTC microphone PCM was observed; check the iPad microphone/WebRTC upstream first."
    elif raw_status == "low":
        stage = "ipad_source_too_quiet"
        message = "Decoded WebRTC microphone audio is already too quiet before Windows processing; improve iPad-side source level first."
    elif processed_status == "too_hot" or state.output_clipped_samples > 0 or state.output_limited_samples > 0:
        stage = "windows_processing_too_hot"
        message = "Windows processing is limiting or clipping peaks; lower Mic gain before judging VB-CABLE or Tencent Meeting."
    elif processed_minus_raw_db is not None and processed_minus_raw_db <= -6.0:
        stage = "windows_processing_loss"
        message = "Processed audio is much lower than decoded WebRTC audio; check low-cut, gain, and gate settings."
    elif state.loopback_capture and cable_status == "silent":
        stage = "cable_loopback_silent"
        message = "Audio reaches Windows processing, but CABLE Output capture is silent; check VB-CABLE routing and the meeting input direction."
    elif state.loopback_capture and cable_minus_processed_db is not None and cable_minus_processed_db <= -6.0:
        stage = "cable_loopback_loss"
        message = "CABLE Output is much lower than the PCM written toward CABLE Input; focus on VB-CABLE/ordinary-app capture."
    elif processed_status == "low" or (state.loopback_capture and cable_status == "low"):
        stage = "route_level_too_low"
        message = "The route carries audio, but the level reaching ordinary apps is still too low for meeting quality."
    else:
        stage = "audio_level_route_ok"
        message = "Layered levels do not show a major level loss; remaining quality issues are likely echo, noise, or source acoustics."

    return {
        "stage": stage,
        "message": message,
        "receiverRaw": raw,
        "processed": processed,
        "cableOutput": cable,
        "processedMinusRawRmsDb": processed_minus_raw_db,
        "cableMinusProcessedRmsDb": cable_minus_processed_db,
        "cableFullCaptureRmsDbfs": _dbfs(state.loopback_rms),
        "cableActiveRmsDbfs": _dbfs(state.loopback_active_rms),
        "cableActiveFrameCount": int(state.loopback_active_frame_count),
    }


def _layer_level(name: str, peak_abs: Any, rms: Any) -> JsonDict:
    status = _capture_level_status(peak_abs, rms)
    return {
        "name": name,
        "peakAbs": peak_abs,
        "rms": rms,
        "peakDbfs": _dbfs(peak_abs),
        "rmsDbfs": _dbfs(rms),
        "levelState": status["levelState"],
        "primaryIssue": status["primaryIssue"],
        "recommendedSourceLiftDb": status["recommendedSourceLiftDb"],
    }


def _dbfs_delta(left_dbfs: Any, right_dbfs: Any) -> float | None:
    try:
        if left_dbfs is None or right_dbfs is None:
            return None
        return round(float(left_dbfs) - float(right_dbfs), 2)
    except (TypeError, ValueError):
        return None


def _start_loopback_capture_process(state: _AudioReceiverState, duration_seconds: float) -> None:
    bridge_py = Path(__file__).resolve().parents[1] / "bridge.py"
    capture_duration = max(3.0, float(duration_seconds if duration_seconds > 0 else 8.0) + 2.0)
    args = [
        sys.executable,
        str(bridge_py),
        "--duration-seconds",
        str(round(capture_duration, 3)),
    ]
    cable_capture_path = state.diagnostic_capture_paths.get("cable_output")
    if cable_capture_path:
        args.extend(["--capture-path", cable_capture_path])
    args.append("vbcable-output-capture")
    state.loopback_process = subprocess.Popen(
        args,
        cwd=str(bridge_py.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _finish_loopback_capture_process(state: _AudioReceiverState, warnings: list[str]) -> None:
    process = state.loopback_process
    if process is None:
        return
    try:
        stdout, stderr = process.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=5.0)
        warnings.append("CABLE Output loopback capture timed out.")
    if stderr.strip():
        warnings.append(f"CABLE Output loopback capture stderr: {stderr.strip()}")
    if process.returncode != 0:
        warnings.append(f"CABLE Output loopback capture exited with {process.returncode}.")
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except Exception as exc:
        warnings.append(f"CABLE Output loopback capture returned invalid JSON: {exc}")
        return
    capture = payload.get("capture", payload)
    state.loopback_frame_count = int(capture.get("recordedFrameCount") or capture.get("frameCount") or 0)
    state.loopback_peak_abs = _int_or_none(capture.get("peakAbs"))
    state.loopback_rms = _float_or_none(capture.get("rms"))
    state.loopback_active_rms = _float_or_none(capture.get("activeRms"))
    state.loopback_active_frame_count = int(capture.get("activeFrameCount") or 0)
    state.loopback_nonzero_samples = int(capture.get("nonzeroSamples") or 0)
    state.ordinary_apps_receive_audio_from_endpoint = bool(capture.get("ordinaryAppsReceiveAudioFromEndpoint") or payload.get("ok"))
    _merge_cable_capture_file_status(state, capture)


def capture_vbcable_output(
    duration_seconds: float = 5.0,
    meeting_input_device: str = DEFAULT_MEETING_INPUT_DEVICE,
    capture_path: str | None = None,
    monitor_gain: float = 1.0,
) -> JsonDict:
    backend = _load_audio_backend()
    if not backend["ok"]:
        return {"ok": False, "command": "vbcable_output_capture", "errors": [backend["error"]["message"]]}
    sd = backend["sounddevice"]
    np = backend["numpy"]
    devices = _device_list(sd)
    meeting_input = _find_device(devices, meeting_input_device, is_input=True)
    if meeting_input is None:
        return {
            "ok": False,
            "command": "vbcable_output_capture",
            "meeting_input_device": meeting_input_device,
            "meeting_input_device_found": False,
            "capture": {
                "ordinaryAppsReceiveAudioFromEndpoint": False,
                "recordedFrameCount": 0,
                "peakAbs": None,
                "rms": None,
                "peakDbfs": None,
                "rmsDbfs": None,
                "nonzeroSamples": 0,
                **_capture_level_status(None, None),
            },
            "errors": [f"VB-CABLE recording device not found: {meeting_input_device}"],
        }

    sample_rate_hz = int(float(meeting_input.get("default_samplerate") or 48000))
    channels = max(1, min(2, int(meeting_input.get("max_input_channels") or 1)))
    deadline = time.monotonic() + max(0.25, float(duration_seconds))
    state = _AudioReceiverState()
    errors: list[str] = []
    warnings: list[str] = []
    chunks: list[Any] = []
    stream = None
    capture_buffer = _InputCaptureBuffer(np)
    try:
        stream = sd.InputStream(
            samplerate=sample_rate_hz,
            channels=channels,
            dtype="int16",
            device=int(meeting_input["index"]),
            blocksize=max(240, int(sample_rate_hz * 0.01)),
            latency=0.05,
            callback=capture_buffer.callback,
        )
        stream.start()
        while time.monotonic() < deadline:
            time.sleep(0.05)
            for recorded in capture_buffer.pop_all():
                _record_loopback_samples(np, state, recorded)
                if capture_path:
                    chunks.append(recorded)
        for recorded in capture_buffer.pop_all():
            _record_loopback_samples(np, state, recorded)
            if capture_path:
                chunks.append(recorded)
        if capture_buffer.overflow_count:
            warnings.append(f"CABLE Output capture input stream reported {capture_buffer.overflow_count} callback status events.")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                warnings.append(f"closing CABLE Output capture stream: {exc}")

    file_info: JsonDict = {}
    if capture_path and chunks and not errors:
        try:
            file_info = _write_capture_files(
                np,
                chunks,
                sample_rate_hz=sample_rate_hz,
                channels=channels,
                capture_path=capture_path,
                monitor_gain=monitor_gain,
            )
        except Exception as exc:
            errors.append(f"writing capture WAV: {exc}")

    return {
        "ok": bool(not errors and state.ordinary_apps_receive_audio_from_endpoint),
        "command": "vbcable_output_capture",
        "changes_system": False,
        "meeting_input_device": meeting_input_device,
        "meeting_input_device_found": True,
        "duration_seconds": duration_seconds,
        "sampleRateHz": sample_rate_hz,
        "channels": channels,
        "capture": {
            "ordinaryAppsReceiveAudioFromEndpoint": state.ordinary_apps_receive_audio_from_endpoint,
            "recordedFrameCount": state.loopback_frame_count,
            "peakAbs": state.loopback_peak_abs,
            "rms": state.loopback_rms,
            "activeRms": state.loopback_active_rms,
            "peakDbfs": _dbfs(state.loopback_peak_abs),
            "rmsDbfs": _dbfs(state.loopback_rms),
            "activeRmsDbfs": _dbfs(state.loopback_active_rms),
            "activeFrameCount": state.loopback_active_frame_count,
            "nonzeroSamples": state.loopback_nonzero_samples,
            **_capture_level_status(state.loopback_peak_abs, state.loopback_active_rms if state.loopback_active_rms is not None else state.loopback_rms),
            **file_info,
        },
        "errors": errors,
        "warnings": warnings,
    }


def record_vbcable_output_until_stop(
    *,
    stop_file: str,
    capture_path: str,
    meeting_input_device: str = DEFAULT_MEETING_INPUT_DEVICE,
    monitor_gain: float = 1.0,
    tail_seconds: float = 0.0,
) -> JsonDict:
    backend = _load_audio_backend()
    if not backend["ok"]:
        return {"ok": False, "command": "vbcable_output_record", "errors": [backend["error"]["message"]]}
    sd = backend["sounddevice"]
    np = backend["numpy"]
    devices = _device_list(sd)
    meeting_input = _find_device(devices, meeting_input_device, is_input=True)
    if meeting_input is None:
        return {
            "ok": False,
            "command": "vbcable_output_record",
            "meeting_input_device": meeting_input_device,
            "meeting_input_device_found": False,
            "errors": [f"VB-CABLE recording device not found: {meeting_input_device}"],
        }

    stop_path = Path(stop_file)
    capture = Path(capture_path)
    capture.parent.mkdir(parents=True, exist_ok=True)
    if stop_path.exists():
        stop_path.unlink()

    sample_rate_hz = int(float(meeting_input.get("default_samplerate") or 48000))
    channels = max(1, min(2, int(meeting_input.get("max_input_channels") or 1)))
    state = _AudioReceiverState()
    errors: list[str] = []
    warnings: list[str] = []
    stream = None
    capture_buffer = _InputCaptureBuffer(np)
    started_at = time.monotonic()
    stop_seen_at: float | None = None
    try:
        stream = sd.InputStream(
            samplerate=sample_rate_hz,
            channels=channels,
            dtype="int16",
            device=int(meeting_input["index"]),
            blocksize=max(240, int(sample_rate_hz * 0.01)),
            latency=0.05,
            callback=capture_buffer.callback,
        )
        stream.start()
        with wave.open(str(capture), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate_hz)
            while True:
                for recorded in capture_buffer.pop_all():
                    _record_loopback_samples(np, state, recorded)
                    handle.writeframes(recorded.astype(np.int16, copy=False).tobytes())
                if stop_path.exists() and stop_seen_at is None:
                    stop_seen_at = time.monotonic()
                if stop_seen_at is not None and time.monotonic() - stop_seen_at >= max(0.0, float(tail_seconds)):
                    break
                time.sleep(0.03)
            for recorded in capture_buffer.pop_all():
                _record_loopback_samples(np, state, recorded)
                handle.writeframes(recorded.astype(np.int16, copy=False).tobytes())
        if capture_buffer.overflow_count:
            warnings.append(f"CABLE Output record input stream reported {capture_buffer.overflow_count} callback status events.")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                warnings.append(f"closing CABLE Output record stream: {exc}")

    file_info: JsonDict = {}
    if capture.exists() and not errors:
        try:
            file_info = _create_monitor_file_from_wav(np, capture, monitor_gain)
        except Exception as exc:
            errors.append(f"writing monitor WAV: {exc}")

    return {
        "ok": bool(not errors and capture.exists()),
        "command": "vbcable_output_record",
        "changes_system": False,
        "meeting_input_device": meeting_input_device,
        "meeting_input_device_found": True,
        "duration_seconds": round(time.monotonic() - started_at, 3),
        "tail_seconds": max(0.0, float(tail_seconds)),
        "sampleRateHz": sample_rate_hz,
        "channels": channels,
        "capture": {
            "ordinaryAppsReceiveAudioFromEndpoint": state.ordinary_apps_receive_audio_from_endpoint,
            "recordedFrameCount": state.loopback_frame_count,
            "peakAbs": state.loopback_peak_abs,
            "rms": state.loopback_rms,
            "activeRms": state.loopback_active_rms,
            "peakDbfs": _dbfs(state.loopback_peak_abs),
            "rmsDbfs": _dbfs(state.loopback_rms),
            "activeRmsDbfs": _dbfs(state.loopback_active_rms),
            "activeFrameCount": state.loopback_active_frame_count,
            "nonzeroSamples": state.loopback_nonzero_samples,
            **_capture_level_status(state.loopback_peak_abs, state.loopback_active_rms if state.loopback_active_rms is not None else state.loopback_rms),
            "captureFile": str(capture.resolve()),
            "playbackFile": str(capture.resolve()),
            "monitorGain": 1.0,
            "monitorPeakDbfs": None,
            "monitorRmsDbfs": None,
            "monitorClippedSamples": 0,
            "monitorClippedRatio": 0.0,
            "monitorClipped": False,
            **file_info,
        },
        "errors": errors,
        "warnings": warnings,
    }


def _write_capture_files(
    np: Any,
    chunks: list[Any],
    *,
    sample_rate_hz: int,
    channels: int,
    capture_path: str,
    monitor_gain: float,
) -> JsonDict:
    audio = np.concatenate(chunks, axis=0).astype(np.int16, copy=False)
    path = Path(capture_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(path, audio, sample_rate_hz, channels)

    result: JsonDict = {
        "captureFile": str(path.resolve()),
        "playbackFile": str(path.resolve()),
        "monitorGain": 1.0,
        "monitorPeakDbfs": None,
        "monitorRmsDbfs": None,
        "monitorClippedSamples": 0,
        "monitorClippedRatio": 0.0,
        "monitorClipped": False,
    }
    gain = float(monitor_gain or 1.0)
    if gain > 1.0:
        boosted = np.clip(audio.astype(np.float64) * gain, -32768, 32767).astype(np.int16)
        monitor_path = path.with_name(path.stem + f"_monitor_x{gain:g}" + path.suffix)
        _write_wav(monitor_path, boosted, sample_rate_hz, channels)
        result["playbackFile"] = str(monitor_path.resolve())
        result["monitorFile"] = str(monitor_path.resolve())
        result["monitorGain"] = gain
        result["monitorPeakAbs"] = int(np.max(np.abs(boosted.astype(np.int32)))) if boosted.size else 0
        result["monitorRms"] = round(float(np.sqrt(np.mean(boosted.astype(np.float64) ** 2))), 3) if boosted.size else 0.0
        result["monitorPeakDbfs"] = _dbfs(result["monitorPeakAbs"])
        result["monitorRmsDbfs"] = _dbfs(result["monitorRms"])
        monitor_clipped = int(np.count_nonzero(np.abs(boosted.astype(np.int32)) >= 32760))
        result["monitorClippedSamples"] = monitor_clipped
        result["monitorClippedRatio"] = _sample_ratio(monitor_clipped, int(boosted.size))
        result["monitorClipped"] = monitor_clipped > 0
    return result


def _write_wav(path: Path, audio: Any, sample_rate_hz: int, channels: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(audio.tobytes())


def _create_monitor_file_from_wav(np: Any, path: Path, monitor_gain: float) -> JsonDict:
    gain = float(monitor_gain or 1.0)
    if gain <= 1.0:
        return {}
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_rate_hz = source.getframerate()
        raw = source.readframes(source.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16)
    if channels > 0:
        audio = audio.reshape((-1, channels))
    boosted = np.clip(audio.astype(np.float64) * gain, -32768, 32767).astype(np.int16)
    monitor_path = path.with_name(path.stem + f"_monitor_x{gain:g}" + path.suffix)
    _write_wav(monitor_path, boosted, sample_rate_hz, channels)
    monitor_clipped = int(np.count_nonzero(np.abs(boosted.astype(np.int32)) >= 32760))
    return {
        "playbackFile": str(monitor_path.resolve()),
        "monitorFile": str(monitor_path.resolve()),
        "monitorGain": gain,
        "monitorPeakAbs": int(np.max(np.abs(boosted.astype(np.int32)))) if boosted.size else 0,
        "monitorRms": round(float(np.sqrt(np.mean(boosted.astype(np.float64) ** 2))), 3) if boosted.size else 0.0,
        "monitorPeakDbfs": _dbfs(int(np.max(np.abs(boosted.astype(np.int32)))) if boosted.size else 0),
        "monitorRmsDbfs": _dbfs(round(float(np.sqrt(np.mean(boosted.astype(np.float64) ** 2))), 3) if boosted.size else 0.0),
        "monitorClippedSamples": monitor_clipped,
        "monitorClippedRatio": _sample_ratio(monitor_clipped, int(boosted.size)),
        "monitorClipped": monitor_clipped > 0,
    }


def _sample_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(min(1.0, max(0.0, int(count) / float(total))), 6)


def _dbfs(value: Any) -> float | None:
    try:
        amplitude = float(value)
    except (TypeError, ValueError):
        return None
    if amplitude <= 0.0:
        return None
    return round(20.0 * math.log10(min(amplitude, 32768.0) / 32768.0), 2)


def _db_gap(current_dbfs: float | None, target_dbfs: float | None) -> float:
    if current_dbfs is None or target_dbfs is None:
        return 0.0
    return round(max(0.0, float(target_dbfs) - float(current_dbfs)), 2)


def _capture_level_status(peak_abs: Any, rms: Any) -> JsonDict:
    peak = float(peak_abs or 0.0)
    rms_value = float(rms or 0.0)
    rms_dbfs = _dbfs(rms_value)
    target_rms = 300.0
    target_rms_dbfs = _dbfs(target_rms)
    sustained_too_quiet = bool(rms_value > 0.0 and rms_value < 80.0 and peak < 1500.0)
    if peak <= 0.0:
        level_state = "silent"
        primary_issue = "silent"
    elif sustained_too_quiet:
        level_state = "low"
        primary_issue = "source_too_quiet"
    elif peak > 26000.0:
        level_state = "too_hot"
        primary_issue = "level_too_hot"
    else:
        level_state = "ok"
        primary_issue = "none"
    return {
        "levelState": level_state,
        "primaryIssue": primary_issue,
        "sustainedOutputTooQuiet": sustained_too_quiet,
        "targetSustainedRms": target_rms,
        "targetSustainedRmsDbfs": target_rms_dbfs,
        "recommendedSourceLiftDb": _db_gap(rms_dbfs, target_rms_dbfs) if sustained_too_quiet else 0.0,
    }


def _audio_frame_to_s16le(np: Any, frame: Any) -> tuple[Any, int, int]:
    sample_rate_hz = int(getattr(frame, "sample_rate", None) or 48000)
    frame_samples = int(getattr(frame, "samples", 0) or 0)
    channel_count = _audio_frame_channel_count(frame)
    array = frame.to_ndarray()
    if array.ndim == 1:
        if channel_count > 1 and array.size % channel_count == 0:
            samples = array.reshape((-1, channel_count))
        else:
            samples = array.reshape((-1, 1))
    else:
        samples = _reshape_audio_ndarray(np, array, channel_count, frame_samples)
    if samples.dtype != np.int16:
        if samples.dtype.kind == "f":
            samples = np.clip(samples, -1.0, 1.0) * 32767.0
        samples = np.clip(np.rint(samples), -32768, 32767).astype(np.int16)
    else:
        samples = samples.astype(np.int16, copy=False)
    if samples.ndim == 1:
        samples = samples.reshape((-1, 1))
    return samples, sample_rate_hz, int(samples.shape[1])


def _audio_frame_channel_count(frame: Any) -> int:
    layout = getattr(frame, "layout", None)
    channels = getattr(layout, "channels", None)
    try:
        count = len(channels)
    except Exception:
        count = int(getattr(frame, "channels", 0) or 0)
    return max(1, count)


def _reshape_audio_ndarray(np: Any, array: Any, channel_count: int, frame_samples: int) -> Any:
    # PyAV may return planar audio as (channels, samples) and packed audio as
    # (1, samples * channels). Preserve interleaving instead of blindly transposing.
    if array.shape[0] == channel_count and (frame_samples <= 0 or array.shape[1] == frame_samples):
        return array.T
    if array.shape[0] == 1 and channel_count > 1 and array.shape[1] % channel_count == 0:
        return array.reshape((-1, channel_count))
    if array.shape[1] == channel_count:
        return array
    if frame_samples > 0 and array.size == frame_samples * channel_count:
        return array.reshape((frame_samples, channel_count))
    if array.shape[0] == 1:
        return array.reshape((-1, 1))
    return np.ascontiguousarray(array.T)


def _record_loopback_samples(np: Any, state: _AudioReceiverState, samples: Any) -> None:
    if samples is None or samples.size == 0:
        return
    values = samples.astype(np.float64)
    peak = int(np.max(np.abs(values)))
    state.loopback_peak_abs = peak if state.loopback_peak_abs is None else max(state.loopback_peak_abs, peak)
    state.loopback_nonzero_samples += int(np.count_nonzero(samples))
    state.loopback_frame_count += int(samples.shape[0])
    state._loopback_sum_squares += float(np.sum(np.square(values)))
    state._loopback_sample_count += int(values.size)
    if state._loopback_sample_count:
        state.loopback_rms = round(math.sqrt(state._loopback_sum_squares / state._loopback_sample_count), 3)
    block_rms = math.sqrt(float(np.mean(np.square(values)))) if values.size else 0.0
    if peak >= 20 or block_rms >= 8.0:
        state._loopback_active_sum_squares += float(np.sum(np.square(values)))
        state._loopback_active_sample_count += int(values.size)
        state.loopback_active_frame_count += int(samples.shape[0])
        state.loopback_active_rms = round(math.sqrt(state._loopback_active_sum_squares / state._loopback_active_sample_count), 3)
    state.ordinary_apps_receive_audio_from_endpoint = bool(
        state.loopback_frame_count > 0
        and state.loopback_nonzero_samples > 0
        and state.loopback_peak_abs is not None
        and state.loopback_peak_abs > 0
    )


def _record_receiver_samples(np: Any, state: _AudioReceiverState, samples: Any) -> None:
    if samples is None or samples.size == 0:
        return
    values = samples.astype(np.float64)
    peak = int(np.max(np.abs(values)))
    state.receiver_peak_abs = peak if state.receiver_peak_abs is None else max(state.receiver_peak_abs, peak)
    state._receiver_sum_squares += float(np.sum(np.square(values)))
    state._receiver_sample_count += int(values.size)
    if state._receiver_sample_count:
        state.receiver_rms = round(math.sqrt(state._receiver_sum_squares / state._receiver_sample_count), 3)


def _record_output_samples(np: Any, state: _AudioReceiverState, samples: Any) -> None:
    if samples is None or samples.size == 0:
        return
    values = samples.astype(np.float64)
    peak = int(np.max(np.abs(values)))
    state.output_peak_abs = peak if state.output_peak_abs is None else max(state.output_peak_abs, peak)
    state._output_sum_squares += float(np.sum(np.square(values)))
    state._output_sample_count += int(values.size)
    if state._output_sample_count:
        state.output_rms = round(math.sqrt(state._output_sum_squares / state._output_sample_count), 3)


def _apply_low_cut_filter(np: Any, samples: Any, state: _AudioReceiverState, sample_rate_hz: int) -> Any:
    cutoff = float(state.low_cut_hz or 0.0)
    if cutoff <= 0.0 or samples is None or samples.size == 0:
        return samples
    sample_rate = max(1.0, float(sample_rate_hz or 48000))
    channels = int(samples.shape[1]) if getattr(samples, "ndim", 1) > 1 else 1
    values = samples.astype(np.float64, copy=False)
    if values.ndim == 1:
        values = values.reshape((-1, 1))
    if state._low_cut_previous_input is None or len(state._low_cut_previous_input) != channels:
        state._low_cut_previous_input = np.zeros(channels, dtype=np.float64)
        state._low_cut_previous_output = np.zeros(channels, dtype=np.float64)
    previous_input = state._low_cut_previous_input
    previous_output = state._low_cut_previous_output
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    filtered = np.empty_like(values, dtype=np.float64)
    for index in range(values.shape[0]):
        current = values[index]
        output = alpha * (previous_output + current - previous_input)
        filtered[index] = output
        previous_input = current
        previous_output = output
    state._low_cut_previous_input = previous_input.copy()
    state._low_cut_previous_output = previous_output.copy()
    return np.clip(np.rint(filtered), -32768, 32767).astype(np.int16)


def _apply_output_gain(np: Any, samples: Any, state: _AudioReceiverState) -> Any:
    gain = float(state.output_gain or 1.0)
    if abs(gain - 1.0) < 0.001:
        return samples
    scaled = samples.astype(np.float64) * gain
    clipped = np.count_nonzero((scaled > 32767.0) | (scaled < -32768.0))
    if clipped:
        state.output_clipped_samples += int(clipped)
    limited = _soft_limit_int16(np, scaled, state)
    return np.clip(np.rint(limited), -32768, 32767).astype(np.int16)


def _soft_limit_int16(np: Any, scaled: Any, state: _AudioReceiverState) -> Any:
    knee = 28000.0
    limit = 32767.0
    values = scaled.astype(np.float64, copy=False)
    abs_values = np.abs(values)
    over_knee = abs_values > knee
    limited_samples = int(np.count_nonzero(over_knee))
    if limited_samples <= 0:
        return values
    state.output_limited_samples += limited_samples
    headroom = limit - knee
    compressed_abs = knee + headroom * np.tanh((abs_values - knee) / headroom)
    return np.where(over_knee, np.sign(values) * compressed_abs, values)


def _apply_noise_gate(np: Any, samples: Any, state: _AudioReceiverState) -> Any:
    threshold = float(state.noise_gate_threshold or 0.0)
    if threshold <= 0.0 or samples is None or samples.size == 0:
        return samples
    values = samples.astype(np.float64)
    rms = math.sqrt(float(np.mean(values * values))) if values.size else 0.0
    if rms >= threshold:
        state.noise_gate_gain = 1.0
        return samples
    state.noise_gate_frames += 1
    state.noise_gate_samples += int(samples.shape[0])
    attenuation = float(state.noise_gate_attenuation)
    release = 0.25
    state.noise_gate_gain += (attenuation - state.noise_gate_gain) * release
    state.noise_gate_gain = max(attenuation, min(1.0, state.noise_gate_gain))
    attenuated = values * state.noise_gate_gain
    return np.clip(np.rint(attenuated), -32768, 32767).astype(np.int16)


def _receiver_stats_payload(state: _AudioReceiverState, virtual_ready: bool, normal_visible: bool, pc: Any) -> JsonDict:
    return {
        "receiverState": state.receiver_state,
        "audioPacketsReceived": int(state.audio_packets_received),
        "audioBytesReceived": int(state.audio_bytes_received),
        "audioFramesWritten": int(state.audio_frames_written),
        "audioBufferMs": float(state.audio_buffer_ms),
        "lastFrameAgeMs": state.last_frame_age_ms(),
        "virtualMicrophoneReady": bool(virtual_ready),
        "normalAppMicrophoneVisible": bool(normal_visible),
        "ordinaryAppsReceiveAudioFromEndpoint": bool(state.ordinary_apps_receive_audio_from_endpoint),
        "loopbackPeakAbs": state.loopback_peak_abs,
        "loopbackRms": state.loopback_rms,
        "loopbackPeakDbfs": _dbfs(state.loopback_peak_abs),
        "loopbackRmsDbfs": _dbfs(state.loopback_rms),
        "loopbackLevelState": _capture_level_status(state.loopback_peak_abs, state.loopback_rms)["levelState"],
        "loopbackPrimaryIssue": _capture_level_status(state.loopback_peak_abs, state.loopback_rms)["primaryIssue"],
        "loopbackRecommendedSourceLiftDb": _capture_level_status(state.loopback_peak_abs, state.loopback_rms)["recommendedSourceLiftDb"],
        "loopbackFrameCount": int(state.loopback_frame_count),
        "playbackUnderflows": int(state.playback_underflows),
        "playbackDroppedFrames": int(state.playback_dropped_frames),
        "playbackOverflowDroppedFrames": int(state.playback_buffer.overflow_dropped_frames) if state.playback_buffer is not None else 0,
        "playbackCatchupDroppedFrames": int(state.playback_buffer.catchup_dropped_frames) if state.playback_buffer is not None else 0,
        "playbackUnderflowRatio": _playback_underflow_ratio(state),
        "playbackUnderflowFrameRatio": _playback_underflow_frame_ratio(state),
        "playbackRequestedFrames": int(state.playback_buffer.requested_frames) if state.playback_buffer is not None else 0,
        "playbackDeliveredFrames": int(state.playback_buffer.delivered_frames) if state.playback_buffer is not None else 0,
        "playbackSilentFrames": int(state.playback_buffer.silent_frames) if state.playback_buffer is not None else 0,
        "playbackPrebufferMs": _frames_to_ms(state.playback_prebuffer_frames, 48000),
        "playbackMaxBufferMs": _frames_to_ms(state.playback_max_buffer_frames, 48000),
        "playbackDroppedRatio": _playback_dropped_ratio(state),
        "receiverPeakAbs": state.receiver_peak_abs,
        "receiverRms": state.receiver_rms,
        "receiverPeakDbfs": _dbfs(state.receiver_peak_abs),
        "receiverRmsDbfs": _dbfs(state.receiver_rms),
        "outputPeakAbs": state.output_peak_abs,
        "outputRms": state.output_rms,
        "outputPeakDbfs": _dbfs(state.output_peak_abs),
        "outputRmsDbfs": _dbfs(state.output_rms),
        "outputGain": float(state.output_gain),
        "lowCutHz": float(state.low_cut_hz),
        "outputClippedSamples": int(state.output_clipped_samples),
        "outputLimitedSamples": int(state.output_limited_samples),
        "noiseGateThreshold": float(state.noise_gate_threshold),
        "noiseGateGain": round(float(state.noise_gate_gain), 4),
        "noiseGateFrames": int(state.noise_gate_frames),
        "noiseGateSamples": int(state.noise_gate_samples),
        "peerConnectionState": str(pc.connectionState),
        "iceConnectionState": str(pc.iceConnectionState),
        "message": "Windows received iPad microphone over WebRTC/Opus and wrote audio to VB-CABLE.",
    }


def _playback_underflow_ratio(state: _AudioReceiverState) -> float:
    callbacks = int(state.playback_buffer.callbacks) if state.playback_buffer is not None else 0
    if callbacks <= 0:
        return 0.0
    return round(min(1.0, max(0.0, state.playback_underflows / float(callbacks))), 4)


def _playback_underflow_frame_ratio(state: _AudioReceiverState) -> float:
    requested = int(state.playback_buffer.requested_frames) if state.playback_buffer is not None else 0
    silent = int(state.playback_buffer.silent_frames) if state.playback_buffer is not None else 0
    if requested <= 0:
        return 0.0
    return round(min(1.0, max(0.0, silent / float(requested))), 4)


def _ms_to_frames(milliseconds: float, sample_rate_hz: int, *, minimum: int, maximum: int) -> int:
    raw = int(round((float(milliseconds or 0.0) / 1000.0) * float(sample_rate_hz or 48000)))
    return max(int(minimum), min(int(maximum), raw))


def _frames_to_ms(frames: int, sample_rate_hz: int) -> float:
    if sample_rate_hz <= 0:
        return 0.0
    return round((float(frames) / float(sample_rate_hz)) * 1000.0, 3)


def _playback_dropped_ratio(state: _AudioReceiverState) -> float:
    written = int(state.audio_frames_written)
    dropped = int(state.playback_dropped_frames)
    total = written + dropped
    if total <= 0:
        return 0.0
    return round(min(1.0, max(0.0, dropped / float(total))), 4)


def _quality_status(state: _AudioReceiverState, ipad_status: JsonDict) -> JsonDict:
    input_peak = int(state.receiver_peak_abs or 0)
    output_peak = int(state.output_peak_abs if state.output_peak_abs is not None else input_peak)
    output_rms = float(state.output_rms or 0.0)
    clipped = int(state.output_clipped_samples)
    limited = int(state.output_limited_samples)
    underflows = int(state.playback_underflows)
    dropped = int(state.playback_dropped_frames)
    underflow_ratio = _playback_underflow_ratio(state)
    underflow_frame_ratio = _playback_underflow_frame_ratio(state)
    dropped_ratio = _playback_dropped_ratio(state)
    overflow_dropped = int(state.playback_buffer.overflow_dropped_frames) if state.playback_buffer is not None else 0
    output_gain = float(state.output_gain or 1.0)
    target_sustained_rms_abs = 300.0
    target_sustained_rms_dbfs = _dbfs(target_sustained_rms_abs)
    output_rms_dbfs = _dbfs(output_rms)
    estimated_output_peak = output_peak
    suggested_gain = _suggest_mic_gain(output_peak, output_gain, clipped)
    suggested_gain_step = _suggest_mic_gain_step(output_gain, suggested_gain)
    suggested_monitor_gain = _suggest_monitor_gain(output_peak)
    estimated_next_gain_peak = _estimate_peak_after_gain_step(output_peak, output_gain, suggested_gain_step)
    estimated_next_gain_rms = _estimate_peak_after_gain_step(int(round(output_rms)), output_gain, suggested_gain_step)
    estimated_safe_gain_peak = _estimate_peak_after_gain_step(output_peak, output_gain, suggested_gain)
    estimated_safe_gain_rms = _estimate_peak_after_gain_step(int(round(output_rms)), output_gain, suggested_gain)
    peak_too_quiet_for_gain_only = bool(output_peak > 0 and output_peak < 500 and suggested_gain_step >= 3.0 and estimated_next_gain_peak < 500)
    sustained_too_quiet_for_gain_only = bool(
        output_rms > 0.0
        and output_rms < 80.0
        and output_peak < 1500
        and suggested_gain_step >= 3.0
        and estimated_next_gain_rms < 120
    )
    source_too_quiet = bool(peak_too_quiet_for_gain_only or sustained_too_quiet_for_gain_only)
    gain_only_likely_to_amplify_noise = bool(source_too_quiet)
    gain_risk_message = (
        "Windows gain is likely to amplify room noise and acoustic echo more than useful speech; improve the iPad-side source level first."
        if gain_only_likely_to_amplify_noise
        else "Modest Windows gain may help, but source placement is still preferred."
    )
    recommended_source_lift_db = _db_gap(output_rms_dbfs, target_sustained_rms_dbfs) if source_too_quiet else 0.0
    gain_safety = _gain_safety_status(
        current_gain=output_gain,
        suggested_gain=suggested_gain,
        suggested_gain_step=suggested_gain_step,
        clipped=clipped,
        limited=limited,
        source_too_quiet=source_too_quiet,
        estimated_safe_gain_peak=estimated_safe_gain_peak,
        estimated_safe_gain_rms=estimated_safe_gain_rms,
        target_sustained_rms_abs=target_sustained_rms_abs,
    )
    latency_ms = float(state.audio_buffer_ms or 0.0)
    gate_ratio = 0.0
    if state.audio_frames_written > 0:
        gate_ratio = round(min(1.0, state.noise_gate_samples / float(state.audio_frames_written)), 4)
    voice_processing = _first_present(
        ipad_status,
        "voiceProcessingEnabled",
        "microphoneVoiceProcessingEnabled",
        "audioVoiceProcessingEnabled",
        "aecEnabled",
        "echoCancellationEnabled",
    )
    if voice_processing is True:
        echo_state = "verified"
        echo_message = "iPad reports voice processing/AEC enabled."
        echo_risk_state = "controlled"
        echo_risk_message = "Echo risk is controlled by reported iPad voice processing/AEC."
    elif voice_processing is False:
        echo_state = "disabled"
        echo_message = "iPad reports voice processing/AEC disabled; echo is likely if iPad speaker is active."
        echo_risk_state = "high"
        echo_risk_message = "Echo risk is high if iPad speaker audio can reach the iPad microphone."
    else:
        echo_state = "unverified"
        echo_message = "iPad status does not expose voice processing/AEC evidence."
        echo_risk_state = "unknown"
        echo_risk_message = "Echo risk is unknown; use headphones or keep the iPad speaker off for meeting tests."

    if output_peak <= 0:
        level_state = "silent"
        level_message = "No decoded microphone PCM level was observed."
    elif output_peak < 500 or sustained_too_quiet_for_gain_only:
        level_state = "low"
        level_message = "Microphone level is low; sustained RMS is too weak for clean meeting audio."
    elif output_peak > 26000 or clipped > 0:
        level_state = "too_hot"
        level_message = "Level is near clipping; lower Mic gain."
    else:
        level_state = "ok"
        level_message = "Microphone level is in a usable range."

    if overflow_dropped > 0 or (dropped > 960 and dropped_ratio > 0.01):
        continuity_state = "dropping"
        continuity_message = "Playback buffer dropped audio; speech may skip."
    elif underflows > 3 and underflow_frame_ratio > 0.03:
        continuity_state = "underflowing"
        continuity_message = "Playback buffer ran dry repeatedly; speech may crackle or pause."
    else:
        continuity_state = "ok"
        continuity_message = "Playback continuity counters are low."

    if latency_ms >= 1500.0:
        latency_state = "high_latency"
        latency_message = "Playback buffer is intentionally large for stability; meeting audio will be delayed."
    elif latency_ms >= 500.0:
        latency_state = "buffered"
        latency_message = "Playback buffer has a moderate stability margin."
    else:
        latency_state = "low_latency"
        latency_message = "Playback buffer is low-latency; watch for underflows on this Python/PortAudio path."
    suggested_prebuffer_ms, suggested_prebuffer_reason = _suggest_playback_prebuffer_ms(state, continuity_state, latency_state)

    recommendations: list[str] = []
    if level_state == "silent":
        recommendations.append("Check that the iPad microphone is active and close enough to the speaker.")
    elif level_state == "low":
        if source_too_quiet:
            if recommended_source_lift_db > 0:
                recommendations.append(f"Source level is extremely low; improve iPad-side source level by roughly {recommended_source_lift_db:g} dB before adding more Windows gain.")
            else:
                recommendations.append("Source level is extremely low; move the iPad closer before adding more Windows gain, because gain will mostly amplify room noise and echo.")
        else:
            recommendations.append(f"Move the iPad closer first, then try Mic gain around {suggested_gain_step:g}; high gain raises room noise and echo.")
    elif level_state == "too_hot":
        recommendations.append(f"Lower Mic gain to around {suggested_gain:g} to avoid clipping.")
    if continuity_state != "ok":
        recommendations.append(f"Raise playback prebuffer toward {suggested_prebuffer_ms:g} ms, then restart the bridge if underflows/drops keep rising.")
    elif latency_state == "high_latency":
        recommendations.append(f"Audio is stable but delayed; after stability is confirmed, test playback prebuffer around {suggested_prebuffer_ms:g} ms.")
    if gate_ratio > 0.3:
        recommendations.append("Noise gate is active on a large share of audio; lower Gate or set it to 0 if quiet words are being cut off.")
    if limited > 0 and clipped == 0:
        recommendations.append("Soft limiter is active; lower Mic gain if speech still sounds compressed or harsh.")
    if echo_state != "verified":
        recommendations.append("Enable and expose iPad-side voice processing/AEC; Windows gain and VB-CABLE cannot remove acoustic echo.")
    primary_issue, primary_recommendation = _primary_quality_issue(
        level_state=level_state,
        continuity_state=continuity_state,
        latency_state=latency_state,
        echo_state=echo_state,
        source_too_quiet=source_too_quiet,
        limited=limited,
    )

    return {
        "windowsShortTermReady": level_state == "ok" and continuity_state == "ok" and clipped == 0,
        "fullShortTermReady": level_state == "ok" and continuity_state == "ok" and clipped == 0 and echo_state == "verified",
        "primaryIssue": primary_issue,
        "primaryRecommendation": primary_recommendation,
        "levelState": level_state,
        "levelMessage": level_message,
        "inputPeakAbs": input_peak,
        "inputPeakDbfs": _dbfs(input_peak),
        "outputPeakAbs": output_peak,
        "outputPeakDbfs": _dbfs(output_peak),
        "outputRms": state.output_rms,
        "outputRmsDbfs": output_rms_dbfs,
        "estimatedOutputPeakAbs": estimated_output_peak,
        "estimatedNextGainPeakAbs": estimated_next_gain_peak,
        "estimatedNextGainPeakDbfs": _dbfs(estimated_next_gain_peak),
        "estimatedNextGainRms": estimated_next_gain_rms,
        "estimatedNextGainRmsDbfs": _dbfs(estimated_next_gain_rms),
        "safeMicGainCeiling": suggested_gain,
        "safeMicGainAction": gain_safety["action"],
        "safeMicGainMessage": gain_safety["message"],
        "safeMicGainCanReachTarget": gain_safety["canReachTarget"],
        "estimatedSafeGainPeakAbs": estimated_safe_gain_peak,
        "estimatedSafeGainPeakDbfs": _dbfs(estimated_safe_gain_peak),
        "estimatedSafeGainRms": estimated_safe_gain_rms,
        "estimatedSafeGainRmsDbfs": _dbfs(estimated_safe_gain_rms),
        "targetPeakDbfs": _dbfs(4000.0),
        "targetSustainedRms": target_sustained_rms_abs,
        "targetSustainedRmsDbfs": target_sustained_rms_dbfs,
        "recommendedSourceLiftDb": recommended_source_lift_db,
        "sustainedOutputTooQuiet": sustained_too_quiet_for_gain_only,
        "sourceTooQuietForGainOnly": source_too_quiet,
        "gainOnlyLikelyToAmplifyNoise": gain_only_likely_to_amplify_noise,
        "gainRiskMessage": gain_risk_message,
        "continuityState": continuity_state,
        "continuityMessage": continuity_message,
        "latencyState": latency_state,
        "latencyMessage": latency_message,
        "effectivePlaybackLatencyMs": round(latency_ms, 3),
        "playbackUnderflowRatio": underflow_ratio,
        "playbackUnderflowFrameRatio": underflow_frame_ratio,
        "playbackDroppedRatio": dropped_ratio,
        "playbackOverflowDroppedFrames": overflow_dropped,
        "playbackCatchupDroppedFrames": int(state.playback_buffer.catchup_dropped_frames) if state.playback_buffer is not None else 0,
        "echoCancellationState": echo_state,
        "echoCancellationMessage": echo_message,
        "echoRiskState": echo_risk_state,
        "echoRiskMessage": echo_risk_message,
        "lowCutHz": float(state.low_cut_hz),
        "noiseGateState": "enabled" if state.noise_gate_threshold > 0 else "disabled",
        "noiseGateThreshold": float(state.noise_gate_threshold),
        "noiseGateGain": round(float(state.noise_gate_gain), 4),
        "noiseGateFrames": int(state.noise_gate_frames),
        "noiseGateActivityRatio": gate_ratio,
        "outputLimitedSamples": limited,
        "recommendedMicGain": suggested_gain,
        "recommendedMicGainStep": suggested_gain_step,
        "recommendedMonitorGain": suggested_monitor_gain,
        "recommendedPlaybackPrebufferMs": suggested_prebuffer_ms,
        "recommendedPlaybackPrebufferReason": suggested_prebuffer_reason,
        "recommendations": recommendations,
    }


def _suggest_mic_gain(peak: int, current_gain: float, clipped: int) -> float:
    if clipped > 0:
        return round(max(0.5, min(3.0, current_gain * 0.5)), 2)
    if peak <= 0:
        return round(max(1.0, min(3.0, current_gain)), 2)
    target_post_gain_peak = 4000.0
    return round(max(0.5, min(3.0, target_post_gain_peak / float(peak))), 2)


def _suggest_monitor_gain(peak: int) -> float:
    if peak <= 0:
        return 4.0
    target_monitor_peak = 4000.0
    return round(max(1.0, min(12.0, target_monitor_peak / float(peak))), 2)


def _gain_safety_status(
    *,
    current_gain: float,
    suggested_gain: float,
    suggested_gain_step: float,
    clipped: int,
    limited: int,
    source_too_quiet: bool,
    estimated_safe_gain_peak: int,
    estimated_safe_gain_rms: int,
    target_sustained_rms_abs: float,
) -> JsonDict:
    can_reach_target = bool(
        estimated_safe_gain_peak >= 500
        and float(estimated_safe_gain_rms) >= float(target_sustained_rms_abs)
    )
    if clipped > 0 or limited > 0:
        return {
            "action": "lower_gain",
            "message": "Lower Mic gain before judging quality; current processing is clipping or limiting peaks.",
            "canReachTarget": can_reach_target,
        }
    if source_too_quiet:
        return {
            "action": "hold_source_first",
            "message": "Do not raise Windows Mic gain yet; even the safe gain ceiling is unlikely to reach clean meeting level.",
            "canReachTarget": can_reach_target,
        }
    if suggested_gain_step > current_gain + 0.001:
        return {
            "action": "raise_modestly",
            "message": "A modest Mic gain step is reasonable, but source placement is still preferred over large Windows gain.",
            "canReachTarget": can_reach_target,
        }
    if suggested_gain_step < current_gain - 0.001:
        return {
            "action": "lower_gain",
            "message": "Lower Mic gain toward the safe ceiling to avoid harsh or clipped speech.",
            "canReachTarget": can_reach_target,
        }
    return {
        "action": "keep_gain",
        "message": "Current Mic gain is within the conservative short-term range.",
        "canReachTarget": can_reach_target,
    }


def _primary_quality_issue(
    *,
    level_state: str,
    continuity_state: str,
    latency_state: str,
    echo_state: str,
    source_too_quiet: bool,
    limited: int,
) -> tuple[str, str]:
    if source_too_quiet:
        return "source_too_quiet", "move_ipad_closer"
    if level_state == "silent":
        return "silent", "check_ipad_microphone"
    if level_state == "too_hot":
        return "level_too_hot", "lower_mic_gain"
    if continuity_state != "ok":
        return "continuity_unstable", "raise_prebuffer_or_restart_bridge"
    if limited > 0:
        return "limiter_active", "lower_mic_gain_if_harsh"
    if latency_state == "high_latency":
        return "high_latency", "lower_prebuffer_after_stable"
    if echo_state != "verified":
        return "aec_unverified", "use_headphones_or_enable_ipad_aec"
    if level_state == "low":
        return "level_low", "move_ipad_closer_or_raise_gain_modestly"
    return "none", "none"


def _suggest_mic_gain_step(current_gain: float, target_gain: float) -> float:
    current = max(0.5, min(20.0, float(current_gain or 1.0)))
    target = max(0.5, min(3.0, float(target_gain or current)))
    if target > current:
        return round(min(target, current * 2.0), 2)
    if target < current:
        return round(max(target, current * 0.5), 2)
    return round(target, 2)


def _estimate_peak_after_gain_step(peak: int, current_gain: float, next_gain: float) -> int:
    if peak <= 0:
        return 0
    current = max(0.05, float(current_gain or 1.0))
    next_value = max(0.05, float(next_gain or current))
    return int(round(float(peak) * (next_value / current)))


def _suggest_playback_prebuffer_ms(state: _AudioReceiverState, continuity_state: str, latency_state: str) -> tuple[float, str]:
    current = _frames_to_ms(state.playback_prebuffer_frames, 48000)
    if continuity_state != "ok":
        target = max(current, 2000.0)
        return min(5000.0, round(target + 500.0, 3)), "increase_for_continuity"
    if latency_state == "high_latency":
        return max(1000.0, min(1500.0, round(current * 0.75, 3))), "lower_after_stable"
    return current, "keep_current"


def _first_present(source: JsonDict, *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _load_audio_backend() -> JsonDict:
    try:
        import numpy as np
        import sounddevice as sd
        return {"ok": True, "numpy": np, "sounddevice": sd}
    except Exception as exc:
        return {"ok": False, "error": {"code": "audio_backend_unavailable", "message": str(exc)}}


def _device_list(sd: Any) -> list[JsonDict]:
    devices = []
    hostapis = sd.query_hostapis() if hasattr(sd, "query_hostapis") else []
    for index, device in enumerate(sd.query_devices()):
        hostapi_index = int(device.get("hostapi", -1) or -1)
        hostapi_name = ""
        if 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name", ""))
        devices.append(
            {
                "index": index,
                "name": str(device.get("name", "")),
                "hostapi": hostapi_index,
                "hostapi_name": hostapi_name,
                "max_input_channels": int(device.get("max_input_channels", 0) or 0),
                "max_output_channels": int(device.get("max_output_channels", 0) or 0),
                "default_samplerate": float(device.get("default_samplerate", 0) or 0),
            }
        )
    return devices


def _find_device(devices: list[JsonDict], name: str, *, is_input: bool = False, is_output: bool = False) -> JsonDict | None:
    needle = name.lower()
    candidates = []
    for device in devices:
        text = str(device.get("name", "")).lower()
        if needle not in text:
            continue
        if is_input and int(device.get("max_input_channels") or 0) < 1:
            continue
        if is_output and int(device.get("max_output_channels") or 0) < 1:
            continue
        candidates.append(device)
    if not candidates:
        return None

    def score(device: JsonDict) -> tuple[int, int, int, int, int]:
        rate = int(float(device.get("default_samplerate") or 0))
        channels_key = "max_input_channels" if is_input else "max_output_channels"
        channels = int(device.get(channels_key) or 0)
        exact = 1 if str(device.get("name", "")).lower().strip() == needle.strip() else 0
        hostapi = str(device.get("hostapi_name", "")).lower()
        hostapi_score = 4 if "wasapi" in hostapi else 2 if "directsound" in hostapi else 1 if "mme" in hostapi else 0
        rate_score = 2 if rate == 48000 else 1 if rate == 44100 else 0
        stereo_score = 2 if channels == 2 else 1 if channels > 2 else 0
        fewer_channels = -abs(channels - 2)
        return (exact, hostapi_score, rate_score, stereo_score, fewer_channels)

    return sorted(candidates, key=score, reverse=True)[0]


def _normalize_base_url(base_url: str) -> str:
    text = base_url.strip().rstrip("/")
    if not text.startswith(("http://", "https://")):
        text = "http://" + text
    return text


def _normal_app_microphone_visible(enabled: bool) -> bool:
    if not enabled:
        return False
    try:
        media = inspect_media_devices()
        return bool(media.get("windows_detects_compatible_microphone_route_now") or media.get("normal_app_microphone_visible"))
    except Exception:
        return False


def _prefer_codec(transceiver: Any, codecs: list[Any], preferred_name: str) -> None:
    preferred = [codec for codec in codecs if preferred_name.lower() in str(getattr(codec, "mimeType", "")).lower()]
    others = [codec for codec in codecs if codec not in preferred]
    if preferred:
        transceiver.setCodecPreferences(preferred + others)


async def _wait_for_ice_gathering_complete(pc: Any, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while pc.iceGatheringState != "complete" and time.monotonic() < deadline:
        await asyncio.sleep(0.05)


async def _apply_polled_ice_candidates(pc: Any, client: WebRTCMicrophoneClient, warnings: list[str]) -> None:
    from aiortc.sdp import candidate_from_sdp

    seen: set[str] = set()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            payload = client.local_ice_candidates()
        except Exception as exc:
            warnings.append(f"polling iPad ICE candidates failed: {exc}")
            return
        candidates = payload.get("localIceCandidates") or []
        if isinstance(candidates, dict):
            candidates = [candidates]
        added = 0
        for item in candidates:
            if not isinstance(item, dict):
                continue
            raw_candidate = str(item.get("candidate") or "").strip()
            if not raw_candidate:
                continue
            candidate_key = "|".join(
                [
                    raw_candidate,
                    str(item.get("sdpMid") or ""),
                    str(item.get("sdpMLineIndex") if item.get("sdpMLineIndex") is not None else ""),
                ]
            )
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            candidate_sdp = raw_candidate.removeprefix("candidate:")
            try:
                candidate = candidate_from_sdp(candidate_sdp)
                if item.get("sdpMid") is not None:
                    candidate.sdpMid = str(item.get("sdpMid"))
                if item.get("sdpMLineIndex") is not None:
                    candidate.sdpMLineIndex = int(item.get("sdpMLineIndex"))
                await pc.addIceCandidate(candidate)
                added += 1
            except Exception as exc:
                warnings.append(f"adding iPad ICE candidate failed: {exc}")
        if added > 0:
            await asyncio.sleep(0.25)
        if candidates and time.monotonic() > deadline - 3.0:
            return
        await asyncio.sleep(0.25)


def _extract_description(payload: JsonDict) -> JsonDict | None:
    for key in ("localDescription", "remoteDescription", "description"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("type") and value.get("sdp"):
            return {"type": str(value["type"]), "sdp": str(value["sdp"])}
    if payload.get("type") and payload.get("sdp"):
        return {"type": str(payload["type"]), "sdp": str(payload["sdp"])}
    return None


def _inbound_audio_totals(stats: Any) -> tuple[int, int]:
    packets = 0
    bytes_received = 0
    for report in stats.values():
        if getattr(report, "type", None) != "inbound-rtp":
            continue
        if getattr(report, "kind", None) not in (None, "audio"):
            continue
        packets += int(getattr(report, "packetsReceived", 0) or 0)
        bytes_received += int(getattr(report, "bytesReceived", 0) or 0)
    return packets, bytes_received


def _microphone_upstream_status(status: JsonDict) -> JsonDict:
    nested = status.get("microphoneUpstream") if isinstance(status.get("microphoneUpstream"), dict) else {}
    return {
        "microphoneUpstreamState": status.get("microphoneUpstreamState", nested.get("state")),
        "microphoneUpstreamPacketsSent": status.get("microphoneUpstreamPacketsSent", nested.get("packetsSent")),
        "microphoneUpstreamBytesSent": status.get("microphoneUpstreamBytesSent", nested.get("bytesSent")),
        "microphoneUpstreamStatsFresh": status.get("microphoneUpstreamStatsFresh", nested.get("statsFresh")),
        "microphoneUpstreamStatsAgeMs": status.get("microphoneUpstreamStatsAgeMs", nested.get("statsAgeMs")),
    }


def _int_value(value: Any) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else (None if value is None else bool(value))


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
