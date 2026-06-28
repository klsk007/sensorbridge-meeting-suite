param(
  [switch]$Register,
  [switch]$Unregister,
  [switch]$Start,
  [switch]$Stop,
  [switch]$Status,
  [string]$Configuration = 'Debug',
  [string]$Platform = 'x64',
  [string]$DeployDir = 'C:\ProgramData\SensorBridge\VCamSample'
)

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}
$cameraRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $cameraRoot)
$sourceOutput = Join-Path $root "third_party\src\VCamSample\$Platform\$Configuration"
$sourceExe = Join-Path $sourceOutput 'VCamSample.exe'
$sourceDll = Join-Path $sourceOutput 'VCamSampleSource.dll'
$deployedExe = Join-Path $DeployDir 'VCamSample.exe'
$deployedDll = Join-Path $DeployDir 'VCamSampleSource.dll'
$regsvr32 = Join-Path $env:WINDIR 'System32\regsvr32.exe'

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-VCamSample {
  $processes = @(Get-Process VCamSample -ErrorAction SilentlyContinue)
  if ($processes.Count -eq 0) {
    return
  }

  $processes | Stop-Process -Force
  foreach ($process in $processes) {
    try {
      Wait-Process -Id $process.Id -Timeout 10 -ErrorAction Stop
    }
    catch {
      $stillRunning = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
      if ($stillRunning) {
        throw "VCamSample process $($process.Id) did not exit within 10 seconds."
      }
    }
  }
}

function Test-VCamRegistered {
  return Test-Path 'HKLM:\Software\Classes\CLSID\{3cad447d-f283-4af4-a3b2-6f5363309f52}\InprocServer32'
}

function Stop-CameraFrameServer {
  $service = Get-Service -Name FrameServer -ErrorAction SilentlyContinue
  if (-not $service -or $service.Status -ne 'Running') {
    return $false
  }

  Stop-Service -Name FrameServer -Force -ErrorAction Stop
  $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(10))
  return $true
}

function Start-CameraFrameServer {
  $service = Get-Service -Name FrameServer -ErrorAction SilentlyContinue
  if ($service -and $service.Status -ne 'Running') {
    Start-Service -Name FrameServer -ErrorAction SilentlyContinue
  }
}

function Copy-VCamOutput {
  if (-not (Test-Path $sourceExe) -or -not (Test-Path $sourceDll)) {
    throw "VCamSample build output was not found under $sourceOutput. Run drivers\camera\build-dev.ps1 -Build first."
  }

  New-Item -ItemType Directory -Force -Path $DeployDir | Out-Null
  Copy-Item -Force $sourceExe, $sourceDll -Destination $DeployDir
  Get-ChildItem $DeployDir -File | Unblock-File -ErrorAction SilentlyContinue
}

function Test-MFVirtualCameraCompatibility {
  $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
  $osVersion = [Environment]::OSVersion.Version
  $dllPath = Join-Path $env:WINDIR 'System32\mfsensorgroup.dll'
  $dllExists = Test-Path $dllPath
  $dllLoadable = $false
  $exported = $false
  $loadError = $null

  if ($dllExists) {
    $signature = @'
using System;
using System.Runtime.InteropServices;
public static class SensorBridgeNativeProbe {
  [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern IntPtr LoadLibrary(string lpFileName);
  [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Ansi)]
  public static extern IntPtr GetProcAddress(IntPtr hModule, string procName);
}
'@
    if (-not ('SensorBridgeNativeProbe' -as [type])) {
      Add-Type -TypeDefinition $signature
    }
    $module = [SensorBridgeNativeProbe]::LoadLibrary($dllPath)
    if ($module -ne [IntPtr]::Zero) {
      $dllLoadable = $true
      $exported = ([SensorBridgeNativeProbe]::GetProcAddress($module, 'MFCreateVirtualCamera') -ne [IntPtr]::Zero)
    }
    else {
      $loadError = "LoadLibrary failed with Win32 error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())."
    }
  }

  $build = if ($os -and $os.BuildNumber) { [int]$os.BuildNumber } else { [int]$osVersion.Build }
  $supported = ($build -ge 22000) -and $dllLoadable -and $exported
  return [ordered]@{
    ok = $true
    command = 'mf_virtual_camera_compatibility'
    changes_system = $false
    os = [ordered]@{
      caption = if ($os) { $os.Caption } else { $null }
      version = if ($os) { $os.Version } else { $osVersion.ToString() }
      build = $build
    }
    required_build = 22000
    mfsensorgroup_dll = [ordered]@{
      path = $dllPath
      exists = $dllExists
      loadable = $dllLoadable
      load_error = $loadError
    }
    mfcreatevirtualcamera = [ordered]@{
      exported = $exported
      callable = $exported
    }
    mf_virtual_camera_supported = $supported
    status = if ($supported) { 'supported' } else { 'unsupported_on_this_windows_build_or_runtime' }
    fallback_required = -not $supported
    fallback_recommendation = if ($supported) { $null } else { 'Use a Windows 10-compatible DirectShow virtual source filter, or run the Media Foundation provider on Windows build 22000+ with mfsensorgroup.dll exporting MFCreateVirtualCamera.' }
  }
}

$compatibility = Test-MFVirtualCameraCompatibility

$report = [ordered]@{
  ok = $true
  component = 'VCamSample'
  mode = 'development-session'
  provider_api = 'MediaFoundation.MFCreateVirtualCamera'
  compatibility = $compatibility
  os_version = $compatibility.os.version
  mf_virtual_camera_supported_by_current_os = $compatibility.mf_virtual_camera_supported
  fallback_required = $compatibility.fallback_required
  fallback_recommendation = $compatibility.fallback_recommendation
  deploy_dir = $DeployDir
  source_output = $sourceOutput
  admin = Test-Admin
  registered_before = Test-VCamRegistered
  running_before = [bool](Get-Process VCamSample -ErrorAction SilentlyContinue)
  frame_server_running_before = [bool]((Get-Service -Name FrameServer -ErrorAction SilentlyContinue).Status -eq 'Running')
  frame_server_stopped_for_copy = $false
  register_requested = [bool]$Register
  unregister_requested = [bool]$Unregister
  start_requested = [bool]$Start
  stop_requested = [bool]$Stop
  installs_permanent_camera = $false
  creates_camera_while_process_runs = $compatibility.mf_virtual_camera_supported
  notes = @(
    'Registers the upstream VCamSample COM media source in HKLM for development only.',
    'VCamSample depends on MFCreateVirtualCamera, which is supported for this sample on Windows 11.',
    'Starts a session-lifetime Media Foundation virtual camera; closing VCamSample removes the camera.',
    'When the SensorBridge frame-file patch has been built, VCamSampleSource reads ProgramData\SensorBridge\camera\latest.bmp.'
  )
}

if ($Stop -or $Unregister) {
  Stop-VCamSample
}

if (($Register -or $Start) -and -not $compatibility.mf_virtual_camera_supported) {
  $report.ok = $false
  $report.skipped = $true
  $report.creates_camera_while_process_runs = $false
  $report.error = [ordered]@{
    code = 'unsupported_on_this_windows_build_or_runtime'
    message = 'MFCreateVirtualCamera is not available on this Windows build/runtime; VCamSample was not launched.'
  }
  $report.registered_after = Test-VCamRegistered
  $report.running_after = [bool](Get-Process VCamSample -ErrorAction SilentlyContinue)
  $report.frame_server_running_after = [bool]((Get-Service -Name FrameServer -ErrorAction SilentlyContinue).Status -eq 'Running')
  $report.status_requested = [bool]$Status
  $report | ConvertTo-Json -Depth 8
  exit 0
}

if ($Register) {
  if (-not $report.admin) {
    throw 'Administrator rights are required to register VCamSampleSource.dll in HKLM.'
  }
  Stop-VCamSample
  $report.frame_server_stopped_for_copy = Stop-CameraFrameServer
  Copy-VCamOutput
  $reg = Start-Process -FilePath $regsvr32 -ArgumentList @('/s', $deployedDll) -Wait -PassThru
  $report.register_exit_code = $reg.ExitCode
  if ($reg.ExitCode -ne 0) {
    $report.ok = $false
  }
  if ($report.frame_server_stopped_for_copy) {
    Start-CameraFrameServer
  }
}

if ($Unregister) {
  if (-not $report.admin) {
    throw 'Administrator rights are required to unregister VCamSampleSource.dll from HKLM.'
  }
  if (Test-Path $deployedDll) {
    $reg = Start-Process -FilePath $regsvr32 -ArgumentList @('/s', '/u', $deployedDll) -Wait -PassThru
    $report.unregister_exit_code = $reg.ExitCode
    if ($reg.ExitCode -ne 0) {
      $report.ok = $false
    }
  }
}

if ($Start) {
  if (-not (Test-Path $deployedExe)) {
    Copy-VCamOutput
  }
  if (-not (Test-VCamRegistered)) {
    throw 'VCamSampleSource.dll is not registered. Run this script with -Register first.'
  }
  $existing = @(Get-Process VCamSample -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($existing.Count -gt 0) {
    $report.already_running = $true
    $report.started_process_id = $existing[0].Id
    $report.started_process_running = $true
  }
  else {
    $proc = Start-Process -FilePath $deployedExe -WorkingDirectory $DeployDir -WindowStyle Minimized -PassThru
    Start-Sleep -Seconds 3
    $report.already_running = $false
    $report.started_process_id = $proc.Id
    $report.started_process_running = -not $proc.HasExited
  }
}

$report.registered_after = Test-VCamRegistered
$report.running_after = [bool](Get-Process VCamSample -ErrorAction SilentlyContinue)
$report.frame_server_running_after = [bool]((Get-Service -Name FrameServer -ErrorAction SilentlyContinue).Status -eq 'Running')
$report.status_requested = [bool]$Status

$report | ConvertTo-Json -Depth 5
