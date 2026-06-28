# SensorBridge Microphone for Windows

This is a microphone-only extraction from `klsk007/sensorbridge-windows`.

It intentionally removes the product paths for camera, speaker return, acceleration, and WebRTC video. The production microphone path receives iPhone/iPad microphone audio over WebRTC/Opus and writes it to a user-installed VB-CABLE device. The app does not install, update, disable, or configure Windows audio drivers.

## Transport Status

Production microphone audio uses WebRTC/Opus through `POST /api/v2/webrtc/offer`. HTTP audio sample endpoints remain only for diagnostics and fallback checks.

Short-term quality tuning in the Windows app:

- `--output-gain` boosts decoded iPad microphone PCM before writing to `CABLE Input`; the GUI defaults to `1.5`. If the status reports low level, move the iPad closer before raising gain. The app keeps recommended gain conservative because high gain amplifies room noise and acoustic echo.
- `--low-cut-hz` defaults to `80` for the WebRTC microphone bridge. It removes DC/rumble before gain and VB-CABLE output. Use `--low-cut-hz 0` only for A/B diagnostics if speech sounds too thin.
- `outputClippedSamples` should stay at `0`. Lower Mic gain if it increases. The bridge now applies a soft limiter before VB-CABLE so sudden peaks are less harsh than hard clipping, but `outputLimitedSamples > 0` still means the gain is high enough to compress peaks.
- `--noise-gate-threshold` softly attenuates very low-level frames before `CABLE Input`; the GUI defaults to `0.0` because gate artifacts can sound like dropouts on quiet iPad microphone input. Try `8.0` only as a diagnostic if steady room noise is worse than occasional quiet-word cutoff.
- `playbackUnderflows`, `playbackUnderflowRatio`, `playbackUnderflowFrameRatio`, and `playbackDroppedFrames` show continuity. The frame ratio is the main quality signal because it measures how many requested output frames had to be silent-filled; callback ratio is diagnostic. The playback buffer no longer drops audio just to catch up latency; it trims only exact overflow frames, so `playbackOverflowDroppedFrames` is the key drop warning.
- The WebRTC bridge prebuffers about `1.5 s` before opening VB-CABLE output. This adds startup delay but reduces crackle caused by early playback underflows in the Python/PortAudio path. Use `--playback-prebuffer-ms` and `--playback-max-buffer-ms` for A/B diagnostics.
- `latencyState` reports the stability/latency tradeoff: `high_latency` means the bridge is likely more stable but delayed, while `low_latency` needs closer underflow monitoring.
- `recommendedPlaybackPrebufferMs` gives the next prebuffer value to try: raise it when continuity is unstable, lower it after a stable high-latency run.
- `outputPeakAbs` and `outputRms` show the processed signal written toward VB-CABLE after low-cut/gain/limiting/noise-gate. GUI level status is based on this output level, while `receiverPeakAbs` remains the raw decoded WebRTC level.
- `inputPeakDbfs`, `outputPeakDbfs`, `outputRmsDbfs`, and loopback `peakDbfs`/`rmsDbfs` show the same levels as dBFS. Values around `-50 dBFS` are extremely quiet for a microphone bridge; improve iPad-side source level before adding Windows gain. Level diagnosis now checks sustained RMS too, so a single transient peak no longer makes a very quiet run look healthy.
- `recommendedSourceLiftDb` estimates how much more iPad-side sustained RMS is needed to reach the short-term target (`targetSustainedRmsDbfs`, about `-40.77 dBFS`). Treat this as a source placement/source volume target, not as permission to add more Windows gain.
- `recommendedMicGain` is the conservative target gain, and `recommendedMicGainStep` is the safer next adjustment step shown in the GUI status card. Prefer the step value so noise and echo do not jump abruptly.
- `safeMicGainAction` explains whether the next gain step should actually be used. `hold_source_first` means the decoded iPad source is too weak and more Windows gain is unlikely to reach clean meeting level; improve the iPad-side source first. `safeMicGainCeiling` and `estimatedSafeGainRmsDbfs` show the conservative ceiling and what it would likely achieve.
- `sourceTooQuietForGainOnly: true` means the iPad microphone signal is so low that even the conservative next gain step is still weak; move the iPad closer or improve the source before raising Windows gain further. `gainOnlyLikelyToAmplifyNoise: true` makes that same risk explicit for UI/status consumers: more Windows gain will mostly amplify room noise and acoustic echo. In this state, the GUI Use button will not auto-apply a higher Mic gain, although it can still apply a prebuffer recommendation.
- `--monitor-gain` only boosts the WAV used for listening checks. It does not affect Tencent Meeting. The GUI defaults to `4.0` instead of the older `20.0` so room noise is not exaggerated, and the top volume card reports `recommendedMonitorGain` from the current output level. Recording status reports CABLE Output `levelState`, `peakDbfs`/`rmsDbfs`, and `recommendedSourceLiftDb`, plus monitor WAV `monitorPeakDbfs`/`monitorRmsDbfs`, `monitorClippedSamples`, `monitorClippedRatio`, and `monitorClipped`; if the playback WAV clips, lower Listen gain and record again before judging microphone quality.
- `webrtc-microphone --capture-path .\captures\diag.wav` writes layered diagnostic WAVs: `diag_receiver_raw.wav` is decoded WebRTC/Opus before Windows filtering, `diag_processed.wav` is the PCM written toward `CABLE Input`, and `diag_cable_output.wav` is what ordinary apps record from `CABLE Output`. If raw is already bad, fix the iPad/WebRTC source first; if processed is worse than raw, lower gain/filter/gate; if only CABLE Output is bad, focus on VB-CABLE/meeting capture.
- `diagnostic_captures.qualityAttribution.stage` gives the same comparison as a machine-readable diagnosis, such as `ipad_source_too_quiet`, `windows_processing_loss`, `windows_processing_too_hot`, `cable_loopback_loss`, or `audio_level_route_ok`. The GUI quality details show this layer diagnosis when diagnostic captures are enabled.
- The WebRTC result includes a `quality` object with `levelState`, `continuityState`, `echoCancellationState`, `windowsShortTermReady`, `fullShortTermReady`, and `recommendations`. `windowsShortTermReady` covers the Windows VB-CABLE bridge only. `fullShortTermReady` also requires iPad-side voice processing/AEC evidence.
- `quality.primaryIssue` gives the highest-priority short-term diagnosis for automation, logs, and the GUI headline, such as `source_too_quiet`, `level_too_hot`, `continuity_unstable`, `high_latency`, or `aec_unverified`. The GUI renders `primaryIssue` and `primaryRecommendation` as localized text while the raw JSON remains available below.
- `echoRiskState` is `controlled` only when iPad-side voice processing/AEC is reported. If it is `unknown` or `high`, Tencent Meeting can still receive `CABLE Output`, but use headphones or keep the iPad speaker off during tests.

Echo is not fixed by VB-CABLE or Windows-side gain. If the iPad speaker is active near the iPad microphone, the iPad app should use an iOS voice-processing audio session (`playAndRecord` / `voiceChat` / voice processing) so acoustic echo cancellation has access to the render/capture path.

A production-ready WebRTC run should show both sides:

- Windows receiver: `windows_receiver.audioPacketsReceived > 0`, `windows_receiver.audioBufferMs` reported, and audio written to `CABLE Input`.
- Windows loopback: `windows_loopback_capture.ordinaryAppsReceiveAudioFromEndpoint == true` proves `CABLE Output` can capture the same audio ordinary meeting apps should receive. `windows_loopback_capture.levelState` and `recommendedSourceLiftDb` show whether that ordinary-app capture is actually loud enough.
- Tencent Meeting: `tencent_meeting.state == verified_audio` means `CABLE Output` is selectable and loopback-verified. `selectable_unverified_audio` means the device is visible but audio has not been proven through the ordinary app capture path yet; the GUI recommends Test Cable/Record before joining a meeting.
- `tencent_meeting.readyForTencentMeeting` and `audioRouteReadyForTencentMeeting` describe only the Windows route. Check `windowsQualityReadyForTencentMeeting` for current level/continuity readiness; it now also requires `loopbackQualityReadyForTencentMeeting == true` so ordinary-app capture is loud enough. Check `fullQualityReadyForTencentMeeting` when iPad-side AEC is also verified.
- If `tencent_meeting.loopbackQualityReadyForTencentMeeting == false`, the GUI labels the meeting capture as too quiet even when the audio route itself is verified.
- `tencent_meeting.qualityPrimaryIssue` and `qualityPrimaryRecommendation` mirror the quality diagnosis so meeting readiness can explain why a verified route is still not quality-ready.
- `tencent_meeting.recommendedSourceLiftDb` mirrors the source-level gap, and the GUI top volume card shows it when the source is too quiet.
- When the route and Windows quality are ready but `qualityPrimaryIssue == aec_unverified`, the GUI labels Tencent Meeting as route-ready with echo risk instead of fully ready.
- Top-level `ok` still means the WebRTC/VB-CABLE route ran successfully. Use `readiness.state`, `readiness.message`, `readiness.nextAction`, `readiness.nextActionMessage`, `readiness.audioRouteReady`, `readiness.loopbackQualityReady`, `readiness.windowsQualityReady`, and `readiness.fullQualityReady` to decide whether the result is meeting-quality ready. The GUI top status and quality details show the next action near the top so users see whether to fix the iPad source, fix meeting loopback level, lower Windows gain, raise gain modestly, verify CABLE, or verify AEC.
- iPad upstream: `microphoneUpstreamPacketsSent > 0`, `microphoneUpstreamBytesSent > 0`, `microphoneUpstreamStatsFresh == true`, and `microphoneUpstreamState == sending_webrtc_opus`.
- Device route: VB-CABLE is present, and ordinary Windows apps can select `CABLE Output` as the microphone.

## Safe VB-CABLE Path

Install VB-CABLE manually from VB-Audio, then use this app as a user-mode bridge:

- app output device: `CABLE Input`
- Tencent Meeting microphone: `CABLE Output`

Do not bundle VB-CABLE with this app unless you have permission from VB-Audio. The app only detects and uses an already installed VB-CABLE device.

## Quick Start

```powershell
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 10 --output-gain 1.0 --low-cut-hz 80 --noise-gate-threshold 0 webrtc-microphone
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 10 --output-gain 1.0 --low-cut-hz 80 --noise-gate-threshold 0 --capture-path .\captures\diag.wav webrtc-microphone
python .\bridge.py --capture-path .\captures\diag.json diagnostic-summary
python .\bridge.py --base-url http://192.168.0.24:27180 --relay-url http://192.168.0.23:27181 connection-check
python .\bridge.py short-term-status
python .\bridge.py --base-url http://192.168.0.23:27181 --duration-seconds 4 --gain-values 0.75,1.0,1.25 gain-tune
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 5 webrtc-loopback-check
python .\bridge.py --duration-seconds 10 --capture-path .\captures\sample.wav --monitor-gain 4 vbcable-output-capture
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 0 --output-gain 1.0 --low-cut-hz 80 webrtc-microphone
python .\bridge.py --base-url http://192.168.0.24:27180 vbcable-product-status
python .\bridge.py --base-url http://192.168.0.24:27180 --frames 5 vbcable-loopback-check
python .\bridge.py --base-url http://192.168.0.24:27180 --frames 0 pump-vbcable
python .\bridge.py diagnostic-bundle
powershell -ExecutionPolicy Bypass -File .\windows-app\SensorBridge.Microphone.App\build.ps1
powershell -ExecutionPolicy Bypass -File .\windows-app\SensorBridge.Microphone.App\install-shortcut.ps1
python .\bridge.py desktop-shortcut-status
.\windows-app\SensorBridge.Microphone.App\bin\Release\SensorBridge.Microphone.App.exe
.\windows-app\SensorBridge.Microphone.App\bin\Release\SensorBridge.Microphone.App.exe --language zh-CN
```

`--duration-seconds 0 webrtc-microphone` runs until stopped. The GUI Start button uses this persistent WebRTC mode. `pump-vbcable` remains the legacy HTTP PCM diagnostic bridge. `install-shortcut.ps1` creates the current user's desktop shortcut and automatically builds the app first if the Release EXE is missing.

The GUI has Base URL, Output, Mic gain, Listen gain, Noise gate, Prebuffer, and Language fields plus Start/Stop/Refresh/Test Cable buttons. Language can be switched between English and Chinese, and status text follows the selected language. Before Start/Refresh/Test/Tune/Record, the GUI runs a backend preflight and automatically switches the Base URL to the relay URL when the relay is the reachable target. Mic gain is applied before audio is written to `CABLE Input`; start around `1.0` and adjust in small steps from the status recommendation so the bridge does not amplify room noise, echo, or clipping. The Tune button runs `gain-tune` from the GUI, writes per-gain WAV/JSON reports, and fills the recommended Mic gain; restart Start if the bridge is already running. The tray menu also exposes Tune gain, Open diagnostics folder, and Bundle diagnostics so generated WAV/JSON evidence is easy to find or share as a zip. Prebuffer defaults to `1500` ms after repeated clean loopback runs; raise it toward `2000` ms if continuity becomes unstable, or try `1200` ms only after a stable run. The Use button beside Prebuffer fills in recommended bridge settings, including `recommendedMicGainStep`, `recommendedMonitorGain`, and `recommendedPlaybackPrebufferMs`; it is enabled only when those recommendations differ from the current GUI/running bridge settings. When the source is too quiet for gain-only correction, Use skips Mic gain so it does not amplify room noise and echo, but it can still fill Listen gain for the next quality-check playback WAV. The top WebRTC status shows the source-too-quiet state directly and also calls out level-too-hot and continuity-unstable states before the generic tuning message. The status names edited bridge settings such as Mic gain, Gate, or Prebuffer that need restart to apply. Noise gate only attenuates very low-level frames; set it to `0` if it cuts off quiet speech. Listen gain only affects the playback WAV generated by the quality check, and defaults lower than older builds so background noise is not exaggerated. The WebRTC status card now surfaces level, continuity, AEC state, Tencent Meeting audio verification, and localized short-term quality recommendations before the raw JSON. It also has Record/Play quality-check buttons. Record first warms up WebRTC and waits until `CABLE Output` is actually receiving audio, then starts an open-ended recording. Pressing the same button again stops it after recording a short delayed-audio tail, saves a raw WAV, and saves a monitor WAV with gain for listening. Play replays the latest monitor WAV through the normal Windows playback device. Start speaking after the status changes from preparing to recording.

Each GUI WebRTC refresh and each CLI `webrtc-microphone` / `webrtc-loopback-check` run writes `captures/latest_webrtc_status.json`, `captures/latest_webrtc_summary.json`, and `captures/latest_webrtc_summary.txt`; send the text or summary file when reporting short-term microphone quality to the iPad/Mac side. `diagnostic-bundle` packages the latest JSON/TXT/WAV/LOG evidence plus desktop shortcut and VB-CABLE status snapshots into `captures/bundles/*.zip`.

Use `gain-tune` when the route works but the sound is too quiet, noisy, or distorted. It runs the WebRTC/VB-CABLE loopback for each gain value, saves one WAV and one JSON report per gain under `captures/gain_tune`, and recommends the most conservative usable next gain. It is a diagnostic helper only; it does not install drivers or change Windows audio settings.

- backend reachability
- whether iPad WebRTC microphone upstream stats are fresh
- Windows WebRTC receiver packet/frame counts and audio buffer duration
- whether `CABLE Output` records non-silent audio during the WebRTC loopback check
- whether `CABLE Input` is available for playback
- whether Tencent Meeting should be able to select `CABLE Output`
- whether `CABLE Output` can actually be recorded by ordinary apps during a loopback test

## Important Truth Boundary

Receiving WebRTC/Opus audio is not the same as creating a Windows input device. In the safe path, VB-CABLE provides the Windows input device and this app only sends audio to it from user mode.

`microphone-product-status` writes the latest S16LE PCM to:

```text
C:\ProgramData\SensorBridge\microphone\latest.pcm
C:\ProgramData\SensorBridge\microphone\latest.json
```

Normal Windows apps should select `CABLE Output` when VB-CABLE is installed. The legacy SysVAD driver workflow remains in the repo for isolated driver development, but it is not the safe default path and should not be run on a primary machine.

## Commands

```powershell
python .\bridge.py --base-url http://192.168.0.24:27180 start-audio
python .\bridge.py --base-url http://192.168.0.24:27180 sample-audio
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 10 --output-gain 1.0 --low-cut-hz 80 --noise-gate-threshold 0 webrtc-microphone
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 10 --output-gain 1.0 --low-cut-hz 80 --noise-gate-threshold 0 --capture-path .\captures\diag.wav webrtc-microphone
python .\bridge.py --capture-path .\captures\diag.json diagnostic-summary
python .\bridge.py --base-url http://192.168.0.24:27180 --relay-url http://192.168.0.23:27181 connection-check
python .\bridge.py short-term-status
python .\bridge.py --base-url http://192.168.0.23:27181 --duration-seconds 4 --gain-values 0.75,1.0,1.25 gain-tune
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 5 webrtc-loopback-check
python .\bridge.py --duration-seconds 10 --capture-path .\captures\sample.wav --monitor-gain 4 vbcable-output-capture
python .\bridge.py --capture-path .\captures\sample.wav --stop-file .\captures\sample.stop --monitor-gain 4 --tail-seconds 4 vbcable-output-record
python .\bridge.py --base-url http://192.168.0.24:27180 --duration-seconds 0 --output-gain 1.0 --low-cut-hz 80 --noise-gate-threshold 0 webrtc-microphone
python .\bridge.py vbcable-status
python .\bridge.py --base-url http://192.168.0.24:27180 vbcable-product-status
python .\bridge.py --base-url http://192.168.0.24:27180 --frames 5 vbcable-loopback-check
python .\bridge.py --base-url http://192.168.0.24:27180 --frames 0 pump-vbcable
python .\bridge.py diagnostic-bundle
python .\bridge.py --base-url http://192.168.0.24:27180 --frames 5 microphone-pipeline-check
python .\bridge.py microphone-feeder-check
python .\bridge.py media-devices
python .\bridge.py microphone-route-status
python .\bridge.py microphone-readiness
python .\bridge.py microphone-install-plan
python .\bridge.py microphone-install-status
python .\bridge.py microphone-test-signing-status
```

## Legacy Driver Path

The `drivers/audio` folder keeps the guarded SysVAD development-driver workflow from the source repository. This is not the recommended path for normal users or primary machines.

```powershell
powershell -ExecutionPolicy Bypass -File .\third_party\fetch-third-party.ps1 -Component Windows-driver-samples
powershell -ExecutionPolicy Bypass -File .\drivers\audio\build-dev.ps1 -ApplySensorBridgePatch -Build
powershell -ExecutionPolicy Bypass -File .\drivers\audio\test-signing.ps1 -Enable
powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -Install
powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -VerifyOnly
```

These commands may require Visual Studio driver components, WDK, administrator elevation, test signing, and a reboot.
