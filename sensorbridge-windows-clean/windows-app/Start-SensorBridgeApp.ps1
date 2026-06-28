param(
  [int]$Port = 8765,
  [string]$HostName = '127.0.0.1',
  [string]$UpstreamUrl = 'http://192.168.0.24:27180',
  [switch]$ProductMode,
  [switch]$OpenDashboard,
  [switch]$Json,
  [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = 'py'
$baseUrl = "http://${HostName}:$Port"
$serverProcess = $null
$started = $false

function Invoke-JsonGet($Path) {
  Invoke-RestMethod -Uri "$baseUrl$Path" -Method Get -TimeoutSec 5
}

function Invoke-JsonPost($Path, $Body = @{}) {
  $jsonBody = $Body | ConvertTo-Json -Depth 8
  Invoke-RestMethod -Uri "$baseUrl$Path" -Method Post -ContentType 'application/json' -Body $jsonBody -TimeoutSec 30
}

function Test-ServerReady {
  try {
    $health = Invoke-JsonGet '/health'
    return [bool]$health.ok
  } catch {
    return $false
  }
}

if (-not (Test-ServerReady) -and -not $NoStart) {
  $args = @('-3', (Join-Path $root 'sensorbridge.py'), '--host', $HostName, '--port', [string]$Port, '--upstream-url', $UpstreamUrl)
  if ($ProductMode) {
    $args += '--start-directshow-camera-sender'
  }
  $serverProcess = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $root -PassThru -WindowStyle Hidden
  $started = $true
  $deadline = (Get-Date).AddSeconds(15)
  while ((Get-Date) -lt $deadline) {
    if (Test-ServerReady) { break }
    Start-Sleep -Milliseconds 250
  }
}

$ready = Test-ServerReady
$productStart = $null
$status = $null
$cameraProviderStatus = $null
$directShowStatus = $null
$openStatus = $null

if ($ready -and $ProductMode) {
  try {
    $productStart = Invoke-JsonPost '/api/v1/product/start'
  } catch {
    $productStart = [ordered]@{
      ok = $false
      command = 'start_product_mode'
      error = $_.Exception.Message
    }
  }
}

if ($ready) {
  try { $status = Invoke-JsonGet '/api/v1/product/status' } catch {}
  try { $cameraProviderStatus = Invoke-JsonGet '/api/camera/provider/status' } catch {}
  try { $directShowStatus = Invoke-JsonGet '/api/directshow/camera/status' } catch {}
  try { $openStatus = Invoke-JsonGet '/api/directshow/camera/open-status' } catch {}
}

if ($OpenDashboard -and $ready) {
  Start-Process "$baseUrl/"
}

$report = [ordered]@{
  ok = [bool]$ready
  command = 'start_sensorbridge_camera_app'
  product = 'camera_only'
  base_url = $baseUrl
  upstream_url = $UpstreamUrl
  server_started = [bool]$started
  server_process_id = if ($serverProcess) { $serverProcess.Id } else { $null }
  product_mode_requested = [bool]$ProductMode
  activeCameraTransport = if ($status) { $status.activeCameraTransport } else { $null }
  receivedFps = if ($status) { $status.receivedFps } else { $null }
  decodedFps = if ($status) { $status.decodedFps } else { $null }
  virtualCameraFps = if ($status) { $status.virtualCameraFps } else { $null }
  latestFrameAgeMs = if ($status) { $status.latestFrameAgeMs } else { $null }
  estimatedLatencyMs = if ($status) { $status.estimatedLatencyMs } else { $null }
  droppedFrames = if ($status) { $status.droppedFrames } else { $null }
  normalWindowsCameraVisible = if ($status) { $status.normalWindowsCameraVisible } else { $null }
  product_start = $productStart
  product_status = $status
  camera_provider_status = $cameraProviderStatus
  directshow_camera_status = $directShowStatus
  directshow_open_status = $openStatus
  notes = @(
    'Camera-only launcher. Product Mode starts WebRTC/H.264 receiver and SensorBridge Camera sender only.',
    'If WebRTC is unavailable, the camera remains unavailable.'
  )
}

if ($Json) {
  $report | ConvertTo-Json -Depth 12
} else {
  Write-Host "SensorBridge Camera"
  Write-Host "URL: $baseUrl/"
  Write-Host "Ready: $ready"
  if ($status) {
    Write-Host "activeCameraTransport: $($status.activeCameraTransport)"
    Write-Host "receivedFps: $($status.receivedFps)"
    Write-Host "decodedFps: $($status.decodedFps)"
    Write-Host "virtualCameraFps: $($status.virtualCameraFps)"
  }
}
