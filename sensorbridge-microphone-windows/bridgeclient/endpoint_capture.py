from __future__ import annotations

import math
from typing import Any

JsonDict = dict[str, Any]


def inspect_windows_endpoint_capture(duration_s: float = 0.75) -> JsonDict:
    """Capture from Windows-visible SensorBridge endpoints using optional PortAudio bindings."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        return {
            "ok": False,
            "command": "windows_endpoint_capture_check",
            "available": False,
            "error": {
                "code": "sounddevice_unavailable",
                "message": str(exc),
            },
            "ordinary_apps_receive_audio_from_endpoint": False,
            "ipad_pcm_injected_into_virtual_endpoint": False,
            "notes": [
                "Install the optional sounddevice package to sample Windows audio endpoints.",
            ],
        }

    devices = sd.query_devices()
    candidates = [
        (index, device)
        for index, device in enumerate(devices)
        if int(device.get("max_input_channels", 0) or 0) > 0
        and "SensorBridge" in str(device.get("name", ""))
    ]

    captures: list[JsonDict] = []
    for index, device in candidates:
        sample_rate = int(float(device.get("default_samplerate") or 48000))
        if sample_rate < 1:
            sample_rate = 48000
        frame_count = max(1, int(duration_s * sample_rate))
        try:
            data = sd.rec(frame_count, samplerate=sample_rate, channels=1, dtype="int16", device=index)
            sd.wait()
            samples = data.reshape(-1).astype(np.float64)
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            peak_abs = int(np.max(np.abs(samples))) if samples.size else 0
            first_samples = [int(value) for value in data.reshape(-1)[:16]]
            captures.append(
                {
                    "index": index,
                    "name": str(device.get("name", "")),
                    "sample_rate_hz": sample_rate,
                    "opened": True,
                    "rms": round(rms, 3),
                    "peak_abs": peak_abs,
                    "nonzero_samples": int(np.count_nonzero(data)),
                    "looks_like_sysvad_test_tone": _looks_like_sysvad_test_tone(first_samples, rms, peak_abs),
                    "first_samples": first_samples,
                }
            )
        except Exception as exc:
            captures.append(
                {
                    "index": index,
                    "name": str(device.get("name", "")),
                    "sample_rate_hz": sample_rate,
                    "opened": False,
                    "error": str(exc),
                }
            )

    opened = [item for item in captures if item.get("opened")]
    active = [item for item in opened if float(item.get("rms") or 0.0) > 1.0 and int(item.get("nonzero_samples") or 0) > 0]
    sysvad_tone = bool(active) and all(bool(item.get("looks_like_sysvad_test_tone")) for item in active[: min(3, len(active))])
    return {
        "ok": bool(active),
        "command": "windows_endpoint_capture_check",
        "available": True,
        "sensorbridge_input_device_count": len(candidates),
        "opened_endpoint_count": len(opened),
        "active_endpoint_count": len(active),
        "ordinary_apps_receive_audio_from_endpoint": bool(active),
        "endpoint_audio_looks_like_sysvad_test_tone": sysvad_tone,
        "ipad_pcm_injected_into_virtual_endpoint": bool(active) and not sysvad_tone,
        "captures": captures,
        "notes": [
            "This samples the Windows recording endpoint that ordinary apps can open.",
            "A fixed SysVAD test tone means apps can receive endpoint audio, but the iPad PCM handoff is not yet injected into the virtual microphone driver.",
        ],
    }


def _looks_like_sysvad_test_tone(first_samples: list[int], rms: float, peak_abs: int) -> bool:
    if not (11000.0 <= rms <= 12150.0 and 16000 <= peak_abs <= 16500):
        return False
    if len(first_samples) < 8:
        return True
    # SysVAD's sample capture is a stable high-amplitude sine. The exact phase may vary.
    amplitude = max(1.0, float(peak_abs))
    normalized = [sample / amplitude for sample in first_samples[:8]]
    diffs = [abs(after - before) for before, after in zip(normalized, normalized[1:])]
    return max(diffs) < 0.45 and any(abs(sample) > 0.85 for sample in normalized)
