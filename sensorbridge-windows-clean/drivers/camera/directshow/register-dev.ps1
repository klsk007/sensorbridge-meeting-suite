param(
  [switch]$Register,
  [switch]$Unregister,
  [switch]$Status,
  [string]$Configuration = 'Release',
  [string]$Platform = 'x64'
)

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$sourceDir = Join-Path $root 'third_party\src\softcam'
$dllPath = Join-Path $sourceDir "dist\bin\$Platform\softcam.dll"
$installerExe = Join-Path $sourceDir "examples\softcam_installer\$Platform\$Configuration\softcam_installer.exe"
$sampleSenderExe = Join-Path $sourceDir "examples\sender\$Platform\$Configuration\sender.exe"
$senderExe = Join-Path $root "windows-app\SensorBridge.DirectShowSender\$Platform\$Configuration\SensorBridge.DirectShowSender.exe"
$regsvr32 = Join-Path $env:SystemRoot 'System32\regsvr32.exe'
$directshowProbe = Join-Path $root 'tools\directshow-device-probe.ps1'

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-SoftcamRegistryEvidence {
  $keys = @(
    'HKCR:\CLSID',
    'HKLM:\SOFTWARE\Classes\CLSID',
    'HKLM:\SOFTWARE\WOW6432Node\Classes\CLSID'
  )
  $matches = @()
  foreach ($key in $keys) {
    if (-not (Test-Path $key)) {
      continue
    }
    try {
      $matches += Get-ChildItem $key -ErrorAction SilentlyContinue |
        Where-Object {
          $value = (Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue).'(default)'
          $name = if ($value) { [string]$value } else { [string]$_.PSChildName }
          $name -match 'Softcam|SensorBridge'
        } |
        Select-Object -First 20 |
        ForEach-Object {
          $value = (Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue).'(default)'
          [ordered]@{
            path = $_.Name
            name = if ($value) { [string]$value } else { $null }
          }
        }
    } catch {
    }
  }
  return @($matches)
}

function Invoke-DirectShowProbe {
  if (-not (Test-Path $directshowProbe)) {
    return [ordered]@{
      ok = $false
      error = [ordered]@{
        code = 'directshow_probe_missing'
        message = "DirectShow probe script was not found: $directshowProbe"
      }
    }
  }
  try {
    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $directshowProbe
    return $output | ConvertFrom-Json
  } catch {
    return [ordered]@{
      ok = $false
      error = [ordered]@{
        code = 'directshow_probe_failed'
        message = $_.Exception.Message
      }
    }
  }
}

function Test-DirectShowProbeSeesSensorBridgeCamera {
  param($Probe)
  if (-not $Probe -or -not $Probe.ok) {
    return $false
  }
  $devices = @($Probe.videoInput)
  foreach ($device in $devices) {
    if ([string]$device.name -match 'SensorBridge') {
      return $true
    }
  }
  return $false
}

$admin = Test-Admin
$dllExists = Test-Path $dllPath
$installerExists = Test-Path $installerExe
$senderExists = Test-Path $senderExe
$sampleSenderExists = Test-Path $sampleSenderExe
$senderProcesses = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -eq $senderExe -or ($_.ProcessName -eq 'SensorBridge.DirectShowSender' -and $senderExists)
})
$evidence = Get-SoftcamRegistryEvidence

$report = [ordered]@{
  ok = $true
  component = 'softcam'
  command = 'directshow_camera_register'
  purpose = 'Windows 10-compatible DirectShow SensorBridge Camera fallback'
  changes_system = [bool]($Register -or $Unregister)
  installs_driver_or_camera = $false
  registers_directshow_filter = [bool]$Register
  unregisters_directshow_filter = [bool]$Unregister
  requires_admin = [bool]($Register -or $Unregister)
  admin = $admin
  source_dir = $sourceDir
  platform = $Platform
  configuration = $Configuration
  artifacts = [ordered]@{
    softcam_dll = $dllPath
    softcam_dll_exists = $dllExists
    installer_exe = $installerExe
    installer_exe_exists = $installerExists
    sender_exe = $senderExe
    sender_exe_exists = $senderExists
    sample_sender_exe = $sampleSenderExe
    sample_sender_exe_exists = $sampleSenderExists
    regsvr32 = $regsvr32
    regsvr32_exists = (Test-Path $regsvr32)
    directshow_probe = $directshowProbe
    directshow_probe_exists = (Test-Path $directshowProbe)
  }
  registry_evidence = $evidence
  registered_now = ($evidence.Count -gt 0)
  sender_running = ($senderProcesses.Count -gt 0)
  sender_processes = @($senderProcesses | ForEach-Object {
    [ordered]@{
      id = $_.Id
      process_name = $_.ProcessName
      path = $_.Path
    }
  })
  creates_windows_camera_now = $false
  visible_to_windows_apps = $false
  notes = @(
    'softcam registration writes COM/DirectShow registry entries; it does not install a kernel driver.',
    'This script does not reboot, enable test signing, or install non-camera drivers.',
    'Camera support is not complete until Windows enumeration sees SensorBridge Camera or the registered DirectShow device.'
  )
}

$blocks = @()
if (-not $dllExists) {
  $blocks += 'softcam.dll is missing; run drivers\camera\directshow\build-dev.ps1 -Fetch -Build.'
}
if (-not (Test-Path $regsvr32)) {
  $blocks += 'regsvr32.exe was not found.'
}
if (($Register -or $Unregister) -and -not $admin) {
  $blocks += 'Administrator rights are required to register/unregister the DirectShow filter.'
}

if ($Register) {
  if ($blocks.Count -gt 0) {
    $report.ok = $false
  }
  else {
    $proc = Start-Process -FilePath $regsvr32 -ArgumentList @('/s', $dllPath) -Wait -PassThru
    $report.register_exit_code = $proc.ExitCode
    $report.ok = $proc.ExitCode -eq 0
  }
}

if ($Unregister) {
  if (-not $dllExists) {
    $report.ok = $false
  }
  elseif (-not $admin) {
    $report.ok = $false
  }
  else {
    $proc = Start-Process -FilePath $regsvr32 -ArgumentList @('/u', '/s', $dllPath) -Wait -PassThru
    $report.unregister_exit_code = $proc.ExitCode
    $report.ok = $proc.ExitCode -eq 0
  }
}

$evidenceAfter = Get-SoftcamRegistryEvidence
$probeAfter = Invoke-DirectShowProbe
$probeSeesSensorBridgeCamera = Test-DirectShowProbeSeesSensorBridgeCamera -Probe $probeAfter
$report.registry_evidence_after = $evidenceAfter
$report.registered_after = ($evidenceAfter.Count -gt 0)
$report.directshow_probe = $probeAfter
$report.creates_windows_camera_now = $false
$report.visible_to_windows_apps = $probeSeesSensorBridgeCamera
if ($blocks.Count -gt 0) {
  $report.blocks = $blocks
}

$report | ConvertTo-Json -Depth 8
