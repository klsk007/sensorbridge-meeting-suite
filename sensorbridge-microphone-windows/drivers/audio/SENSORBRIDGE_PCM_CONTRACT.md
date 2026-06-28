# SensorBridge Microphone PCM Contract

This contract defines the user-mode audio handoff that the SensorBridge Windows client now produces for a SysVAD-derived virtual microphone.

Current development producer:

```text
C:\ProgramData\SensorBridge\microphone\latest.pcm
C:\ProgramData\SensorBridge\microphone\latest.json
```

The local test server writes the same shape under its configured data directory:

```text
<data-dir>\microphone\latest.pcm
<data-dir>\microphone\latest.json
```

`latest.pcm` contains one complete SensorBridge microphone frame. It is replaced atomically.

PCM format:

- Encoding: signed 16-bit little-endian PCM, `S16LE`
- Sample rate: declared by `latest.json` as `sample_rate_hz`
- Channel count: declared by `latest.json` as `channel_count`
- Frame count: declared by `latest.json` as `frame_count`
- Byte count: `frame_count * channel_count * 2`

`latest.json` fields:

```json
{
  "sequence": 12,
  "timestamp_ns": 1782465472292352000,
  "sample_rate_hz": 48000,
  "channel_count": 1,
  "sample_format": "S16LE",
  "frame_count": 480,
  "byte_count": 960,
  "content_type": "audio/L16",
  "pcm_encoding": "S16LE",
  "path": "C:\\ProgramData\\SensorBridge\\microphone\\latest.pcm",
  "updated_at": 1782465472.292,
  "source": "sensorbridge-audio-frame"
}
```

Consumer requirements for the future driver bridge:

- Read `latest.json` first, then open `path`.
- Ignore a frame if `sample_format` is not `S16LE`.
- Ignore a frame if `byte_count` does not match the actual file size.
- Ignore stale or repeated frames by tracking `sequence`.
- On underrun, output silence rather than blocking the audio engine.
- If the configured endpoint requires a different channel count or sample rate, resample or duplicate/downmix in the user-mode bridge before writing into the driver buffer.

Current status:

- `python .\bridge.py --frames 3 microphone-pipeline-check` writes and verifies this contract.
- `python .\bridge.py --frames 3 microphone-feeder-check` writes the contract and then reads it back as a future driver/APO/user-mode feeder would.
- `/api/v1/microphone/pipeline-check?frames=3` writes and verifies this contract for the local dashboard/server path.
- `/api/v1/microphone/feeder-check?frames=3` verifies both the producer and consumer side for the local dashboard/server path.
- The existing SysVAD patch currently changes identity, INF names, and endpoint naming only. It does not yet read this PCM contract from kernel mode or through a user-mode APO/service bridge.
- Windows will enumerate the SensorBridge microphone only after the development driver is test/prod signed, installed, and loaded.
