# SensorBridge Camera Installer Scripts

These scripts are camera-only helpers for the Windows receiver.

- `install-dev.ps1` creates a per-user desktop shortcut for `SensorBridge.App.exe`.
- `install-status.ps1` reports whether that shortcut and the app executable exist.
- `check-build-prereqs.ps1` reports basic tools needed for the camera app and DirectShow sender build.
- `uninstall-dev.ps1` removes the per-user shortcut.

They do not install drivers or modify Windows default devices.
