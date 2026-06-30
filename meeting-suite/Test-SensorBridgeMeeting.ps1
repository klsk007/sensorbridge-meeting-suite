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

function Test-PythonBridgeRuntime {
    param([string]$File)

    if (-not $File -or -not (Test-Path $File)) { return $false }
    $code = @"
import importlib.util, sys
required = ['sounddevice']
ok = sys.version_info >= (3, 10) and all(importlib.util.find_spec(name) is not None for name in required)
raise SystemExit(0 if ok else 1)
"@
    & $File -c $code 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-PythonInvocation {
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
            return @{ File = $candidate; Prefix = @(); Version = (& $candidate -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null) }
        }
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
    pythonRuntime = if ($PythonInvocation) { [ordered]@{ found = $true; file = $PythonInvocation.File; version = $PythonInvocation.Version } } else { [ordered]@{ found = $false; file = $null; version = $null } }
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
