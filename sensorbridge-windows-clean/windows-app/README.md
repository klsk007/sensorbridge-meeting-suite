# SensorBridge Windows App

`SensorBridge.App.exe` is a WinForms launcher for the camera-only SensorBridge Windows receiver.

It starts Product Mode, embeds the compact camera dashboard, and shows native status for:

- WebRTC camera transport
- SensorBridge Camera readiness
- next camera action/blocker

The app stays available from the Windows notification area. Closing the main window hides it to the tray; the tray menu can reopen the main window, open the dashboard, or exit and shut down the local camera service.

Build:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows-app\SensorBridge.App\build.ps1
```

Run Product Mode from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-app\Start-SensorBridgeApp.ps1 -ProductMode
```
