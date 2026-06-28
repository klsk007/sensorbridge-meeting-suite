# Audio Driver Plan

`SensorBridge Virtual Microphone` is planned as a SysVAD-derived virtual audio endpoint.

Development install requirements:

- Visual Studio
- Windows Driver Kit
- Administrator shell
- Test signing enabled for unsigned development drivers
- Reboot may be required after enabling test signing or installing/removing the driver

Production release requires Microsoft-compatible driver signing. The current app can receive mock audio frames, but Windows will not enumerate a SensorBridge microphone until the driver is built, test/prod signed, installed, and loaded by Windows.

Fetch the upstream SysVAD source through the manifest-driven third-party script:

```powershell
powershell -ExecutionPolicy Bypass -File ..\..\third_party\fetch-third-party.ps1 -Component Windows-driver-samples
```

The relevant upstream subdirectory is `third_party/src/Windows-driver-samples/audio/sysvad`. The fetch script also initializes the required `wil` submodule. Fetching source does not enable test signing, build the driver, install the INF, or make Windows enumerate a SensorBridge microphone.

Check local build prerequisites without installing anything:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\audio\build-dev.ps1
python .\bridge.py microphone-readiness
```

Fetch and attempt a development build:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\audio\build-dev.ps1 -Fetch -ApplySensorBridgePatch -Build
```

On a machine with Visual Studio DriverKit build tools, ATL, Spectre libraries, WDK, and WIL present, this produces a test-signed SysVAD package under:

```text
third_party\src\Windows-driver-samples\audio\sysvad\x64\Debug\package
```

The SensorBridge patch updates the root hardware id to `Root\SensorBridge_VirtualMicrophone` and writes SensorBridge-friendly provider, device, APO, and microphone endpoint names into the generated INFs. It deliberately keeps the upstream binary driver/sample structure until the real driver-side PCM injection path is implemented.

The Windows client now produces a concrete user-mode PCM handoff for that future injection path:

```powershell
python .\bridge.py --frames 3 microphone-pipeline-check
python .\bridge.py --frames 3 microphone-feeder-check
```

The command validates SensorBridge microphone frames and atomically writes:

```text
C:\ProgramData\SensorBridge\microphone\latest.pcm
C:\ProgramData\SensorBridge\microphone\latest.json
```

The same contract is available from the local server through `/api/v1/microphone/pipeline-check?frames=3`, using the server data directory. `/api/v1/microphone/feeder-check?frames=3` reads the handoff back as a future SysVAD/APO/user-mode feeder would. See `drivers\audio\SENSORBRIDGE_PCM_CONTRACT.md` for the exact fields and consumer rules. This is not yet a Windows audio endpoint by itself; it is the stable producer/consumer contract that a SysVAD/APO/user-mode bridge must consume after driver installation.

Check the development install boundary without changing the system:

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1
powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1
powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -VerifyOnly
powershell -ExecutionPolicy Bypass -File .\drivers\audio\test-signing.ps1 -Status
```

The status JSON reports `sensorbridge_package`, `root_hardware_id`, `can_install_now`, `install_blocks`, `reboot_required_before_install`, `verification`, and `creates_windows_microphone_now`. On a normal development machine, `can_install_now` remains false until Windows test signing is enabled and the machine has rebooted. `-VerifyOnly` performs the same PnP evidence check without attempting installation. `creates_windows_microphone_now` is true only when a SensorBridge `AudioEndpoint` is present, because that is the user-selectable microphone surface.

Install is intentionally explicit and guarded:

```powershell
# Administrator shell. This changes Windows boot configuration and requires a reboot.
powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -EnableTestSigning -ConfirmSystemChange ENABLE_TEST_SIGNING
shutdown /r /t 0

# Administrator shell, after reboot.
powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -InstallDriver -ConfirmSystemChange INSTALL_DRIVER
powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -VerifyOnly
```

After the reboot, the post-reboot helper combines install, PnP verification, WinRT media-device probing, and the microphone route verdict:

```powershell
# Plan-only, no system changes.
powershell -ExecutionPolicy Bypass -File .\drivers\audio\post-reboot-install.ps1

# Administrator shell, after test signing is enabled and the machine has rebooted.
powershell -ExecutionPolicy Bypass -File .\drivers\audio\post-reboot-install.ps1 -InstallAndVerify -ConfirmSystemChange INSTALL_MICROPHONE_DRIVER
powershell -ExecutionPolicy Bypass -File .\drivers\audio\post-reboot-install.ps1 -VerifyOnly
```

The guided wizard is plan-only by default. It refuses test-signing or driver-install actions unless the matching `-ConfirmSystemChange` token is present. Under the hood, the install script imports the generated test certificate and uses WDK `devcon.exe` for the root-enumerated base INF. It refuses to install when test signing is disabled. After install it re-runs the PnP verification and only reports `creates_windows_microphone_now: true` if Windows enumeration shows SensorBridge microphone evidence.
