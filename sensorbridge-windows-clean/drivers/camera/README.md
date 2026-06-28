# Camera Driver Plan

`SensorBridge Virtual Camera` currently has a Windows 11 Media Foundation development path.

Development install requirements:

- Windows 11
- Visual Studio with C++ workload
- Windows SDK
- Administrator shell for COM registration and virtual camera registration

The recommended upstream sample is `smourier/VCamSample` under the MIT license. Use the manifest-driven fetch script to clone the upstream source into `third_party/src/VCamSample`:

```powershell
powershell -ExecutionPolicy Bypass -File ..\..\third_party\fetch-third-party.ps1 -Component VCamSample
```

This only fetches source. The development registration script can register the patched sample as a session-lifetime Windows 11 Media Foundation virtual camera named `SensorBridge Camera`. This proves Windows camera apps can enumerate a virtual camera.

On Windows 10 or any runtime without `mfsensorgroup.dll!MFCreateVirtualCamera`, this provider is not enough for product completion. The setup/status commands report `mf_virtual_camera_supported_by_current_os=false`, skip VCamSample launch, and route product setup toward the DirectShow fallback. Product completion still requires a provider that normal Windows apps enumerate as `SensorBridge Camera`.

For the SensorBridge frame path, apply the local SensorBridge patch before building. The patch brands the development device as `SensorBridge Camera` and makes `VCamSampleSource\FrameGenerator` draw `C:\ProgramData\SensorBridge\camera\latest.bmp` every frame, then fall back to the upstream HSL test pattern if no SensorBridge frame is available.

Check local build prerequisites without installing anything:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\build-dev.ps1
```

Fetch and attempt a development build:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\build-dev.ps1 -Fetch -ApplySensorBridgePatch -Build
```

Register and start the development virtual camera from an administrator shell:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\register-dev.ps1 -Register -Start
```

For Windows 10 fallback work, use the pinned MIT `softcam` DirectShow component:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\directshow\build-dev.ps1 -Fetch -Build
python .\bridge.py directshow-camera-build-status
python .\bridge.py directshow-camera-register-status
```

If the build artifacts are present, register the DirectShow filter explicitly from an Administrator shell:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\directshow\register-dev.ps1 -Register
```

This writes DirectShow/COM registration only; it does not reboot, enable test signing, or install non-camera drivers. Registration evidence is not enough to claim camera support. Verify Windows enumeration and open/capture before marking `SensorBridge Camera` complete.

During registration, `register-dev.ps1` may briefly stop and restart the Windows Camera Frame Server service so the previously registered `VCamSampleSource.dll` can be replaced cleanly.

Verify with:

```powershell
python .\bridge.py directshow-camera-open-status
dotnet run --project .\tools\CameraFrameProbe\CameraFrameProbe.csproj -- --output .\data\camera-probe-sensorbridge.bmp
python .\tools\system_check.py
```

`CameraFrameProbe` opens `SensorBridge Camera` through WinRT `MediaCapture` and captures a BMP frame, proving the registered virtual camera can be opened by Windows APIs. The patched development virtual camera reads the BMP frame-file while `VCamSample.exe` is running.

Stop or unregister it:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\camera\register-dev.ps1 -Stop
powershell -ExecutionPolicy Bypass -File .\drivers\camera\register-dev.ps1 -Unregister
```
