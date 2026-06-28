# Tencent Meeting Setup

## Windows Devices

Open Tencent Meeting audio/video settings and select:

- Camera: `SensorBridge Camera`
- Microphone: `CABLE Output`
- Speaker: `CABLE Input`

## Start Order

1. Start the iPhone/iPad SensorBridge app.
2. Confirm the iPhone/iPad service URL, for example `http://192.168.0.24:27180`.
3. Start the Windows suite:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

4. Open Tencent Meeting settings and select the devices above.
5. Use Tencent Meeting's camera preview, microphone level, and speaker test to verify the route.

## Expected Signals

- Camera preview shows the iPhone/iPad camera feed.
- Microphone test moves when speaking near the iPhone/iPad.
- Speaker test plays through the iPhone/iPad.

## Common Problems

- `SensorBridge Camera` is missing: register/build the camera path from `sensorbridge-windows-clean`.
- `CABLE Output` or `CABLE Input` is missing: install VB-CABLE manually and restart the affected apps.
- Microphone is visible but too quiet: run the microphone bridge quality check and adjust source placement before raising Windows gain.
- Speaker audio loops back into microphone: use headphones, lower speaker volume, enable voice-processing/AEC on the mobile side, or use separate virtual cable routes.
