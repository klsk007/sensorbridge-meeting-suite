from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unified_meeting_app_targets_all_three_meeting_devices() -> None:
    source = ROOT / "meeting-suite" / "windows-app" / "SensorBridge.Meeting.App" / "Program.cs"
    text = source.read_text(encoding="utf-8")

    assert "Start-SensorBridgeMeeting.ps1" in text
    assert "Test-SensorBridgeMeeting.ps1" in text
    assert "SensorBridge Camera" in text
    assert "CABLE Output" in text
    assert "CABLE Input" in text
    assert "Cable Microphone" in text
    assert "Cable Speaker" in text
    assert "Meeting microphone" in text
    assert "Meeting speaker" in text
    assert "RefreshAudioDevices" in text
    assert "MicrophoneOutputDevice" in text
    assert "SpeakerCaptureDevice" in text
    assert 'public string MicrophoneOutputDevice = "CABLE Output";' in text
    assert 'public string SpeakerCaptureDevice = "CABLE Input";' in text
    assert 'public string Language = "en";' in text
    assert 'return "en";' in text
    assert "ResolveMicrophoneBridgePlaybackDevice" in text
    assert "ResolveSpeakerBridgeCaptureDevice" in text
    assert "ValidateStartSelection" in text
    assert "same virtual audio cable" in text
    assert "validationError + Environment.NewLine" in text
    assert "Environment.TickCount != Int32.MinValue" not in text
    assert " -MicrophoneMode webrtc" in text
    assert " -SpeakerMode webrtc" in text
    assert "ComboBoxStyle.DropDown" in text
    assert "Camera" in text
    assert "Microphone" in text
    assert "Speaker" in text
    assert "ApplyLanguage" in text
    assert "DropDownStyle.DropDownList" not in text
    assert "_languageCombo" not in text
    assert "_languageLabel" not in text
    assert 'case "btn_start": return "Start";' in text
    assert 'case "btn_stop": return "Stop";' in text
    assert "AddButton(actionRow, delegate { RunReadinessCheck(); })" not in text
    assert "AddButton(actionRow, delegate { OpenSetupDoc(); })" not in text
    assert "_talkButton = AddButton(actionRow" not in text
    assert "PillButton" in text
    assert "ToggleSwitch" in text
    assert "Color.FromArgb(52, 199, 89)" in text
    assert "StopSuiteNow();" in text
    assert "Stop bridge processes started by this project" in text
    assert "TalkRequested += delegate(bool talking) { SetPushToTalk(talking); }" in text
    assert "SetPushToTalk(false)" in text
    assert "FloatingTalkForm" in text
    assert "RoundTalkButton" in text
    assert "TalkRequested" in text
    assert "CloseRequested" in text
    assert "BuildFloatingTalkWindow" in text
    assert "ToggleFloatingTalkWindow" in text
    assert "CloseFloatingTalkWindow" in text
    assert "_floatingWindowButton" in text
    assert "btn_float_open" in text
    assert "btn_float_close" in text
    assert "float_close" in text
    assert "ContextMenuStrip" in text
    assert "_floatingTalkForm.SetTalkEnabled(canTalk)" in text
    assert "_floatingTalkForm.SetTalking(talking)" in text
    assert "_meetingDevices.Visible = false" in text
    assert "_details.Visible = false" in text
    assert "new RowStyle(SizeType.Absolute, 0)" in text
    assert "PushToTalkControlPath" in text
    assert "IEnumerable array = parsed as IEnumerable" in text
    assert "parsed is string" in text


def test_unified_launcher_starts_camera_microphone_and_speaker_components() -> None:
    launcher = ROOT / "meeting-suite" / "Start-SensorBridgeMeeting.ps1"
    text = launcher.read_text(encoding="utf-8")
    readiness = (ROOT / "meeting-suite" / "Test-SensorBridgeMeeting.ps1").read_text(encoding="utf-8")
    combined = (ROOT / "meeting-suite" / "meeting_audio_bridge.py").read_text(encoding="utf-8")

    assert "sensorbridge-windows-clean" in text
    assert "sensorbridge-microphone-windows" in text
    assert "sensorbridge-speaker-windows" in text
    assert "meeting_audio_bridge.py" in text
    assert "webrtc-duplex" in text
    assert "UseCombinedMedia" in text
    assert "UseCombinedBridge" in text
    assert "$UseCombinedMedia = (-not $NoCamera -and ($UseWebRtcMicrophone -or $UseWebRtcSpeaker))" in text
    assert "$UseCombinedBridge = ($UseCombinedAudio -or $UseCombinedMedia)" in text
    assert '"--no-microphone"' in text
    assert '"--no-speaker"' in text
    assert "PushToTalk" in text
    assert "UTF8Encoding" in text
    assert '"--push-to-talk-control"' in text
    assert '"--push-to-talk-default-muted"' in text
    assert '"--speaker-push-to-talk-duck-gain"' in text
    assert '"--speaker-push-to-talk-tail-ms"' in text
    assert 'Name "meeting-media"' in text
    assert "if (-not $UseCombinedBridge -and -not $NoSpeaker)" in text
    assert "combinedAudio" in text
    assert "--enable-video" in text
    assert "combinedMedia" in text
    assert "sensorbridge.py" in text
    assert "bridge.py" in text
    assert "speaker_bridge.py" in text
    assert "pump-vbcable" in text
    assert '"stream"' in text
    assert "webrtc-microphone" in text
    assert "webrtc-speaker" in text
    assert "MicrophoneMode" in text
    assert "SpeakerMode" in text
    assert '[string]$MicrophoneMode = "webrtc"' in text
    assert '[string]$SpeakerMode = "webrtc"' in text
    assert "Assert-CameraPortAvailable" in text
    assert "Get-NetTCPConnection" in text
    assert "Close the older SensorBridge app" in text
    assert "if (-not $NoCamera -and -not $UseCombinedBridge)" in text
    assert "CableInputDevice" in text
    assert "SpeakerCaptureDevice" in text
    assert '"--output-device", $CableInputDevice' in text
    assert '"--capture-device", $SpeakerCaptureDevice' in text
    assert "Resolve-PythonInvocation" in readiness
    assert readiness.index('Test-CommandAvailable "py"') < readiness.index('Test-CommandAvailable "python"')
    assert "microphoneBridgePlaybackDevice" in readiness
    assert "speakerBridgeCaptureDevice" in readiness
    assert "Start-DetachedProcess" in text
    assert "Win32_ProcessStartup" in text
    assert "ShowWindow = 0" in text
    assert "Win32_Process" in text
    assert "sensorbridge-windows-clean\\sensorbridge.py" in text
    assert "sensorbridge-microphone-windows\\bridge.py" in text
    assert "sensorbridge-speaker-windows\\speaker_bridge.py" in text
    assert '"bridge.py"' not in text
    assert "ConvertTo-Json -InputObject @($Started)" in text
    assert "single_webrtc_peer_connection" in combined
    assert "CableOutputAudioTrack" in combined
    assert "_consume_audio_track" in combined
    assert "FrameFileVideoSink" in combined
    assert "transportOk" in combined
    assert "microphoneOk" in combined
    assert "speakerOk" in combined
    assert "cameraOk" in combined
    assert "_is_connected_state(peer_connection_state)" in combined
    assert "_is_connected_state(status_peer_state)" in combined
    assert "receiver.receiver_state == \"receiving_webrtc_opus\"" in combined
    assert "receiver.audio_frames_written > 0" in combined
    assert "_exception_summary" in combined
    assert "_merge_video_receiver_stats" in combined
    assert "videoReceiverState" in combined
    assert "virtualCameraFps" in combined
    assert "FPS_WINDOW_SECONDS" in combined
    assert "deque" in combined
    assert "should_accept_frame" in combined
    assert "asyncio.to_thread" in combined
    assert "--no-microphone" in combined
    assert "--no-speaker" in combined
    assert "--push-to-talk-control" in combined
    assert "--push-to-talk-default-muted" in combined
    assert "--speaker-push-to-talk-duck-gain" in combined
    assert "--speaker-push-to-talk-tail-ms" in combined
    assert 'pc.addTransceiver("video", direction="recvonly")' in combined


def test_unified_meeting_app_hides_helper_console_windows() -> None:
    source = ROOT / "meeting-suite" / "windows-app" / "SensorBridge.Meeting.App" / "Program.cs"
    text = source.read_text(encoding="utf-8")

    assert "CreateNoWindow = true" in text
    assert "ProcessWindowStyle.Hidden" in text
    assert "Stop-SensorBridgeMeeting.ps1" in text
    assert "KillProcessTree" in text
    assert "StopSuiteNow" in text
    assert "_stopInProgress" in text
    assert "ThreadPool.QueueUserWorkItem" in text
    assert 'RunPowerShellScript("Stop-SensorBridgeMeeting.ps1", BuildStopArguments(pids), 30000)' in text
    assert "e.Cancel = true" in text
    assert "HideToTray();" in text
    assert "_trayExitItem" in text
    assert "_allowExit = true; Close();" in text


def test_unified_stop_script_cleans_project_scoped_helpers() -> None:
    script = ROOT / "meeting-suite" / "Stop-SensorBridgeMeeting.ps1"
    text = script.read_text(encoding="utf-8")

    assert "sensorbridge-windows-clean\\sensorbridge.py" in text
    assert "sensorbridge-microphone-windows\\bridge.py" in text
    assert "sensorbridge-speaker-windows\\speaker_bridge.py" in text
    assert "meeting-suite\\meeting_audio_bridge.py" in text
    assert "SensorBridge.DirectShowSender.exe" in text
    assert "DryRun" in text


def test_unified_launcher_primes_camera_media_and_virtual_device() -> None:
    launcher = ROOT / "meeting-suite" / "Start-SensorBridgeMeeting.ps1"
    text = launcher.read_text(encoding="utf-8")

    assert "/api/v1/video/start" in text
    assert "/api/v1/audio/start" in text
    assert "Ensure-CameraVirtualDevice" in text
    assert "sender-dev.ps1" in text
    assert "register-dev.ps1" in text


def test_one_minute_core_test_covers_no_tencent_acceptance_goals() -> None:
    script = ROOT / "meeting-suite" / "Test-OneMinuteCore.ps1"
    text = script.read_text(encoding="utf-8")

    assert "camera_has_picture_and_fps" in text
    assert "virtual_camera_visible_to_windows" in text
    assert "microphone_has_input_level" in text
    assert "speaker_playback_return_route" in text
    assert "three_modules_one_minute_no_crash" in text
    assert "vbcable-loopback-check" in text
    assert "route-test" in text


def test_readme_exposes_single_app_build_and_run_path() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "SensorBridge Meeting Suite" in text
    assert "SensorBridge.Meeting.App.exe" in text
    assert "meeting-suite/windows-app" in text
    assert "Tencent Meeting" in text
    assert "Cable Microphone" in text
    assert "may show the real device name `CABLE Output`" in text
    assert "Cable Speaker" in text
    assert "may show the real device name `CABLE Input`" in text
    assert "Refresh audio devices" in text
    assert "manually choose the matching meeting microphone and" in text


def test_gui_installer_exposes_copyable_vbcable_help() -> None:
    installer = (ROOT / "packaging" / "windows-installer" / "SensorBridgeMeetingInstaller.cs").read_text(
        encoding="utf-8"
    )
    install_script = (ROOT / "packaging" / "Install-SensorBridgeMeeting.ps1").read_text(encoding="utf-8")
    package_script = (ROOT / "scripts" / "Build-MeetingSuitePackage.ps1").read_text(encoding="utf-8")
    installer_script = (ROOT / "scripts" / "Build-MeetingSuiteInstaller.ps1").read_text(encoding="utf-8")
    requirements = (ROOT / "packaging" / "python-runtime-requirements.txt").read_text(encoding="utf-8")
    package_readme = (ROOT / "packaging" / "README-PACKAGE.md").read_text(encoding="utf-8")
    main_readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "https://vb-audio.com/Cable/" in installer
    assert "https://vb-audio.com/Cable/" in install_script
    assert "https://vb-audio.com/Cable/" in package_readme
    assert "https://vb-audio.com/Cable/" in main_readme
    assert "SENSORBRIDGE_VBCABLE_MISSING" in installer
    assert "SENSORBRIDGE_VBCABLE_MISSING" in install_script
    assert "CopyVbCableUrl" in installer
    assert "_vbCableUrlText" in installer
    assert "离线安装/修复 Python 音视频依赖" in installer
    assert "安装前检查" in installer
    assert "推荐：Python 3.10+" in installer
    assert "VBCABLE_Driver_Pack45" in installer
    assert "满足后无需更新" in installer
    assert "无需重装或更新" in installer
    assert "名字不同可在主程序手动选择" in installer
    assert "需手动选择" in installer
    assert "刷新音频设备" in installer
    assert "Refresh audio devices" in install_script
    assert "wheelhouse" in install_script
    assert "--no-index" in install_script
    assert "--find-links" in install_script
    assert "--no-build-isolation" in install_script
    assert "ensurepip" in install_script
    assert "pip', 'download" in package_script
    assert "--platform', 'win_amd64" in package_script
    assert "--timeout', '600" in package_script
    assert "--retries', '10" in package_script
    assert "@('310', '311', '312')" in package_script
    assert "-split '[,; ]+'" in package_script
    assert "($WheelPythonVersions -join ',')" in installer_script
    assert "WheelhouseCacheDir" in package_script
    assert "PipIndexUrl" in package_script
    assert "python-runtime-requirements.txt" in package_script
    assert "meeting-suite\\meeting_audio_bridge.py" in package_script
    assert "local wheelhouse" in installer_script
    assert "aiortc>=1.14" in requirements
    assert "av>=16.0" in requirements
    assert "numpy>=1.26" in requirements
    assert "sounddevice>=0.5.5" in requirements
    assert "StartPreflightCheck" in installer
    assert "_preflightList" in installer
    assert "CheckPythonDependencies" not in installer
    assert "python_deps" not in installer
    assert "CheckPayloadResource" not in installer
    assert "CheckInstallDirectory" not in installer
    assert "CheckPowerShell" not in installer
    assert "CheckCameraRegistrationPermission" not in installer
