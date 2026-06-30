# SensorBridge Meeting Suite Package

This package is the portable installer form of SensorBridge Meeting Suite.

## Install

Open PowerShell in this extracted folder and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1
```

The installer copies the suite to:

```text
%LOCALAPPDATA%\SensorBridgeMeetingSuite
```

It also creates:

- Desktop shortcut: `SensorBridge Meeting Suite`
- Start menu shortcut: `SensorBridge Meeting Suite`

## Optional Setup

The GUI installer includes an `安装前检查` button. Software that the installer
can legally bundle, such as Python 3.12.3, is installed automatically when
missing. Third-party software that cannot be bundled because of licensing, such
as VB-CABLE Driver Pack45, is listed with a copyable official download link.

Install Python bridge dependencies:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1 -InstallPythonDeps
```

The package includes a local `wheelhouse` with the Python audio/video wheels for
Windows x64 Python 3.10, 3.11, and 3.12, plus a bundled Python 3.12.3 runtime package.
When `wheelhouse` is present, the dependency step runs with
`--no-index --find-links .\wheelhouse`, so the target PC does not need internet
access for Python or pip packages. If `wheelhouse` is missing from a development
package, the script falls back to normal pip index behavior.

Register the virtual camera from an elevated PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1 -RegisterCamera
```

Run both optional steps:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1 -InstallPythonDeps -RegisterCamera
```

## External Dependencies

The package automatically installs bundled prerequisites when licensing allows
it. It does not silently install third-party system audio drivers.

Install these separately when needed:

- VB-CABLE for virtual microphone/speaker routing: `https://vb-audio.com/Cable/`

Use the VB-CABLE official page above to download, install, or uninstall the
driver package. The URL is plain text so it can be copied directly.

In the meeting app, select:

- Camera: `SensorBridge Camera`
- Microphone: `Cable Microphone` (may show as `CABLE Output`)
- Speaker: `Cable Speaker` (may show as `CABLE Input`)

Windows may still show the underlying VB-CABLE device names as `CABLE Output`
and `CABLE Input`. In the desktop app, choose devices as they appear in the
meeting app: microphone usually `CABLE Output`, speaker usually `CABLE Input`.
The app converts that meeting-facing choice to the opposite internal VB-CABLE
direction automatically. If the names are different on this PC, click
`Refresh audio devices` in the main app and choose the matching meeting
microphone and speaker devices.

If speaker return sounds noisy or choppy, isolate the route by starting only one
audio direction with `-NoSpeaker` or `-NoMicrophone`. Two separate virtual audio
cable routes are recommended for the cleanest full-duplex setup.

## Uninstall

Remove shortcuts only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-SensorBridgeMeeting.ps1
```

Remove shortcuts and installed files:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-SensorBridgeMeeting.ps1 -RemoveFiles
```

The uninstall script does not remove VB-CABLE or unregister the DirectShow camera filter automatically.
