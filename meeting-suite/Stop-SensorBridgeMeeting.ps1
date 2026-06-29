param(
    [string[]]$Pids = @(),
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Targets = New-Object System.Collections.Generic.List[object]

function Add-Target {
    param(
        [int]$ProcessId,
        [string]$Reason,
        [string]$Name = "",
        [string]$CommandLine = ""
    )

    if ($ProcessId -le 0 -or $ProcessId -eq $PID) {
        return
    }
    foreach ($target in $Targets) {
        if ([int]$target.processId -eq $ProcessId) {
            return
        }
    }
    $Targets.Add([ordered]@{
        processId = $ProcessId
        name = $Name
        reason = $Reason
        commandLine = $CommandLine
    }) | Out-Null
}

foreach ($pidToken in $Pids) {
    foreach ($processIdText in ([string]$pidToken -split "[,\s]+")) {
        if ([string]::IsNullOrWhiteSpace($processIdText)) {
            continue
        }
        $processId = 0
        if ([int]::TryParse($processIdText, [ref]$processId)) {
            Add-Target -ProcessId $processId -Reason "tracked_by_meeting_app"
        }
    }
}

$cameraScript = Join-Path $Root "sensorbridge-windows-clean\sensorbridge.py"
$meetingAudioScript = Join-Path $Root "meeting-suite\meeting_audio_bridge.py"
$microphoneScript = Join-Path $Root "sensorbridge-microphone-windows\bridge.py"
$speakerScript = Join-Path $Root "sensorbridge-speaker-windows\speaker_bridge.py"
$senderExe = Join-Path $Root "sensorbridge-windows-clean\windows-app\SensorBridge.DirectShowSender\x64\Release\SensorBridge.DirectShowSender.exe"

$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
foreach ($process in $processes) {
    $name = [string]$process.Name
    $commandLine = [string]$process.CommandLine
    $executablePath = [string]$process.ExecutablePath
    if ($name -ieq "python.exe" -and (
        $commandLine.Contains($cameraScript) -or
        $commandLine.Contains($meetingAudioScript) -or
        $commandLine.Contains($microphoneScript) -or
        $commandLine.Contains($speakerScript)
    )) {
        Add-Target -ProcessId ([int]$process.ProcessId) -Reason "sensorbridge_python_bridge" -Name $name -CommandLine $commandLine
    }
    if ($name -ieq "python.exe" -and $commandLine.Contains("sensorbridge.py") -and $commandLine.Contains("--port")) {
        Add-Target -ProcessId ([int]$process.ProcessId) -Reason "legacy_relative_camera_bridge" -Name $name -CommandLine $commandLine
    }
    if ($name -ieq "python.exe" -and $commandLine.Contains("bridge.py") -and $commandLine.Contains("--base-url") -and (
        $commandLine.Contains("pump-vbcable") -or
        $commandLine.Contains("webrtc-microphone")
    )) {
        Add-Target -ProcessId ([int]$process.ProcessId) -Reason "legacy_relative_microphone_bridge" -Name $name -CommandLine $commandLine
    }
    if ($name -ieq "python.exe" -and $commandLine.Contains("speaker_bridge.py") -and $commandLine.Contains("--base-url") -and (
        $commandLine.Contains("stream") -or
        $commandLine.Contains("webrtc-speaker")
    )) {
        Add-Target -ProcessId ([int]$process.ProcessId) -Reason "legacy_relative_speaker_bridge" -Name $name -CommandLine $commandLine
    }
    if ($name -ieq "SensorBridge.DirectShowSender.exe" -and (
        $executablePath -ieq $senderExe -or
        $commandLine.Contains($senderExe)
    )) {
        Add-Target -ProcessId ([int]$process.ProcessId) -Reason "sensorbridge_directshow_sender" -Name $name -CommandLine $commandLine
    }
}

$StoppedItems = @()
foreach ($target in $Targets) {
    $didStop = $false
    $errorMessage = $null
    if ($DryRun) {
        $didStop = $true
    } else {
        try {
            Stop-Process -Id ([int]$target.processId) -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 150
            $didStop = -not [bool](Get-Process -Id ([int]$target.processId) -ErrorAction SilentlyContinue)
        } catch {
            $errorMessage = $_.Exception.Message
        }
    }
    $StoppedItems += [ordered]@{
        processId = [int]$target.processId
        name = $target.name
        reason = $target.reason
        stopped = $didStop
        error = $errorMessage
    }
}

[ordered]@{
    ok = -not [bool](@($StoppedItems) | Where-Object { -not [bool]$_.stopped })
    command = "stop_sensorbridge_meeting"
    changes_system = $false
    dryRun = [bool]$DryRun
    root = $Root
    stopped = @($StoppedItems)
} | ConvertTo-Json -Depth 6
