param(
    [string]$IpadBaseUrl = "http://192.168.0.24:27180",
    [int]$CameraPort = 8765,
    [int]$DurationSeconds = 60,
    [int]$SampleIntervalSeconds = 5,
    [double]$MinReceivedFps = 10.0,
    [double]$MinDecodedFps = 10.0,
    [double]$MinVirtualCameraFps = 5.0,
    [int]$MaxLatestFrameAgeMs = 2000,
    [switch]$LeaveRunning
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $Root "logs\meeting-suite"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Checks = @()
$StartedProcesses = @()
$StartedByThisScript = @()

function Add-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [object]$Evidence = $null,
        [string]$Error = ""
    )

    $script:Checks += [ordered]@{
        name = $Name
        ok = $Ok
        error = $Error
        evidence = $Evidence
    }
}

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $executable = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $executable -and (Test-Path $executable.Trim())) {
            return @{ File = $executable.Trim(); Prefix = @() }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; Prefix = @() }
    }

    throw "Python was not found. Install Python 3.10+ or add it to PATH."
}

function Quote-Argument {
    param([string]$Value)

    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Join-Arguments {
    param([string[]]$Arguments)

    return (($Arguments | ForEach-Object { Quote-Argument $_ }) -join " ")
}

function Invoke-JsonProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $Root,
        [int]$TimeoutSeconds = 60
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = Join-Arguments $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch {}
        return [ordered]@{ ok = $false; error = "Timed out after $TimeoutSeconds seconds."; exitCode = $null }
    }

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    try {
        $payload = $stdout | ConvertFrom-Json
    } catch {
        $payload = [pscustomobject]@{ ok = $false; raw = $stdout }
    }
    if ($process.ExitCode -ne 0 -and $payload.PSObject.Properties.Name -notcontains "ok") {
        $payload | Add-Member -NotePropertyName ok -NotePropertyValue $false
    }
    if ($stderr) {
        $payload | Add-Member -NotePropertyName stderr -NotePropertyValue $stderr -Force
    }
    $payload | Add-Member -NotePropertyName exitCode -NotePropertyValue $process.ExitCode -Force
    return $payload
}

function Invoke-WebJson {
    param(
        [string]$Method = "GET",
        [string]$Uri,
        [int]$TimeoutSeconds = 8
    )

    if ($Method -eq "POST") {
        return Invoke-RestMethod -Method Post -Uri $Uri -Body "{}" -ContentType "application/json" -TimeoutSec $TimeoutSeconds
    }
    return Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSeconds
}

function Test-HttpReady {
    param([string]$Uri, [int]$TimeoutSeconds = 2)

    try {
        Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $LogDir "$Name-$timestamp.out.log"
    $stderr = Join-Path $LogDir "$Name-$timestamp.err.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList (Join-Arguments $Arguments) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    $entry = [ordered]@{
        name = $Name
        pid = $process.Id
        process = $process
        stdout = $stdout
        stderr = $stderr
        arguments = $Arguments
        startedByThisScript = $true
    }
    $script:StartedProcesses += $entry
    $script:StartedByThisScript += $entry
    return $entry
}

function Stop-StartedProcesses {
    if ($LeaveRunning) {
        return
    }

    foreach ($entry in [array]$script:StartedByThisScript) {
        try {
            $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if ($process) {
                Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
}

function Ensure-VirtualCamera {
    $directshowRoot = Join-Path $Root "sensorbridge-windows-clean"
    $senderScript = Join-Path $directshowRoot "drivers\camera\directshow\sender-dev.ps1"
    $registerScript = Join-Path $directshowRoot "drivers\camera\directshow\register-dev.ps1"
    $probeScript = Join-Path $directshowRoot "tools\directshow-device-probe.ps1"

    $senderStatus = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $senderScript, "-Status") -TimeoutSeconds 45
    if (-not [bool]$senderStatus.running) {
        $null = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $senderScript, "-Start") -TimeoutSeconds 60
        $senderStatus = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $senderScript, "-Status") -TimeoutSeconds 45
    }

    $probe = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $probeScript) -TimeoutSeconds 45
    $cameraVisible = $false
    foreach ($device in @($probe.videoInput)) {
        if (("{0}" -f $device.name) -like "*SensorBridge Camera*") {
            $cameraVisible = $true
        }
    }

    $registerRepair = $null
    if (-not $cameraVisible) {
        $registerRepair = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $registerScript, "-Register") -TimeoutSeconds 90
        $probe = Invoke-JsonProcess -FilePath "powershell.exe" -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $probeScript) -TimeoutSeconds 45
        foreach ($device in @($probe.videoInput)) {
            if (("{0}" -f $device.name) -like "*SensorBridge Camera*") {
                $cameraVisible = $true
            }
        }
    }

    $openStatus = $null
    try {
        if (Test-HttpReady -Uri "http://127.0.0.1:$CameraPort/health" -TimeoutSeconds 2) {
            $openStatus = Invoke-WebJson -Uri "http://127.0.0.1:$CameraPort/api/directshow/camera/open-status" -TimeoutSeconds 8
        }
    } catch {
        $openStatus = [ordered]@{ ok = $false; error = $_.Exception.Message }
    }

    return [ordered]@{
        sender = $senderStatus
        probe = $probe
        openStatus = $openStatus
        registerRepair = $registerRepair
        ok = ([bool]$senderStatus.running -and [bool]$probe.ok -and $cameraVisible -and ($null -eq $openStatus -or [bool]$openStatus.opens_camera_now -or [bool]$openStatus.visible_to_windows_apps))
    }
}

function Ensure-Camera {
    param([hashtable]$Python)

    $baseUrl = "http://127.0.0.1:$CameraPort"
    $alreadyRunning = Test-HttpReady -Uri "$baseUrl/health" -TimeoutSeconds 2
    if (-not $alreadyRunning) {
        Start-ManagedProcess `
            -Name "camera-core-test" `
            -FilePath $Python.File `
            -Arguments @("sensorbridge.py", "--port", "$CameraPort", "--upstream-url", $IpadBaseUrl) `
            -WorkingDirectory (Join-Path $Root "sensorbridge-windows-clean") | Out-Null

        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 500
            $alreadyRunning = Test-HttpReady -Uri "$baseUrl/health" -TimeoutSeconds 2
        } while (-not $alreadyRunning -and (Get-Date) -lt $deadline)
    }

    if (-not $alreadyRunning) {
        throw "Camera service did not become reachable on $baseUrl."
    }

    $upstream = $IpadBaseUrl.TrimEnd("/")
    $media = [ordered]@{}
    foreach ($path in @("/api/v1/video/start", "/api/v1/audio/start")) {
        try {
            $media[$path] = Invoke-WebJson -Method "POST" -Uri "$upstream$path" -TimeoutSeconds 10
        } catch {
            $media[$path] = [ordered]@{ ok = $false; error = $_.Exception.Message }
        }
    }

    $start = Invoke-WebJson -Method "POST" -Uri "$baseUrl/api/v1/product/start" -TimeoutSeconds 30
    return [ordered]@{
        alreadyRunning = $alreadyRunning
        media = $media
        productStart = $start
    }
}

function Get-CameraStatus {
    return Invoke-WebJson -Uri "http://127.0.0.1:$CameraPort/api/v1/product/status" -TimeoutSeconds 6
}

function Test-CameraStatus {
    param([object]$Status)

    return (
        [bool]$Status.ok -and
        [bool]$Status.cameraAvailable -and
        [bool]$Status.normalWindowsCameraVisible -and
        [double]$Status.receivedFps -ge $MinReceivedFps -and
        [double]$Status.decodedFps -ge $MinDecodedFps -and
        [double]$Status.virtualCameraFps -ge $MinVirtualCameraFps -and
        [double]$Status.latestFrameAgeMs -le $MaxLatestFrameAgeMs
    )
}

function Start-AudioProcesses {
    param([hashtable]$Python)

    $microphone = Start-ManagedProcess `
        -Name "microphone-core-test" `
        -FilePath $Python.File `
        -Arguments @("bridge.py", "--base-url", $IpadBaseUrl, "--frames", "0", "--output-device", "CABLE Input", "pump-vbcable") `
        -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows")

    $speaker = Start-ManagedProcess `
        -Name "speaker-core-test" `
        -FilePath $Python.File `
        -Arguments @("speaker_bridge.py", "--base-url", $IpadBaseUrl, "--duration-seconds", "0", "--gain", "0", "stream") `
        -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows")

    return @($microphone, $speaker)
}

function Get-ProcessAlive {
    param([int]$ProcessIdValue)

    $process = Get-Process -Id $ProcessIdValue -ErrorAction SilentlyContinue
    return [bool]$process
}

$StartedAt = Get-Date
$Python = Resolve-PythonCommand
$Artifacts = [ordered]@{}

try {
try {
    $health = Invoke-WebJson -Uri ($IpadBaseUrl.TrimEnd("/") + "/health") -TimeoutSeconds 5
    Add-Check -Name "ipad_service_reachable" -Ok $true -Evidence $health
} catch {
    Add-Check -Name "ipad_service_reachable" -Ok $false -Error $_.Exception.Message
    throw
}

$virtualCamera = Ensure-VirtualCamera
Add-Check -Name "virtual_camera_visible_to_windows" -Ok ([bool]$virtualCamera.ok) -Evidence $virtualCamera

$cameraStart = Ensure-Camera -Python $Python
Add-Check -Name "camera_product_start" -Ok ([bool]$cameraStart.productStart.ok) -Evidence $cameraStart

$initialCameraStatus = Get-CameraStatus
Add-Check -Name "camera_has_picture_and_fps" -Ok (Test-CameraStatus $initialCameraStatus) -Evidence ([ordered]@{
    receivedFps = $initialCameraStatus.receivedFps
    decodedFps = $initialCameraStatus.decodedFps
    virtualCameraFps = $initialCameraStatus.virtualCameraFps
    latestFrameAgeMs = $initialCameraStatus.latestFrameAgeMs
    normalWindowsCameraVisible = $initialCameraStatus.normalWindowsCameraVisible
})

$microphoneProbe = Invoke-JsonProcess `
    -FilePath $Python.File `
    -Arguments @("bridge.py", "--base-url", $IpadBaseUrl, "--frames", "12", "--frame-delay", "0.05", "--output-device", "CABLE Input", "vbcable-loopback-check") `
    -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows") `
    -TimeoutSeconds 35

$microphoneHasLevel = (
    [bool]$microphoneProbe.ok -and
    [int]$microphoneProbe.recorded_peak_abs -gt 0 -and
    [bool]$microphoneProbe.ordinary_apps_can_record_cable_output
)
Add-Check -Name "microphone_has_input_level" -Ok $microphoneHasLevel -Evidence $microphoneProbe

$speakerProbe = Invoke-JsonProcess `
    -FilePath $Python.File `
    -Arguments @("speaker_bridge.py", "--base-url", $IpadBaseUrl, "--duration-seconds", "5", "--timeout", "12", "route-test") `
    -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows") `
    -TimeoutSeconds 35

$speakerRouteOk = (
    [bool]$speakerProbe.ok -and
    [int]$speakerProbe.chunks_sent -gt 0 -and
    [bool]$speakerProbe.ipad_playback_scheduled
)
Add-Check -Name "speaker_playback_return_route" -Ok $speakerRouteOk -Evidence $speakerProbe

$audioProcesses = Start-AudioProcesses -Python $Python
Start-Sleep -Seconds 2

$samples = @()
$deadline = (Get-Date).AddSeconds([Math]::Max(1, $DurationSeconds))
do {
    $processStates = @()
    foreach ($entry in $audioProcesses) {
        $processStates += [ordered]@{
            name = $entry.name
            pid = $entry.pid
            alive = Get-ProcessAlive -ProcessIdValue $entry.pid
        }
    }

    try {
        $status = Get-CameraStatus
        $cameraOk = Test-CameraStatus $status
        $samples += [ordered]@{
            at = (Get-Date).ToString("o")
            cameraOk = $cameraOk
            receivedFps = $status.receivedFps
            decodedFps = $status.decodedFps
            virtualCameraFps = $status.virtualCameraFps
            latestFrameAgeMs = $status.latestFrameAgeMs
            normalWindowsCameraVisible = $status.normalWindowsCameraVisible
            processStates = $processStates
        }
    } catch {
        $samples += [ordered]@{
            at = (Get-Date).ToString("o")
            cameraOk = $false
            error = $_.Exception.Message
            processStates = $processStates
        }
    }

    if ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds ([Math]::Max(1, $SampleIntervalSeconds))
    }
} while ((Get-Date) -lt $deadline)

$allProcessesAlive = $true
foreach ($sample in $samples) {
    foreach ($state in $sample.processStates) {
        if (-not [bool]$state.alive) {
            $allProcessesAlive = $false
        }
    }
}
$allCameraSamplesOk = ($samples.Count -gt 0) -and -not ($samples | Where-Object { -not [bool]$_.cameraOk })

$receivedValues = @($samples | Where-Object { $_.receivedFps -ne $null } | ForEach-Object { [double]$_.receivedFps })
$decodedValues = @($samples | Where-Object { $_.decodedFps -ne $null } | ForEach-Object { [double]$_.decodedFps })
$virtualValues = @($samples | Where-Object { $_.virtualCameraFps -ne $null } | ForEach-Object { [double]$_.virtualCameraFps })

$simultaneous = [ordered]@{
    durationSeconds = $DurationSeconds
    sampleIntervalSeconds = $SampleIntervalSeconds
    processesStayedAlive = $allProcessesAlive
    cameraStayedStable = $allCameraSamplesOk
    minReceivedFps = if ($receivedValues.Count) { ($receivedValues | Measure-Object -Minimum).Minimum } else { $null }
    minDecodedFps = if ($decodedValues.Count) { ($decodedValues | Measure-Object -Minimum).Minimum } else { $null }
    minVirtualCameraFps = if ($virtualValues.Count) { ($virtualValues | Measure-Object -Minimum).Minimum } else { $null }
    samples = $samples
    startedProcesses = @($audioProcesses | ForEach-Object {
        [ordered]@{ name = $_.name; pid = $_.pid; stdout = $_.stdout; stderr = $_.stderr; arguments = $_.arguments }
    })
}
Add-Check -Name "three_modules_one_minute_no_crash" -Ok ($allProcessesAlive -and $allCameraSamplesOk) -Evidence $simultaneous

$ok = -not ($Checks | Where-Object { -not [bool]$_.ok })
$EndedAt = Get-Date
$report = [ordered]@{
    ok = $ok
    command = "one_minute_core_usability"
    changes_system = $false
    startedAt = $StartedAt.ToString("o")
    endedAt = $EndedAt.ToString("o")
    elapsedSeconds = [Math]::Round(($EndedAt - $StartedAt).TotalSeconds, 3)
    ipadBaseUrl = $IpadBaseUrl
    cameraPort = $CameraPort
    checks = $Checks
    summary = [ordered]@{
        camera = [ordered]@{
            receivedFps = $initialCameraStatus.receivedFps
            decodedFps = $initialCameraStatus.decodedFps
            virtualCameraFps = $initialCameraStatus.virtualCameraFps
            latestFrameAgeMs = $initialCameraStatus.latestFrameAgeMs
            visibleToWindowsApps = $initialCameraStatus.normalWindowsCameraVisible
        }
        microphone = [ordered]@{
            recordedPeakAbs = $microphoneProbe.recorded_peak_abs
            recordedRms = $microphoneProbe.recorded_rms
            latestPeakAbs = $microphoneProbe.latest_audio.peak_abs
            latestRms = $microphoneProbe.latest_audio.rms
            ordinaryAppsCanRecordCableOutput = $microphoneProbe.ordinary_apps_can_record_cable_output
        }
        speaker = [ordered]@{
            chunksSent = $speakerProbe.chunks_sent
            bytesSent = $speakerProbe.bytes_sent
            peakAbs = $speakerProbe.peak_abs
            rms = $speakerProbe.rms
            ipadPlaybackScheduled = $speakerProbe.ipad_playback_scheduled
        }
        simultaneous = [ordered]@{
            processesStayedAlive = $allProcessesAlive
            cameraStayedStable = $allCameraSamplesOk
            minReceivedFps = $simultaneous.minReceivedFps
            minDecodedFps = $simultaneous.minDecodedFps
            minVirtualCameraFps = $simultaneous.minVirtualCameraFps
        }
    }
    notes = @(
        "This is a no-Tencent core test. Tencent Meeting can still have app-specific device selection or permission issues.",
        "The simultaneous speaker process is started with gain 0 during crash monitoring to avoid feedback on a single VB-CABLE route.",
        "For clean full-duplex meetings, use separate virtual cable routes for microphone injection and speaker return when possible."
    )
}

$reportPath = Join-Path $LogDir ("one-minute-core-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
$Artifacts.reportPath = $reportPath
$report["artifacts"] = $Artifacts
$report | ConvertTo-Json -Depth 20 | Set-Content -Path $reportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 20

if (-not $ok) {
    exit 1
}
exit 0
}
finally {
    Stop-StartedProcesses
}
