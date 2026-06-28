param(
    [string]$IpadBaseUrl = "http://192.168.0.24:27180",
    [int]$CameraPort = 8765,
    [switch]$NoCamera,
    [switch]$NoMicrophone,
    [switch]$NoSpeaker,
    [double]$MicGain = 1.0,
    [int]$LowCutHz = 80,
    [double]$NoiseGateThreshold = 0.0,
    [int]$PlaybackPrebufferMs = 1500
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $Root "logs\meeting-suite"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ File = $py.Source; Prefix = @("-3") }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; Prefix = @() }
    }

    throw "Python was not found. Install Python 3.10+ or add it to PATH."
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

    $stdout = Join-Path $LogDir "$Name.out.log"
    $stderr = Join-Path $LogDir "$Name.err.log"
    $process = Start-Process `
        -FilePath $Python.File `
        -ArgumentList ($Python.Prefix + $Arguments) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru

    [pscustomobject]@{
        name = $Name
        pid = $process.Id
        cwd = $WorkingDirectory
        stdout = $stdout
        stderr = $stderr
    }
}

$Python = Resolve-PythonCommand
$Started = @()

if (-not $NoCamera) {
    $Started += Start-BridgeProcess `
        -Name "camera" `
        -WorkingDirectory (Join-Path $Root "sensorbridge-windows-clean") `
        -Arguments @("sensorbridge.py", "--port", "$CameraPort")
}

if (-not $NoMicrophone) {
    $Started += Start-BridgeProcess `
        -Name "microphone" `
        -WorkingDirectory (Join-Path $Root "sensorbridge-microphone-windows") `
        -Arguments @(
            "bridge.py",
            "--base-url", $IpadBaseUrl,
            "--duration-seconds", "0",
            "--output-gain", "$MicGain",
            "--low-cut-hz", "$LowCutHz",
            "--noise-gate-threshold", "$NoiseGateThreshold",
            "--playback-prebuffer-ms", "$PlaybackPrebufferMs",
            "webrtc-microphone"
        )
}

if (-not $NoSpeaker) {
    $Started += Start-BridgeProcess `
        -Name "speaker" `
        -WorkingDirectory (Join-Path $Root "sensorbridge-speaker-windows") `
        -Arguments @(
            "speaker_bridge.py",
            "--base-url", $IpadBaseUrl,
            "--duration-seconds", "0",
            "webrtc-speaker"
        )
}

$Started | ConvertTo-Json -Depth 4
