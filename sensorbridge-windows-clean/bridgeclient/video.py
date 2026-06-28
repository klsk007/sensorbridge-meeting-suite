from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from bridgeclient.client import SensorBridgeClient
from bridgeclient.models import JsonDict, VideoFrame
from bridgeclient.video_sink import FrameFileVideoSink, VideoSink


@dataclass
class VideoBridgeResult:
    frame: VideoFrame
    sink: JsonDict

    def to_json(self) -> JsonDict:
        return {"frame": self.frame.to_json(), "sink": self.sink}


def pump_one_video_frame(client: SensorBridgeClient, sink: VideoSink) -> VideoBridgeResult:
    frame = client.sample_video_frame()
    sink.write_frame(frame)
    return VideoBridgeResult(frame=frame, sink=sink.to_json())


@dataclass
class VideoBridgeRunResult:
    frames_requested: int
    frames_written: int
    first_sequence: int | None
    last_sequence: int | None
    sink: JsonDict

    def to_json(self) -> JsonDict:
        return {
            "ok": True,
            "command": "pump_video",
            "frames_requested": self.frames_requested,
            "frames_written": self.frames_written,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "sink": self.sink,
        }


@dataclass
class CameraPipelineCheckResult:
    frames_requested: int
    frames_written: int
    first_sequence: int | None
    last_sequence: int | None
    sink: JsonDict
    frame_file_ready: bool
    latest_frame_exists: bool
    latest_metadata_exists: bool
    latest_frame_bytes: int
    camera_provider: JsonDict
    media_devices: JsonDict

    def to_json(self) -> JsonDict:
        provider_running = bool(self.camera_provider.get("running_after") or self.camera_provider.get("running_before"))
        provider_registered = bool(self.camera_provider.get("registered_after") or self.camera_provider.get("registered_before"))
        windows_detects_camera = bool(self.media_devices.get("windows_detects_camera_now"))
        ready = self.frame_file_ready and provider_running and provider_registered and windows_detects_camera
        return {
            "ok": ready,
            "command": "camera_pipeline_check",
            "changes_system": False,
            "frames_requested": self.frames_requested,
            "frames_written": self.frames_written,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "sink": self.sink,
            "frame_file_ready": self.frame_file_ready,
            "latest_frame_exists": self.latest_frame_exists,
            "latest_metadata_exists": self.latest_metadata_exists,
            "latest_frame_bytes": self.latest_frame_bytes,
            "camera_provider_running": provider_running,
            "camera_provider_registered": provider_registered,
            "windows_detects_camera_now": windows_detects_camera,
            "windows_camera_feed_ready": ready,
            "camera_provider": self.camera_provider,
            "media_devices": self.media_devices,
            "notes": [
                "This check writes SensorBridge video frames to the frame-file sink consumed by the development camera provider.",
                "It does not install a permanent Windows camera driver.",
            ],
        }


def pump_video_frames(
    client: SensorBridgeClient,
    sink: VideoSink,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
) -> VideoBridgeRunResult:
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1")

    first_sequence: int | None = None
    last_sequence: int | None = None
    for index in range(frame_count):
        frame = client.sample_video_frame()
        sink.write_frame(frame)
        if first_sequence is None:
            first_sequence = frame.sequence
        last_sequence = frame.sequence
        if frame_delay_s > 0 and index < frame_count - 1:
            time.sleep(frame_delay_s)

    sink_payload = sink.to_json()
    return VideoBridgeRunResult(
        frames_requested=frame_count,
        frames_written=int(sink_payload.get("frames_written", frame_count)),
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        sink=sink_payload,
    )


def check_camera_pipeline(
    client: SensorBridgeClient,
    *,
    frame_count: int,
    frame_delay_s: float = 0.0,
    directory: str | Path | None = None,
) -> CameraPipelineCheckResult:
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1")

    from bridgeclient.camera_provider import inspect_camera_provider_status
    from bridgeclient.media_devices import inspect_media_devices

    sink = FrameFileVideoSink(directory)
    result = pump_video_frames(client, sink, frame_count=frame_count, frame_delay_s=frame_delay_s)
    sink_payload = result.sink
    latest_value = sink_payload.get("latest_frame_path")
    metadata_value = sink_payload.get("latest_metadata_path")
    latest_path = Path(str(latest_value)) if latest_value else Path()
    metadata_path = Path(str(metadata_value)) if metadata_value else Path()
    latest_frame_exists = latest_path.is_file()
    latest_metadata_exists = metadata_path.is_file()
    latest_frame_bytes = latest_path.stat().st_size if latest_frame_exists else 0
    frame_file_ready = bool(
        result.frames_written == frame_count
        and latest_frame_exists
        and latest_metadata_exists
        and latest_frame_bytes > 0
    )

    return CameraPipelineCheckResult(
        frames_requested=frame_count,
        frames_written=result.frames_written,
        first_sequence=result.first_sequence,
        last_sequence=result.last_sequence,
        sink=sink_payload,
        frame_file_ready=frame_file_ready,
        latest_frame_exists=latest_frame_exists,
        latest_metadata_exists=latest_metadata_exists,
        latest_frame_bytes=latest_frame_bytes,
        camera_provider=inspect_camera_provider_status(),
        media_devices=inspect_media_devices(),
    )
