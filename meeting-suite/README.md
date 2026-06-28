# Meeting Suite Operator Notes

This folder is the single entry point for the combined product.

## Launch

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

By default the launcher starts all three bridges:

- camera service from `sensorbridge-windows-clean`
- microphone WebRTC bridge from `sensorbridge-microphone-windows`
- speaker WebRTC bridge from `sensorbridge-speaker-windows`

Use switches to start only part of the suite:

```powershell
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoSpeaker
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoCamera
.\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180 -NoMicrophone
```

## Tencent Meeting Devices

- Camera: `SensorBridge Camera`
- Microphone: `CABLE Output`
- Speaker: `CABLE Input`

For clean two-way audio, use two separate virtual cable routes when possible: one for microphone injection and one for speaker return. With one VB-CABLE route, microphone and speaker paths can mix if both directions are active.

## Readiness Check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Test-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

The check verifies local component folders, Python availability, iPhone/iPad service reachability, and the audio route probes exposed by the microphone/speaker bridges.
