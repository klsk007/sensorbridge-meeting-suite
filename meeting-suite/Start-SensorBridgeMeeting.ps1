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
        return @{
            ok = [bool]$productStart.ok
            virtualDevice = $virtualDevice
            mediaStart = $mediaStart
            cameraAvailable = [bool]$productStart.webrtc_connect.cameraAvailable
            directshowSenderOk = [bool]$productStart.directshow_sender.ok
            directshowSenderRunning = [bool]$productStart.directshow_sender.running
            receivedFps = $productStart.product_status.receivedFps
            decodedFps = $productStart.product_status.decodedFps
            virtualCameraFps = $productStart.product_status.virtualCameraFps
            blockers = $productStart.product_status.blockers
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

    $senderStatus = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Status") -TimeoutSeconds 45
    $build = $null
    $register = $null
    if (-not [bool]$senderStatus.exe_exists) {
        $build = Invoke-JsonScript -ScriptPath $buildScript -Arguments @("-Build") -TimeoutSeconds 240
        $senderBuild = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Build") -TimeoutSeconds 180
        $senderStatus = Invoke-JsonScript -ScriptPath $senderScript -Arguments @("-Status") -TimeoutSeconds 45
    }

    $registerStatus = Invoke-JsonScript -ScriptPath $registerScript -Arguments @("-Status") -TimeoutSeconds 60
    if (-not [bool]$registerStatus.registered_after -or -not [bool]$registerStatus.visible_to_windows_apps) {
        $register = Invoke-JsonScript -ScriptPath $registerScript -Arguments @("-Register") -TimeoutSeconds 120
        $registerStatus = Invoke-JsonScript -ScriptPath $registerScript -Arguments @("-Status") -TimeoutSeconds 60
    }

    return @{
        senderExeExists = [bool]$senderStatus.exe_exists
        senderRunning = [bool]$senderStatus.running
        registered = [bool]$registerStatus.registered_after
        visibleToWindowsApps = [bool]$registerStatus.visible_to_windows_apps
        build = $build
        register = $register
    }
}

$Python = Resolve-PythonCommand
$Started = @()

if (-not $NoCamera) {
    $camera = Start-BridgeProcess `
        -Name "camera" `
        -WorkingDirectory (Join-Path $Root "sensorbridge-windows-clean") `
        -Arguments @("sensorbridge.py", "--port", "$CameraPort", "--upstream-url", $IpadBaseUrl)
    $camera | Add-Member -NotePropertyName productStart -NotePropertyValue (Start-CameraProductMode -Port $CameraPort -UpstreamBaseUrl $IpadBaseUrl)
    $Started += $camera
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
