param(
  [string]$SourceDir = ''
)

$ErrorActionPreference = 'Stop'
$cameraRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $cameraRoot)
if (-not $SourceDir) {
  $SourceDir = Join-Path $root 'third_party\src\VCamSample'
}

$framePatchOutput = & (Join-Path $cameraRoot 'apply-frame-file-patch.ps1') -SourceDir $SourceDir
$framePatchReport = $framePatchOutput | ConvertFrom-Json
$resource = Join-Path $SourceDir 'VCamSample\VCamSample.rc'
if (-not (Test-Path $resource)) {
  throw "VCamSample resource file not found: $resource"
}

function Update-Text {
  param(
    [string]$Text,
    [string]$Old,
    [string]$New,
    [ref]$Changed
  )
  if ($Text.Contains($New)) {
    return $Text
  }
  if (-not $Text.Contains($Old)) {
    throw "Expected resource snippet not found: $Old"
  }
  $Changed.Value = $true
  return $Text.Replace($Old, $New)
}

$changed = $false
$text = Get-Content -Raw -Path $resource
$text = Update-Text -Text $text -Old 'CAPTION "About VCamSample"' -New 'CAPTION "About SensorBridge Camera"' -Changed ([ref]$changed)
$text = Update-Text -Text $text -Old 'LTEXT           "VCamSample, Version 1.0",IDC_STATIC,42,14,114,8,SS_NOPREFIX' -New 'LTEXT           "SensorBridge Camera, Version 0.1",IDC_STATIC,42,14,150,8,SS_NOPREFIX' -Changed ([ref]$changed)
$text = Update-Text -Text $text -Old 'VALUE "FileDescription", "Virtual Camera Sample for Windows 11"' -New 'VALUE "FileDescription", "SensorBridge virtual camera for Windows"' -Changed ([ref]$changed)
$text = Update-Text -Text $text -Old 'VALUE "ProductName", "VCamSample"' -New 'VALUE "ProductName", "SensorBridge Camera"' -Changed ([ref]$changed)
$text = Update-Text -Text $text -Old 'IDS_APP_TITLE           "VCamSample"' -New 'IDS_APP_TITLE           "SensorBridge Camera"' -Changed ([ref]$changed)
$text = Update-Text -Text $text -Old 'IDC_VCAMSAMPLE          "VCAMSAMPLE"' -New 'IDC_VCAMSAMPLE          "SENSORBRIDGE_CAMERA"' -Changed ([ref]$changed)

if ($changed) {
  Set-Content -Path $resource -Value $text -Encoding UTF8 -NoNewline
}

[ordered]@{
  ok = $true
  component = 'VCamSample'
  mode = 'sensorbridge-camera-patch'
  source_dir = $SourceDir
  frame_file_patch = $framePatchReport
  branding_changed = $changed
  applied = ($changed -or [bool]$framePatchReport.applied)
  already_applied = (-not $changed -and [bool]$framePatchReport.already_applied)
  windows_camera_name = 'SensorBridge Camera'
  frame_file_dir = Join-Path $env:ProgramData 'SensorBridge\camera'
} | ConvertTo-Json -Depth 8
