param(
    [string]$IpadBaseUrl = "http://192.168.0.24:27180",
    [int]$CameraPort = 8765,
    [switch]$NoCamera,
    [switch]$NoMicrophone,
    [switch]$NoSpeaker,
    [ValidateSet("vbcable", "webrtc")]
    [string]$MicrophoneMode = "webrtc",
    [ValidateSet("http", "webrtc")]
    [string]$SpeakerMode = "webrtc",
    [double]$MicGain = 1.0,
    [string]$CableInputDevice = "CABLE Input",
    [string]$SpeakerCaptureDevice = "CABLE Output",
    [int]$LowCutHz = 80,
    [double]$NoiseGateThreshold = 0.0,
    [int]$PlaybackPrebufferMs = 2500,
    [double]$SpeakerGain = 0.35,
    [double]$SpeakerPushToTalkDuckGain = 0.0,
    [int]$SpeakerPushToTalkTailMs = 1200,
    [switch]$PushToTalk,
    [string]$PushToTalkControlPath = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $Root "logs\meeting-suite"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if ([string]::IsNullOrWhiteSpace($PushToTalkControlPath)) {
    $PushToTalkControlPath = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)) "SensorBridge\meeting\push_to_talk.json"
}

function Write-PushToTalkControl {
    param(
        [string]$Path,
        [bool]$Talking
    )

    $directory = Split-Path -Parent $Path
    if ($directory) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    $payload = @{
        talking = $Talking
        updatedAt = [DateTimeOffset]::UtcNow.ToString("o")
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($Path, $payload, [System.Text.UTF8Encoding]::new($false))
}

function Test-PythonBridgeRuntime {
    param([string]$File)

    if (-not $File -or -not (Test-Path $File)) { return $false }
    $code = @"
import importlib.util, sys
required = ['aiortc', 'av', 'numpy', 'sounddevice']
ok = sys.version_info >= (3, 10) and all(importlib.util.find_spec(name) is not None for name in required)
raise SystemExit(0 if ok else 1)
"@
    & $File -c $code 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-PythonCommand {
    $candidates = @()
    $bundled = Join-Path $Root "python-3.12.3\python.exe"
    if (Test-Path $bundled) {
        $candidates += $bundled
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @("3.12", "3.11", "3.10")) {
            $executable = $null
            try {
                $executable = & $py.Source "-$version" -c "import sys; print(sys.executable)" 2>$null
            } catch {
                $executable = $null
            }
            if ($LASTEXITCODE -eq 0 -and $executable -and (Test-Path $executable.Trim())) {
                $candidates += $executable.Trim()
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $candidates += $python.Source
    }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (Test-PythonBridgeRuntime -File $candidate) {
            return @{ File = $candidate; Prefix = @() }
        }
    }

    throw "Python bridge runtime was not found. Install with the v1.01+ installer, or use Python 3.10+ with aiortc, av, numpy, and sounddevice installed."
}

function Quote-ProcessArgument {
    param([string]$Value)

    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Join-ProcessArguments {
    param([string[]]$ArgumentList)

    return (($ArgumentList | ForEach-Object { Quote-ProcessArgument $_ }) -join " ")
}

function Start-DetachedProcess {
    param(
        [string]$FilePath,
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )

    $startup = ([wmiclass]"Win32_ProcessStartup").CreateInstance()
    $startup.ShowWindow = 0
    $commandLine = (Quote-ProcessArgument $FilePath) + " " + (Join-ProcessArguments $Arguments)
    $result = ([wmiclass]"Win32_Process").Create($commandLine, $WorkingDirectory, $startup)
    if ([int]$result.ReturnValue -ne 0) {
        throw "Failed to start $FilePath with Win32_Process.Create return code $($result.ReturnValue)."
    }
    return [int]$result.ProcessId
}

function Start-BridgeProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )

    if (-not (Test-Path $WorkingDirectory)) {
        throw "Missing component directory for $Name`: $WorkingDirectory"
    }

    $processId = Start-DetachedProcess `
        -FilePath $Python.File `
        -WorkingDirectory $WorkingDirectory `
        -Arguments ($Python.Prefix + $Arguments)

    [pscustomobject]@{
        name = $Name
        pid = $processId
        cwd = $WorkingDirectory
        stdout = $null
        stderr = $null
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            Invoke-RestMethod -Uri $Url -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-CameraPortOwners {
    param([int]$Port)

    $connections = @()
    try {
        $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return @()
    }

    $owners = @()
    foreach ($connection in $connections) {
        $ownerPid = [int]$connection.OwningProcess
        $process = $null
        try {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
        } catch {
            $process = $null
        }

        $owners += [pscustomobject]@{
            processId = $ownerPid
            name = if ($process) { $process.Name } else { $null }
            executablePath = if ($process) { $process.ExecutablePath } else { $null }
            commandLine = if ($process) { $process.CommandLine } else { $null }
        }
    }

    return @($owners | Sort-Object processId -Unique)
}

function Assert-CameraPortAvailable {
    param([int]$Port)

    $owners = @(Get-CameraPortOwners -Port $Port)
    if ($owners.Count -eq 0) { return }

    $ownerDetails = ($owners | ForEach-Object {
        $parts = @("PID=$($_.processId)")
        if ($_.name) { $parts += "name=$($_.name)" }
        if ($_.executablePath) { $parts += "path=$($_.executablePath)" }
        if ($_.commandLine) { $parts += "command=$($_.commandLine)" }
        $parts -join ", "
    }) -join " | "

    throw "Camera local port $Port is already in use. Close the older SensorBridge app, or change CameraPort, then start again. Owner: $ownerDetails"
}

function Wait-CameraProductReady {
    param(
        [string]$BaseUrl,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastStatus = $null
    $lastError = $null
    do {
        try {
            $lastStatus = Invoke-RestMethod -Uri "$BaseUrl/api/v1/product/status" -TimeoutSec 3
            $ready = (
                [bool]$lastStatus.cameraAvailable -and
                [bool]$lastStatus.normalWindowsCameraVisible -and
                [double]$lastStatus.receivedFps -gt 0 -and
                [double]$lastStatus.decodedFps -gt 0 -and
                [double]$lastStatus.virtualCameraFps -gt 0
            )
            if ($ready) {
                return @{
                    ready = $true
                    status = $lastStatus
                    error = $null
                }
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return @{
        ready = $false
        status = $lastStatus
        error = $lastError
    }
}

function Start-CameraProductMode {
    param(
        [int]$Port,
        [string]$UpstreamBaseUrl
    )

    $baseUrl = "http://127.0.0.1:$Port"
    if (-not (Wait-HttpReady -Url "$baseUrl/health" -TimeoutSeconds 20)) {
        return @{
            ok = $false
            skipped = $true
            error = "Camera service did not become reachable on $baseUrl."
        }
    }

    $virtualDevice = Ensure-CameraVirtualDevice
    $upstream = $UpstreamBaseUrl.TrimEnd("/")
    $mediaStart = [ordered]@{}
    foreach ($path in @("/api/v1/video/start", "/api/v1/audio/start")) {
        try {
            $mediaStart[$path] = Invoke-RestMethod -Method Post -Uri "$upstream$path" -Body "{}" -ContentType "application/json" -TimeoutSec 10
        } catch {
            $mediaStart[$path] = @{
                ok = $false
                error = $_.Exception.Message
            }
        }
    }

    try {
        $productStart = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/product/start" -Body "{}" -ContentType "application/json" -TimeoutSec 30
        $readiness = Wait-CameraProductReady -BaseUrl $baseUrl -TimeoutSeconds 10
        $status = if ($readiness.status) { $readiness.status } else { $productStart.product_status }
        return @{
            ok = ([bool]$productStart.ok -and [bool]$readiness.ready)
            productStartOk = [bool]$productStart.ok
            cameraReady = [bool]$readiness.ready
            virtualDevice = $virtualDevice
            mediaStart = $mediaStart
            cameraAvailable = [bool]$status.cameraAvailable
            directshowSenderOk = [bool]$productStart.directshow_sender.ok
            directshowSenderRunning = [bool]$productStart.directshow_sender.running
            normalWindowsCameraVisible = [bool]$status.normalWindowsCameraVisible
            receivedFps = $status.receivedFps
            decodedFps = $status.decodedFps
            virtualCameraFps = $status.virtualCameraFps
            latestFrameAgeMs = $status.latestFrameAgeMs
            blockers = $status.blockers
            readinessError = $readiness.error
        }
    } catch {
        return @{
            ok = $false
            virtualDevice = $virtualDevice
            mediaStart = $mediaStart
            error = $_.Exception.Message
        }
    }
}

function Invoke-JsonScript {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 120
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" $($Arguments -join ' ')"
    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch {}
        return @{ ok = $false; error = "Timed out running $ScriptPath" }
    }
    $output = $process.StandardOutput.ReadToEnd()
    $errorOutput = $process.StandardError.ReadToEnd()
    try {
        $payload = $output | ConvertFrom-Json
    } catch {
        $payload = @{ ok = $false; raw = $output }
    }
    if ($process.ExitCode -ne 0 -and $payload.PSObject.Properties.Name -notcontains "ok") {
        $payload | Add-Member -NotePropertyName ok -NotePropertyValue $false
    }
    if ($errorOutput) {
        $payload | Add-Member -NotePropertyName stderr -NotePropertyValue $errorOutput -Force
    }
    return $payload
}

function Ensure-CameraVirtualDevice {
    $directshowRoot = Join-Path $Root "sensorbridge-windows-clean"
    $senderScript = Join-Path $directshowRoot "drivers\camera\directshow\sender-dev.ps1"
    $buildScript = Join-Path $directshowRoot "drivers\camera\directshow\build-dev.ps1"
    $registerScript = Join-Path $directshowRoot "drivers\camera\directshow\register-dev.ps1"
    $probeScript = Join-Path $directshowRoot "tools\directshow-device-probe.ps1"

    $senderStatus = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Status") -TimeoutSeconds 45
    $build = $null
    $senderBuild = $null
    $senderStart = $null
    $register = $null
    if (-not [bool]$senderStatus.exe_exists) {
        $build = Invoke-JsonScript -ScriptPath $buildScript -Arguments @("-Build") -TimeoutSeconds 240
        $senderBuild = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Build") -TimeoutSeconds 180
        $senderStatus = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Status") -TimeoutSeconds 45
    }

    if (-not [bool]$senderStatus.running) {
        $senderStart = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Start") -TimeoutSeconds 60
        $senderStatus = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Status") -TimeoutSeconds 45
    }

    $probe = Invoke-JsonScript -ScriptPath $probeScript -Arguments @() -TimeoutSeconds 45
    $cameraVisible = $false
    foreach ($device in @($probe.videoInput)) {
        if (("{0}" -f $device.name) -like "*SensorBridge Camera*") {
            $cameraVisible = $true
        }
    }

    if (-not $cameraVisible) {
        $register = Invoke-JsonScript -ScriptPath $registerScript -Arguments @("-Register") -TimeoutSeconds 120
        $probe = Invoke-JsonScript -ScriptPath $probeScript -Arguments @() -TimeoutSeconds 45
        $cameraVisible = $false
        foreach ($device in @($probe.videoInput)) {
            if (("{0}" -f $device.name) -like "*SensorBridge Camera*") {
                $cameraVisible = $true
            }
        }
    }

    return @{
        senderExeExists = [bool]$senderStatus.exe_exists
        senderRunning = [bool]$senderStatus.running
        visibleToWindowsApps = $cameraVisible
        build = $build
        senderBuild = $senderBuild
        senderStart = $senderStart
        register = $register
        probe = $probe
    }
}

$Python = Resolve-PythonCommand
$Started = @()
$UseWebRtcMicrophone = (-not $NoMicrophone -and $MicrophoneMode -eq "webrtc")
$UseWebRtcSpeaker = (-not $NoSpeaker -and $SpeakerMode -eq "webrtc")
$UseCombinedAudio = ($UseWebRtcMicrophone -and $UseWebRtcSpeaker)
$UseCombinedMedia = (-not $NoCamera)
$UseCombinedBridge = ($UseCombinedAudio -or $UseCombinedMedia)

if ($PushToTalk -and -not $NoMicrophone) {
    Write-PushToTalkControl -Path $PushToTalkControlPath -Talking $false
}

if ($UseCombinedBridge) {
    $virtualDevice = $null
    if ($UseCombinedMedia) {
        $virtualDevice = Ensure-CameraVirtualDevice
    }
    $audioArgs = @(
        (Join-Path $Root "meeting-suite\meeting_audio_bridge.py"),
        "--base-url", $IpadBaseUrl,
        "--output-device", $CableInputDevice,
        "--capture-device", $SpeakerCaptureDevice,
        "--duration-seconds", "0",
        "--mic-gain", "$MicGain",
        "--low-cut-hz", "$LowCutHz",
        "--noise-gate-threshold", "$NoiseGateThreshold",
        "--playback-prebuffer-ms", "$PlaybackPrebufferMs",
        "--speaker-gain", "$SpeakerGain"
    )
    if ($UseCombinedMedia) {
        $audioArgs += "--enable-video"
    }
    if ($NoMicrophone -or $MicrophoneMode -ne "webrtc") {
        $audioArgs += "--no-microphone"
    }
    if ($NoSpeaker -or $SpeakerMode -ne "webrtc") {
        $audioArgs += "--no-speaker"
    }
    if ($PushToTalk -and -not $NoMicrophone) {
        $audioArgs += "--push-to-talk-control"
        $audioArgs += $PushToTalkControlPath
        $audioArgs += "--push-to-talk-default-muted"
        if (-not $NoSpeaker -and $SpeakerMode -eq "webrtc") {
            $audioArgs += "--speaker-push-to-talk-duck-gain"
            $audioArgs += "$SpeakerPushToTalkDuckGain"
            $audioArgs += "--speaker-push-to-talk-tail-ms"
            $audioArgs += "$SpeakerPushToTalkTailMs"
        }
    }
    $audioArgs += "webrtc-duplex"
    $audio = Start-BridgeProcess `
        -Name "meeting-media" `
        -WorkingDirectory (Join-Path $Root "meeting-suite") `
        -Arguments $audioArgs
    $audio | Add-Member -NotePropertyName mode -NotePropertyValue "webrtc-duplex"
    if ($UseCombinedMedia) {
        $camera = [pscustomobject]@{
            name = "camera"
            pid = $audio.pid
            cwd = $audio.cwd
            stdout = $audio.stdout
            stderr = $audio.stderr
            mode = "webrtc-duplex"
            combinedMedia = $true
            virtualDevice = $virtualDevice
        }
        $Started += $camera
    }
    if (-not $NoMicrophone) {
        $microphone = [pscustomobject]@{
            name = "microphone"
            pid = $audio.pid
            cwd = $audio.cwd
            stdout = $audio.stdout
            stderr = $audio.stderr
            mode = "webrtc-duplex"
            combinedAudio = $true
        }
        $Started += $microphone
    }
    if (-not $NoSpeaker) {
        $speaker = [pscustomobject]@{
            name = "speaker"
            pid = $audio.pid
            cwd = $audio.cwd
            stdout = $audio.stdout
            stderr = $audio.stderr
            mode = "webrtc-duplex"
            combinedAudio = $true
        }
        $Started += $speaker
    }
} elseif (-not $NoMicrophone) {
    if ($MicrophoneMode -eq "webrtc") {
        $microphoneArgs = @(
            (Join-Path $Root "sensorbridge-microphone-windows\bridge.py"),
            "--base-url", $IpadBaseUrl,
            "--duration-seconds", "0",
            "--output-device", $CableInputDevice,
            "--output-gain", "$MicGain",
            "--low-cut-hz", "$LowCutHz",
            "--noise-gate-threshold", "$NoiseGateThreshold",
            "--playback-prebuffer-ms", "$PlaybackPrebufferMs"
        )
        if ($PushToTalk) {
            $microphoneArgs += "--push-to-talk-control"
            $microphoneArgs += $PushToTalkControlPath
            $microphoneArgs += "--push-to-talk-default-muted"
        }
        $microphoneArgs += "webrtc-microphone"
        $microphone = Start-BridgeProcess `
            -Name "microphone" `
            -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows") `
            -Arguments $microphoneArgs
    } else {
        $microphone = Start-BridgeProcess `
            -Name "microphone" `
            -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows") `
            -Arguments @(
                (Join-Path $Root "sensorbridge-microphone-windows\bridge.py"),
                "--base-url", $IpadBaseUrl,
                "--frames", "0",
                "--output-device", $CableInputDevice,
                "pump-vbcable"
            )
    }
    $microphone | Add-Member -NotePropertyName mode -NotePropertyValue $MicrophoneMode
    $Started += $microphone
}

if (-not $UseCombinedBridge -and -not $NoSpeaker) {
    if ($SpeakerMode -eq "webrtc") {
        $speaker = Start-BridgeProcess `
            -Name "speaker" `
            -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows") `
            -Arguments @(
                (Join-Path $Root "sensorbridge-speaker-windows\speaker_bridge.py"),
                "--base-url", $IpadBaseUrl,
                "--capture-device", $SpeakerCaptureDevice,
                "--duration-seconds", "0",
                "webrtc-speaker"
            )
    } else {
        $speaker = Start-BridgeProcess `
            -Name "speaker" `
            -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows") `
            -Arguments @(
                (Join-Path $Root "sensorbridge-speaker-windows\speaker_bridge.py"),
                "--base-url", $IpadBaseUrl,
                "--capture-device", $SpeakerCaptureDevice,
                "--duration-seconds", "0",
                "--gain", "$SpeakerGain",
                "stream"
            )
    }
    $speaker | Add-Member -NotePropertyName mode -NotePropertyValue $SpeakerMode
    $Started += $speaker
}

ConvertTo-Json -InputObject @($Started) -Depth 4
