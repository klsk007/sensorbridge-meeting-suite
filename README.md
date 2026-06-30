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
        +-- Cable Microphone         -> Tencent Meeting microphone (may show as CABLE Output)
        +-- Tencent Meeting speaker  -> Cable Speaker / iPhone/iPad speaker (may show as CABLE Input)
```

## Current Scope

- Camera: wraps `sensorbridge-windows-clean`, which exposes `SensorBridge Camera` for meeting apps.
- Microphone: wraps `sensorbridge-microphone-windows`, which writes iPhone/iPad microphone audio to an already installed VB-CABLE route.
- Speaker: wraps `sensorbridge-speaker-windows`, which captures the meeting playback route and sends it to the iPhone/iPad speaker endpoint.
- Unified launcher and documentation live in `meeting-suite/` and `docs/`.

## Important Boundary

An iPhone/iPad app cannot register itself as a system-wide Windows camera, microphone, or speaker. Windows must provide the virtual devices. The mobile device is the media source and playback endpoint; this project is the Windows bridge that makes those streams selectable inside Tencent Meeting.

## Quick Start

1. Install VB-CABLE manually from VB-Audio: `https://vb-audio.com/Cable/`
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
- Microphone: `Cable Microphone` (Windows/Tencent may show the real device name `CABLE Output`)
- Speaker: `Cable Speaker` (Windows/Tencent may show the real device name `CABLE Input`) when you want the iPhone/iPad to act as the speaker

`Cable Microphone` and `Cable Speaker` are friendly role names. The real VB-CABLE
device names may still appear as `CABLE Output` and `CABLE Input` in Windows or
Tencent Meeting. In the desktop app, choose the devices as they appear in the
meeting app: microphone usually `CABLE Output`, speaker usually `CABLE Input`.
The app converts that meeting-facing choice to the opposite internal VB-CABLE
direction automatically. If those default names do not appear on the PC, click
`Refresh audio devices` and manually choose the matching meeting microphone and
speaker devices.

If speaker return sounds noisy or choppy, isolate the route by starting only one
audio direction with `-NoSpeaker` or `-NoMicrophone`. Two separate virtual audio
cable routes are recommended for the cleanest full-duplex setup, but the default
launcher keeps the WebRTC microphone and WebRTC speaker path used by the earlier
working version.

Run a local readiness check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\meeting-suite\Test-SensorBridgeMeeting.ps1 -IpadBaseUrl http://192.168.0.24:27180
```

## Build an Installer Package

Build the desktop app and create a portable installer ZIP:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Build-MeetingSuitePackage.ps1
```

The output is written to `dist\SensorBridgeMeetingSuite-<timestamp>.zip`.
Extract the ZIP on a target PC and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1
```

Optional setup steps are documented in `README-PACKAGE.md` inside the ZIP.
The package creates desktop/start menu shortcuts but does not silently install
VB-CABLE or other third-party system drivers.

Build a one-click GUI installer EXE with progress UI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Build-MeetingSuiteInstaller.ps1
```

The output is written to `dist\SensorBridgeMeetingSuiteSetup-<timestamp>.exe`.
Double-click it to extract the embedded package, copy files, create shortcuts,
optionally install Python dependencies, and show installation progress.
The package includes a local `wheelhouse` for the Python audio/video packages
and a bundled Python 3.12.3 runtime package. Target PCs do not need internet access
for Python or pip dependency installation. The build machine still needs
internet access when creating the installer so it can download those offline
resources.
The installer also includes an `安装前检查` button. Software that the installer
can legally bundle, such as Python 3.12.3, is installed automatically when
missing. Third-party software that cannot be bundled because of licensing, such
as VB-CABLE, is listed with a copyable official download link.

## Repository Layout

- `meeting-suite/`: unified launcher, readiness check, and operator notes.
- `meeting-suite/windows-app/`: unified Windows desktop app for launching and checking all bridges.
- `sensorbridge-windows-clean/`: camera bridge.
- `sensorbridge-microphone-windows/`: microphone bridge.
- `sensorbridge-speaker-windows/`: speaker bridge.
- `docs/`: architecture and Tencent Meeting setup notes.

## GitHub Publishing

This folder is already a local Git repository on `main`.

If GitHub CLI is installed and authenticated:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-ToGitHub.ps1 -Repository sensorbridge-meeting-suite
```

For a private repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-ToGitHub.ps1 -Repository sensorbridge-meeting-suite -Private
```

If you already created an empty GitHub repository in the browser:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Publish-ToGitHub.ps1 -RemoteUrl https://github.com/<owner>/sensorbridge-meeting-suite.git
```

Manual equivalent:

```powershell
git add .
git commit -m "Create SensorBridge Meeting Suite"
git branch -M main
git remote add origin https://github.com/<owner>/sensorbridge-meeting-suite.git
git push -u origin main
```
