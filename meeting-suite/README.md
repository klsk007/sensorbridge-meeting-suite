# Meeting Suite Operator Notes

This folder is the single entry point for the combined product.

## Launch

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

By default the launcher starts the selected bridges:

- camera service from `sensorbridge-windows-clean`
- microphone VB-CABLE bridge from `sensorbridge-microphone-windows`
- speaker WebRTC/Opus bridge from `sensorbridge-speaker-windows`

If speaker return sounds noisy or choppy, isolate the route by starting only one
audio direction:

```powershell
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoSpeaker
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoMicrophone
```

Use switches to start only part of the suite:

```powershell
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoSpeaker
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoCamera
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoMicrophone
```

## Tencent Meeting Devices

- Camera: `SensorBridge Camera`
- Microphone: `Cable Microphone` (may show as `CABLE Output`)
- Speaker: `Cable Speaker` (may show as `CABLE Input`)

`Cable Microphone` and `Cable Speaker` are friendly aliases used by this suite.
The real VB-CABLE device names usually remain `CABLE Output` and `CABLE Input`.
If a driver version or Windows language shows different names, use the unified
desktop app's `Refresh audio devices` button and select the matching channels
manually. Select them as they appear in the meeting app: microphone usually
`CABLE Output`, speaker usually `CABLE Input`. The desktop app converts that to
the opposite internal VB-CABLE direction automatically.

For clean two-way audio, two separate virtual cable routes are still preferable:
one for microphone injection and one for speaker return. The default launcher
uses WebRTC microphone plus WebRTC speaker, matching the earlier working route.

## Readiness Check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Test-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

The check verifies local component folders, Python availability, iPhone/iPad service reachability, and the audio route probes exposed by the microphone/speaker bridges.

## One-Minute Core Test

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Test-OneMinuteCore.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

This no-Tencent test verifies camera picture/FPS, Windows virtual camera visibility, microphone input level through `CABLE Output`, speaker playback return through the iPad speaker endpoint, and one minute of simultaneous process stability.
