param(
    [string]$IpadBaseUrl = "http://192.168.0.24:27180",
    [string]$CableInputDevice = "CABLE Input",
    [string]$SpeakerCaptureDevice = "CABLE Output",
    [switch]$SkipRuntime
)

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Resolve-PythonInvocation {
    if (Test-CommandAvailable "py") {
        return @{ File = "py"; Prefix = @("-3") }
    }

    if (Test-CommandAvailable "python") {
        return @{ File = "python"; Prefix = @() }
    }

    return $null
}

function Invoke-JsonCommand {
    param(
        [hashtable]$PythonInvocation,
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )

    try {
        Push-Location $WorkingDirectory
        $output = & $PythonInvocation.File @($PythonInvocation.Prefix + $Arguments) 2>&1
        $exitCode = $LASTEXITCODE
        Pop-Location
        return @{
            ok = ($exitCode -eq 0)
            exitCode = $exitCode
            output = ($output -join "`n")
        }
    } catch {
        Pop-Location -ErrorAction SilentlyContinue
        return @{
            ok = $false
            exitCode = $null
            output = $_.Exception.Message
        }
    }
}

$PythonInvocation = Resolve-PythonInvocation

$checks = [ordered]@{
    root = $Root
    pythonOnPath = (Test-CommandAvailable "python")
    pyLauncherOnPath = (Test-CommandAvailable "py")
    components = [ordered]@{
        camera = (Test-Path (Join-Path $Root "sensorbridge-windows-clean\sensorbridge.py"))
        microphone = (Test-Path (Join-Path $Root "sensorbridge-microphone-windows\bridge.py"))
        speaker = (Test-Path (Join-Path $Root "sensorbridge-speaker-windows\speaker_bridge.py"))
    }
    ipad = [ordered]@{
        baseUrl = $IpadBaseUrl
        healthReachable = $false
        error = $null
    }
    audioRoute = [ordered]@{
        microphoneBridgePlaybackDevice = $CableInputDevice
        meetingMicrophoneSelectInMeeting = "CABLE Output"
        speakerBridgeCaptureDevice = $SpeakerCaptureDevice
        speakerSelectInMeeting = "CABLE Input"
    }
    runtime = [ordered]@{}
}

try {
    $health = Invoke-RestMethod -Uri ($IpadBaseUrl.TrimEnd("/") + "/health") -TimeoutSec 5
    $checks.ipad.healthReachable = $true
    $checks.ipad.health = $health
} catch {
    $checks.ipad.error = $_.Exception.Message
}

if (-not $SkipRuntime -and $null -ne $PythonInvocation) {
    $checks.runtime.microphoneVbCable = Invoke-JsonCommand `
        -PythonInvocation $PythonInvocation `
        -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows") `
        -Arguments @(".\bridge.py", "--output-device", $CableInputDevice, "vbcable-status")

    $checks.runtime.speakerRoute = Invoke-JsonCommand `
        -PythonInvocation $PythonInvocation `
        -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows") `
        -Arguments @(".\speaker_bridge.py", "--capture-device", $SpeakerCaptureDevice, "status")
}

$checks.ok = (
    ($checks.pythonOnPath -or $checks.pyLauncherOnPath) -and
    $checks.components.camera -and
    $checks.components.microphone -and
    $checks.components.speaker
)

$checks | ConvertTo-Json -Depth 8
