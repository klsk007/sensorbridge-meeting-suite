param(
  [string]$BaseUrl = 'http://127.0.0.1:8765',
  [string]$NameContains = 'SensorBridge',
  [int]$TimeoutMilliseconds = 5000,
  [string]$Output = 'data\meeting-camera-probe.bmp',
  [switch]$TencentConfirmed
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = 'py'

function Invoke-Step($Name, [scriptblock]$Action) {
  try {
    $payload = & $Action
    return [ordered]@{
      name = $Name
      ok = if ($null -ne $payload.ok) { [bool]$payload.ok } else { $true }
      payload = $payload
    }
  } catch {
    return [ordered]@{
      name = $Name
      ok = $false
      error = $_.Exception.Message
    }
  }
}

function Invoke-BridgeCommand([string[]]$BridgeArgs) {
  $json = & $python -3 (Join-Path $root 'bridge.py') @BridgeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "bridge.py $($BridgeArgs -join ' ') failed with exit code $LASTEXITCODE`: $json"
  }
  return $json | ConvertFrom-Json
}

function Invoke-HttpJson([string]$Path) {
  return Invoke-RestMethod -Uri "$BaseUrl$Path" -Method Get -TimeoutSec 5
}

function Get-ProductStatusSummary($Payload) {
  if (-not $Payload) {
    return $null
  }
  return [ordered]@{
    ok = [bool]$Payload.ok
    command = $Payload.command
    product = $Payload.product
    activeCameraTransport = $Payload.activeCameraTransport
    receivedFps = $Payload.receivedFps
    decodedFps = $Payload.decodedFps
    virtualCameraFps = $Payload.virtualCameraFps
    latestFrameAgeMs = $Payload.latestFrameAgeMs
    estimatedLatencyMs = $Payload.estimatedLatencyMs
    droppedFrames = $Payload.droppedFrames
    normalWindowsCameraVisible = $Payload.normalWindowsCameraVisible
  }
}

function Find-TencentMeeting {
  $processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(WeMeet|TencentMeeting|TencentMeetingRoom|wemeet|wemeetapp)$' -or
    $_.Path -match 'Tencent|WeMeet'
  } | ForEach-Object {
    [ordered]@{
      id = $_.Id
      process_name = $_.ProcessName
      path = $_.Path
      main_window_title = $_.MainWindowTitle
    }
  })

  $pathCandidates = @()
  if ($env:LOCALAPPDATA) {
    $pathCandidates += Join-Path $env:LOCALAPPDATA 'Tencent\WeMeet\wemeetapp.exe'
  }
  if ($env:ProgramFiles) {
    $pathCandidates += Join-Path $env:ProgramFiles 'Tencent\WeMeet\wemeetapp.exe'
  }
  if (${env:ProgramFiles(x86)}) {
    $pathCandidates += Join-Path ${env:ProgramFiles(x86)} 'Tencent\WeMeet\wemeetapp.exe'
  }
  $knownPaths = @($pathCandidates | Where-Object { $_ -and (Test-Path $_) })

  return [ordered]@{
    running = $processes.Count -gt 0
    processes = $processes
    known_paths = @($knownPaths)
  }
}

Push-Location $root
try {
  $steps = [ordered]@{}
  $steps.product_status = Invoke-Step 'product_status' {
    $payload = Invoke-HttpJson '/api/v1/product/status'
    $summary = Get-ProductStatusSummary $payload
    if ($summary.product -ne 'camera_only') {
      throw "Product service at $BaseUrl is not the camera-only build. Reported product='$($summary.product)'."
    }
    return $summary
  }
  $steps.directshow_register_status = Invoke-Step 'directshow_register_status' {
    Invoke-BridgeCommand @('directshow-camera-register-status')
  }
  $steps.directshow_sender_status = Invoke-Step 'directshow_sender_status' {
    Invoke-BridgeCommand @('directshow-camera-sender-status')
  }
  $steps.directshow_open_status = Invoke-Step 'directshow_open_status' {
    Invoke-BridgeCommand @('--timeout-ms', [string]$TimeoutMilliseconds, 'directshow-camera-open-status')
  }

  $dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
  $dotnetSdks = @()
  if ($dotnet) {
    $dotnetSdks = @(& $dotnet.Source --list-sdks 2>$null)
  }
  if ($dotnet -and $dotnetSdks.Count -gt 0) {
    $steps.winrt_media_capture = Invoke-Step 'winrt_media_capture' {
      $probeArgs = @(
        'run',
        '--project',
        (Join-Path $root 'tools\CameraFrameProbe\CameraFrameProbe.csproj'),
        '--',
        '--name-contains',
        $NameContains,
        '--output',
        $Output
      )
      $json = & $dotnet.Source @probeArgs 2>&1
      if ($LASTEXITCODE -ne 0) {
        throw "CameraFrameProbe failed with exit code $LASTEXITCODE`: $json"
      }
      return $json | ConvertFrom-Json
    }
  } else {
    $steps.winrt_media_capture = [ordered]@{
      name = 'winrt_media_capture'
      ok = $false
      error = 'dotnet SDK not found; cannot run MediaCapture probe used as a closer proxy for normal Windows camera apps.'
    }
  }

  $tencent = Find-TencentMeeting
  $directshowOk = [bool]$steps.directshow_open_status.ok
  $winrtOk = [bool]$steps.winrt_media_capture.ok
  $transport = $null
  if ($steps.product_status.ok -and $steps.product_status.payload) {
    $transport = $steps.product_status.payload.activeCameraTransport
  }
  $activeTransportOk = ($transport -eq 'webrtc')
  $tencentUsable = $directshowOk -and $winrtOk -and [bool]$TencentConfirmed

  $blockers = @()
  if (-not $steps.product_status.ok) { $blockers += 'Product status endpoint is not the camera-only build or is not reachable.' }
  if (-not $activeTransportOk) { $blockers += 'activeCameraTransport is not webrtc.' }
  if (-not $directshowOk) { $blockers += 'DirectShow open probe failed.' }
  if (-not $winrtOk) { $blockers += 'WinRT MediaCapture probe failed or could not run.' }
  if (-not $TencentConfirmed) { $blockers += 'Tencent Meeting was not manually confirmed with SensorBridge Camera selected and preview visible.' }

  $report = [ordered]@{
    ok = $tencentUsable
    command = 'meeting_camera_acceptance'
    product = 'camera_only'
    activeCameraTransport = $transport
    directShowOpensSensorBridgeCamera = $directshowOk
    winRtMediaCaptureOpensSensorBridgeCamera = $winrtOk
    tencentMeetingDetected = [bool]$tencent.running
    tencentMeetingUsable = $tencentUsable
    tencentMeetingManualConfirmation = [bool]$TencentConfirmed
    dotnetSdkAvailable = [bool]($dotnet -and $dotnetSdks.Count -gt 0)
    dotnetSdks = @($dotnetSdks)
    blockers = $blockers
    tencent = $tencent
    steps = $steps
    manual_test = [ordered]@{
      required = -not [bool]$TencentConfirmed
      instruction = 'Open Tencent Meeting settings, select SensorBridge Camera, verify preview is live, then rerun this script with -TencentConfirmed.'
    }
  }

  $report | ConvertTo-Json -Depth 12
  if (-not $report.ok) {
    exit 1
  }
} finally {
  Pop-Location
}
