# SensorBridge Windows

SensorBridge Windows is a camera-only Windows receiver for using an iPad camera as `SensorBridge Camera`.

## Product Path

The only product path is:

`iPad Camera -> WebRTC/H.264 low-latency transport -> Windows receiver/decoder -> Windows virtual camera -> Windows Camera or meeting software`

The Windows app starts Product Mode, connects the WebRTC receiver, starts the Windows virtual camera sender, and displays:

- `activeCameraTransport`
- `receivedFps`
- `decodedFps`
- `virtualCameraFps`
- `latestFrameAgeMs`
- `estimatedLatencyMs`
- `droppedFrames`
- `normalWindowsCameraVisible`

If WebRTC is unavailable or media is not decoded, `SensorBridge Camera` is reported unavailable. Product Mode does not start an alternate frame-polling path.

## Removed Scope

This camera-only workspace removes product support for non-camera features. The HTTP service returns `410 camera_only_feature_removed` for removed routes.

## Run

```powershell
py -3 sensorbridge.py --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

To start Product Mode through the launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-app\Start-SensorBridgeApp.ps1 -ProductMode
```

## Build Windows App

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows-app\SensorBridge.App\build.ps1
```

## Test

```powershell
py -3 -m pytest -q
```

For meeting-software acceptance, run the stricter check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\meeting-camera-acceptance.ps1
```

This script intentionally fails unless the camera-only service is running, `SensorBridge Camera` opens through DirectShow, the WinRT/MediaCapture proxy check can run and pass, and Tencent Meeting has been manually confirmed with `SensorBridge Camera` selected and a live preview visible. DirectShow success alone is not Tencent Meeting success.

## Key Files

- `sensorbridge.py`: local HTTP service and Product Mode orchestration.
- `bridgeclient/webrtc_receiver.py`: optional `aiortc` Windows WebRTC receiver and newest-frame-wins decoded frame queue.
- `bridgeclient/video_sink.py`: frame sink used by the virtual camera sender path.
- `bridgeclient/directshow_camera.py`: DirectShow virtual camera build/register/sender helpers.
- `tools/meeting-camera-acceptance.ps1`: conservative meeting-software acceptance check.
- `static/dashboard.html` and `static/dashboard.js`: camera-only dashboard.
- `windows-app/SensorBridge.App/Program.cs`: camera-only WinForms launcher/status shell.
