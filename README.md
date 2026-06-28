# SensorBridge Meeting Suite

SensorBridge Meeting Suite combines the existing camera, microphone, and speaker bridges into one Windows-side project for using an iPhone or iPad as the meeting hardware source for Tencent Meeting and other desktop meeting apps.

The practical product shape is:

```text
iPhone/iPad camera + microphone + speaker endpoint
        |
        | WebRTC / local network
        v
Windows SensorBridge Meeting Suite
        |
        +-- SensorBridge Camera      -> Tencent Meeting camera
        +-- CABLE Output             -> Tencent Meeting microphone
        +-- Tencent Meeting speaker  -> CABLE Input -> iPhone/iPad speaker
```

## Current Scope

- Camera: wraps `sensorbridge-windows-clean`, which exposes `SensorBridge Camera` for meeting apps.
- Microphone: wraps `sensorbridge-microphone-windows`, which writes iPhone/iPad microphone audio to an already installed VB-CABLE route.
- Speaker: wraps `sensorbridge-speaker-windows`, which captures the meeting playback route and sends it to the iPhone/iPad speaker endpoint.
- Unified launcher and documentation live in `meeting-suite/` and `docs/`.

## Important Boundary

An iPhone/iPad app cannot register itself as a system-wide Windows camera, microphone, or speaker. Windows must provide the virtual devices. The mobile device is the media source and playback endpoint; this project is the Windows bridge that makes those streams selectable inside Tencent Meeting.

## Quick Start

1. Install VB-CABLE manually from VB-Audio.
2. Build/register the camera path from `sensorbridge-windows-clean` if `SensorBridge Camera` is not visible yet.
3. Start the iPhone/iPad SensorBridge service and note its base URL.
4. Start the unified bridge from the desktop app:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\windows-app\SensorBridge.Meeting.App\build.ps1
.\meeting-suite\windows-app\SensorBridge.Meeting.App\bin\Release\SensorBridge.Meeting.App.exe
```

Or start it from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Start-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

5. In Tencent Meeting:

- Camera: `SensorBridge Camera`
- Microphone: `CABLE Output`
- Speaker: set Tencent Meeting output to `CABLE Input` when you want the iPhone/iPad to act as the speaker

Run a local readiness check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Test-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

## Repository Layout

- `meeting-suite/`: unified launcher, readiness check, and operator notes.
- `meeting-suite/windows-app/`: unified Windows desktop app for launching and checking all bridges.
- `sensorbridge-windows-clean/`: camera bridge.
- `sensorbridge-microphone-windows/`: microphone bridge.
- `sensorbridge-speaker-windows/`: speaker bridge.
- `docs/`: architecture and Tencent Meeting setup notes.

## GitHub Publishing

This folder is already a local Git repository. After reviewing the generated project files, create the GitHub remote from your GitHub account and push:

```powershell
git add .
git commit -m "Create SensorBridge Meeting Suite"
git branch -M main
git remote add origin https://github.com/<owner>/sensorbridge-meeting-suite.git
git push -u origin main
```
