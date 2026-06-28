from __future__ import annotations

import base64
import importlib.util
import json
import os
import struct
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from bridgeclient.errors import BridgeClientError
from bridgeclient.models import VideoFrame


class VideoSink(Protocol):
    name: str

    def write_frame(self, frame: VideoFrame) -> None:
        ...

    def to_json(self) -> dict[str, Any]:
        ...


class RawFrameVideoSink(Protocol):
    def write_raw_frame(
        self,
        *,
        sequence: int,
        width: int,
        height: int,
        pixel_format: str,
        raw: bytes,
        timestamp_ns: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        ...


class NullVideoSink:
    name = "null"

    def __init__(self) -> None:
        self.frames_written = 0

    def write_frame(self, frame: VideoFrame) -> None:
        self.frames_written += 1

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "frames_written": self.frames_written}

    def status(self) -> dict[str, Any]:
        return self.to_json()


class PyVirtualCamSink:
    name = "pyvirtualcam"

    def __init__(self) -> None:
        try:
            import numpy
            import pyvirtualcam
        except ImportError as exc:
            raise BridgeClientError(
                "pyvirtualcam video sink requested, but numpy/pyvirtualcam is not installed.",
                code="video_sink_unavailable",
                detail={"sink": self.name, "missing": exc.name},
            ) from exc
        self._numpy = numpy
        self._pyvirtualcam = pyvirtualcam
        self._camera: Any | None = None
        self.frames_written = 0

    def write_frame(self, frame: VideoFrame) -> None:
        if not frame.data_base64 or frame.width is None or frame.height is None:
            raise BridgeClientError(
                "pyvirtualcam sink requires data_base64, width, and height in the video frame.",
                code="video_frame_not_renderable",
                detail={"frame": frame.to_json()},
            )

        raw = base64.b64decode(frame.data_base64)
        array = self._numpy.frombuffer(raw, dtype=self._numpy.uint8)
        expected = frame.width * frame.height * 3
        if array.size != expected:
            raise BridgeClientError(
                "pyvirtualcam sink currently expects raw RGB24 frame bytes.",
                code="unsupported_video_frame_format",
                detail={
                    "expected_bytes": expected,
                    "actual_bytes": int(array.size),
                    "pixel_format": frame.pixel_format,
                },
            )
        image = array.reshape((frame.height, frame.width, 3))
        if self._camera is None:
            self._camera = self._pyvirtualcam.Camera(width=frame.width, height=frame.height, fps=30)
        self._camera.send(image)
        self._camera.sleep_until_next_frame()
        self.frames_written += 1

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "frames_written": self.frames_written}

    def status(self) -> dict[str, Any]:
        return self.to_json()


class FrameFileVideoSink:
    name = "frame_file"

    def __init__(self, directory: str | Path | None = None) -> None:
        if directory is None:
            directory = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SensorBridge" / "camera"
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.frames_written = 0
        self.latest_frame_path: Path | None = None
        self.latest_metadata_path = self.directory / "latest.json"

    def write_frame(self, frame: VideoFrame) -> None:
        if not frame.data_base64:
            raise BridgeClientError(
                "frame-file sink requires data_base64 in the video frame.",
                code="video_frame_not_renderable",
                detail={"frame": frame.to_json()},
            )
        raw = base64.b64decode(frame.data_base64)
        pixel_format = (frame.pixel_format or "").lower()
        if pixel_format in {"rgb24", "bgr24", "bgra32", "rgba32"}:
            if frame.width is None or frame.height is None:
                raise BridgeClientError(
                    "raw frame-file sink requires width and height.",
                    code="video_frame_not_renderable",
                    detail={"frame": frame.to_json()},
                )
            payload = _encode_bmp(frame.width, frame.height, raw, pixel_format)
            target = self.directory / "latest.bmp"
            content_type = "image/bmp"
        else:
            raise BridgeClientError(
                "frame-file sink supports RGB24, BGR24, BGRA32, and RGBA32 frames.",
                code="unsupported_video_frame_format",
                detail={"pixel_format": frame.pixel_format, "bytes": len(raw)},
            )

        self._write_payload(
            sequence=frame.sequence,
            timestamp_ns=frame.timestamp_ns,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            payload=payload,
            target=target,
            content_type=content_type,
            metadata=None,
        )

    def write_raw_frame(
        self,
        *,
        sequence: int,
        width: int,
        height: int,
        pixel_format: str,
        raw: bytes,
        timestamp_ns: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized = pixel_format.lower()
        if normalized in {"rgb24", "bgr24", "bgra32", "rgba32"}:
            payload = _encode_bmp(width, height, raw, normalized)
            target = self.directory / "latest.bmp"
            content_type = "image/bmp"
        else:
            raise BridgeClientError(
                "frame-file sink supports RGB24, BGR24, BGRA32, and RGBA32 raw frames.",
                code="unsupported_video_frame_format",
                detail={"pixel_format": pixel_format, "bytes": len(raw), "width": width, "height": height},
            )
        self._write_payload(
            sequence=sequence,
            timestamp_ns=timestamp_ns,
            width=width,
            height=height,
            pixel_format=pixel_format,
            payload=payload,
            target=target,
            content_type=content_type,
            metadata=metadata,
        )

    def _write_payload(
        self,
        *,
        sequence: int | None,
        timestamp_ns: int | None,
        width: int | None,
        height: int | None,
        pixel_format: str | None,
        payload: bytes,
        target: Path,
        content_type: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        _atomic_write(target, payload)
        metadata = {
            **(metadata or {}),
            "sequence": sequence,
            "timestamp_ns": timestamp_ns,
            "width": width,
            "height": height,
            "pixel_format": pixel_format,
            "content_type": content_type,
            "path": str(target),
            "updated_at": time.time(),
        }
        _atomic_write(self.latest_metadata_path, json.dumps(metadata, indent=2).encode("utf-8"))
        self.latest_frame_path = target
        self.frames_written += 1

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "frames_written": self.frames_written,
            "directory": str(self.directory),
            "latest_frame_path": str(self.latest_frame_path) if self.latest_frame_path else None,
            "latest_metadata_path": str(self.latest_metadata_path),
        }

    def status(self) -> dict[str, Any]:
        return self.to_json()


def _atomic_write(path: Path, payload: bytes) -> None:
    last_error: OSError | None = None
    for attempt in range(6):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp")
        try:
            tmp.write_bytes(payload)
            tmp.replace(path)
            return
        except OSError as exc:
            last_error = exc
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if getattr(exc, "winerror", None) not in {5, 32}:
                raise
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _encode_bmp(width: int, height: int, raw: bytes, pixel_format: str) -> bytes:
    channels = {
        "rgb24": 3,
        "bgr24": 3,
        "bgra32": 4,
        "rgba32": 4,
    }[pixel_format]
    expected = width * height * channels
    if len(raw) != expected:
        raise BridgeClientError(
            "raw video frame byte count does not match width, height, and pixel format.",
            code="unsupported_video_frame_format",
            detail={
                "expected_bytes": expected,
                "actual_bytes": len(raw),
                "pixel_format": pixel_format,
                "width": width,
                "height": height,
            },
        )

    if pixel_format == "bgr24":
        row_bytes = width * 3
        padding = (4 - (row_bytes % 4)) % 4
        if padding:
            rows = [raw[offset : offset + row_bytes] + (b"\x00" * padding) for offset in range(0, len(raw), row_bytes)]
            pixel_payload = b"".join(rows)
        else:
            pixel_payload = raw
        dib_header_size = 40
        pixel_offset = 14 + dib_header_size
        image_size = len(pixel_payload)
        file_size = pixel_offset + image_size
        file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
        dib_header = struct.pack(
            "<IiiHHIIiiII",
            dib_header_size,
            width,
            -height,
            1,
            24,
            0,
            image_size,
            2835,
            2835,
            0,
            0,
        )
        return file_header + dib_header + pixel_payload

    pixel_bytes = bytearray(width * height * 4)
    src = 0
    dst = 0
    for _ in range(width * height):
        if pixel_format == "rgb24":
            r, g, b = raw[src], raw[src + 1], raw[src + 2]
            src += 3
        elif pixel_format == "bgr24":
            b, g, r = raw[src], raw[src + 1], raw[src + 2]
            src += 3
        elif pixel_format == "bgra32":
            b, g, r = raw[src], raw[src + 1], raw[src + 2]
            src += 4
        else:
            r, g, b = raw[src], raw[src + 1], raw[src + 2]
            src += 4
        pixel_bytes[dst : dst + 4] = bytes((b, g, r, 255))
        dst += 4

    dib_header_size = 40
    pixel_offset = 14 + dib_header_size
    image_size = len(pixel_bytes)
    file_size = pixel_offset + image_size
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
    # Negative height stores rows top-down, matching the in-memory frame order.
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        dib_header_size,
        width,
        -height,
        1,
        32,
        0,
        image_size,
        2835,
        2835,
        0,
        0,
    )
    return file_header + dib_header + bytes(pixel_bytes)


def inspect_video_sinks() -> dict[str, Any]:
    pyvirtualcam_spec = importlib.util.find_spec("pyvirtualcam")
    numpy_spec = importlib.util.find_spec("numpy")
    pyvirtualcam_info: dict[str, Any] = {
        "available": bool(pyvirtualcam_spec and numpy_spec),
        "pyvirtualcam_installed": pyvirtualcam_spec is not None,
        "numpy_installed": numpy_spec is not None,
        "creates_windows_device": False,
        "requires_existing_backend": True,
        "notes": [
            "pyvirtualcam can write frames only when an existing compatible virtual camera backend is installed.",
            "This check does not prove Windows enumerates a SensorBridge camera device.",
        ],
    }
    if pyvirtualcam_spec is None:
        pyvirtualcam_info["missing"] = "pyvirtualcam"
    elif numpy_spec is None:
        pyvirtualcam_info["missing"] = "numpy"
    else:
        try:
            import pyvirtualcam

            backends = getattr(pyvirtualcam, "BACKENDS", None)
            pyvirtualcam_info["version"] = getattr(pyvirtualcam, "__version__", None)
            pyvirtualcam_info["backends"] = sorted(str(name) for name in backends) if backends else []
        except Exception as exc:  # pragma: no cover - defensive environment probe.
            pyvirtualcam_info["available"] = False
            pyvirtualcam_info["error"] = f"{type(exc).__name__}: {exc}"

    return {
        "ok": True,
        "command": "video_sink_status",
        "sinks": {
            "null": {
                "available": True,
                "creates_windows_device": False,
                "notes": ["Development sink only; discards frames after counting them."],
            },
            "pyvirtualcam": pyvirtualcam_info,
            "frame_file": {
                "available": True,
                "creates_windows_device": False,
                "directory": str(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SensorBridge" / "camera"),
                "notes": [
                    "Writes the latest SensorBridge frame to disk for a development virtual camera source to consume.",
                    "This check does not prove Windows enumerates a camera by itself.",
                ],
            },
        },
        "system_virtual_camera_required": True,
    }


def create_video_sink(name: str) -> VideoSink:
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "null":
        return NullVideoSink()
    if normalized in {"frame_file", "framefile", "file"}:
        return FrameFileVideoSink()
    if normalized == "pyvirtualcam":
        return PyVirtualCamSink()
    raise BridgeClientError(
        f"Unknown video sink '{name}'.",
        code="unknown_video_sink",
        detail={"sink": name, "available": ["null", "frame-file", "pyvirtualcam"]},
    )
