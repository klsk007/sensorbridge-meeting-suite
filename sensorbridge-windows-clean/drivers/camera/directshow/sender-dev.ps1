param(
  [switch]$Build,
  [switch]$Start,
  [switch]$Stop,
  [switch]$Status,
  [string]$Configuration = 'Release',
  [string]$Platform = 'x64',
  [string]$FrameDir = '',
  [int]$Width = 640,
  [int]$Height = 480,
  [double]$Fps = 30.0
)

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$senderDir = Join-Path $root 'windows-app\SensorBridge.DirectShowSender'
$buildScript = Join-Path $senderDir 'build.ps1'
$exe = Join-Path $senderDir "$Platform\$Configuration\SensorBridge.DirectShowSender.exe"
if (-not $FrameDir) {
  $FrameDir = Join-Path $env:ProgramData 'SensorBridge\camera'
}

function Get-SenderProcesses {
  $resolved = if (Test-Path $exe) { (Resolve-Path $exe).Path } else { $exe }
  return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.ProcessName -eq 'SensorBridge.DirectShowSender') -or ($_.Path -eq $resolved)
  })
}

function Get-LatestFrameEvidence {
  $latestBmp = Join-Path $FrameDir 'latest.bmp'
  $latestJson = Join-Path $FrameDir 'latest.json'
  return [ordered]@{
    frame_dir = $FrameDir
    frame_dir_exists = (Test-Path $FrameDir)
    latest_bmp = $latestBmp
    latest_bmp_exists = (Test-Path $latestBmp)
    latest_metadata = $latestJson
    latest_metadata_exists = (Test-Path $latestJson)
  }
}

function Quote-ProcessArgument {
  param([string]$Value)

  if ($Value -match '[\s"]') {
    return '"' + ($Value -replace '"', '\"') + '"'
  }
  return $Value
}

function Join-ProcessArguments {
  param([string[]]$ArgumentList)

  return (($ArgumentList | ForEach-Object { Quote-ProcessArgument $_ }) -join ' ')
}

$buildReport = $null
if ($Build) {
  if (-not (Test-Path $buildScript)) {
    $buildReport = [ordered]@{
      ok = $false
      error = "Build script missing: $buildScript"
    }
  } else {
    $buildJson = & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript -Build -Configuration $Configuration -Platform $Platform
    try {
      $buildReport = $buildJson | ConvertFrom-Json
    } catch {
      $buildReport = $buildJson
    }
  }
}

if ($Stop) {
  foreach ($process in Get-SenderProcesses) {
    Stop-Process -Id $process.Id -Force
  }
  Start-Sleep -Milliseconds 250
}

$blocks = @()
if (-not (Test-Path $exe)) {
  $blocks += 'SensorBridge.DirectShowSender.exe is missing; run this script with -Build.'
}

$startedProcess = $null
$alreadyRunningBeforeStart = $false
if ($Start) {
  if ($blocks.Count -eq 0) {
    $existingProcesses = Get-SenderProcesses
    $alreadyRunningBeforeStart = ($existingProcesses.Count -gt 0)
    if (-not $alreadyRunningBeforeStart) {
      New-Item -ItemType Directory -Force -Path $FrameDir | Out-Null
      $args = @(
        '--frame-dir', $FrameDir,
        '--width', [string]$Width,
        '--height', [string]$Height,
        '--fps', [string]$Fps
      )
      $startup = ([wmiclass]'Win32_ProcessStartup').CreateInstance()
      $startup.ShowWindow = 0
      $commandLine = '"' + $exe + '" ' + (Join-ProcessArguments $args)
      $createResult = ([wmiclass]'Win32_Process').Create($commandLine, $senderDir, $startup)
      if ([int]$createResult.ReturnValue -ne 0) {
        throw "Failed to start SensorBridge.DirectShowSender.exe with Win32_Process.Create return code $($createResult.ReturnValue)."
      }
      Start-Sleep -Milliseconds 600
    }
  }
}

$processes = Get-SenderProcesses
$report = [ordered]@{
  ok = ($blocks.Count -eq 0)
  command = 'directshow_camera_sender'
  changes_system = $false
  installs_driver_or_camera = $false
  component = 'SensorBridge.DirectShowSender'
  provider_api = 'DirectShow.softcam'
  build_requested = [bool]$Build
  start_requested = [bool]$Start
  stop_requested = [bool]$Stop
  status_requested = [bool]$Status
  build = $buildReport
  exe = $exe
  exe_exists = (Test-Path $exe)
  frame = Get-LatestFrameEvidence
  width = $Width
  height = $Height
  fps = $Fps
  running = ($processes.Count -gt 0)
  already_running_before_start = $alreadyRunningBeforeStart
  started_pid = if ($startedProcess) { $startedProcess.Id } else { $null }
  processes = @($processes | ForEach-Object {
    [ordered]@{
      id = $_.Id
      process_name = $_.ProcessName
      path = $_.Path
    }
  })
  notes = @(
    'Runs a user-mode SensorBridge frame-file sender for the registered DirectShow softcam filter.',
    'The sender reads latest.bmp from ProgramData\SensorBridge\camera and publishes frames to SensorBridge Camera.',
    'This does not install drivers, enable test signing, or reboot.'
  )
}

if ($blocks.Count -gt 0) {
  $report.ok = $false
  $report.blocks = $blocks
}

$report | ConvertTo-Json -Depth 8
