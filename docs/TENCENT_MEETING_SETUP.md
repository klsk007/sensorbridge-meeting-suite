# Tencent Meeting Setup

## Windows Devices

Open Tencent Meeting audio/video settings and select:

- Camera: `SensorBridge Camera`
- Microphone: `Cable Microphone` (may show as `CABLE Output`)
- Speaker: `Cable Speaker` (may show as `CABLE Input`)

The text in parentheses is the real VB-CABLE device name Windows/Tencent may show.
Use the friendly alias to remember the role:

- `Cable Microphone` means the meeting microphone input. Internally, the bridge writes the iPhone/iPad microphone into the VB-CABLE playback side, usually `CABLE Input`, so Tencent can receive it from the recording side.
- `Cable Speaker` means the meeting speaker/output target. Internally, the bridge captures the VB-CABLE recording side, usually `CABLE Output`, and sends it to the iPhone/iPad speaker.

If the PC shows different VB-CABLE names, open the SensorBridge desktop app,
click `Refresh audio devices`, and choose the matching channels manually:

- Meeting microphone selection: the microphone device shown in the meeting app, usually `CABLE Output`.
- Meeting speaker selection: the speaker device shown in the meeting app, usually `CABLE Input`.

The desktop app converts those meeting-facing choices to the opposite internal
VB-CABLE direction automatically.

If speaker return sounds noisy or choppy, isolate the route by testing one audio
direction at a time with `-NoSpeaker` or `-NoMicrophone`. Two separate virtual
audio cable routes are recommended for the cleanest full-duplex setup.

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
- Speaker audio loops back into microphone or the iPad plays noise: first test with `-NoSpeaker` and `-NoMicrophone` to isolate the noisy direction. For the cleanest full-duplex route, use one virtual cable per audio direction.
