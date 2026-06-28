param(
  [string]$BaseUrl = 'http://127.0.0.1:8765',
  [switch]$SkipServer
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$checks = [ordered]@{}

function Run-Step($Name, [scriptblock]$Action) {
  try {
    $payload = & $Action
    $checks[$Name] = [ordered]@{ ok = $true; payload = $payload }
  } catch {
    $checks[$Name] = [ordered]@{ ok = $false; error = $_.Exception.Message }
  }
}

Run-Step 'python_compile' {
  py -3 -m py_compile .\sensorbridge.py .\bridge.py .\bridgeclient\webrtc_receiver.py .\bridgeclient\models.py
}

Run-Step 'tests' {
  py -3 -m pytest -q
}

Run-Step 'windows_app_build' {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\windows-app\SensorBridge.App\build.ps1
}

Run-Step 'directshow_status' {
  py -3 .\bridge.py directshow-camera-register-status | ConvertFrom-Json
}

Run-Step 'directshow_open_status' {
  py -3 .\bridge.py directshow-camera-open-status | ConvertFrom-Json
}

$ok = -not @($checks.Values | Where-Object { -not $_.ok }).Count
[ordered]@{
  ok = [bool]$ok
  command = 'verify_dev'
  product = 'camera_only'
  checks = $checks
} | ConvertTo-Json -Depth 8
