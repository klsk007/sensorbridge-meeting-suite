param(
  [switch]$Status,
  [switch]$Install,
  [switch]$VerifyOnly,
  [string]$Configuration = 'Debug',
  [string]$Platform = 'x64'
)

$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $audioRoot)
$sourceDir = Join-Path $root 'third_party\src\Windows-driver-samples\audio\sysvad'
$buildDir = Join-Path $sourceDir "$Platform\$Configuration"
$packageDir = Join-Path $buildDir 'package'
$certificate = Join-Path $buildDir 'package.cer'

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-TestSigningStatus {
  $text = (& bcdedit /enum 2>&1 | Out-String)
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  return [ordered]@{
    checked = $true
    exit_code = $exitCode
    enabled = ($text -match '(?im)^\s*testsigning\s+Yes\s*$')
    requires_admin_to_change = $true
  }
}

function Find-DevCon {
  $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Tools'
  if (Test-Path $kits) {
    $found = Get-ChildItem -Path $kits -Recurse -Filter devcon.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\x64\\devcon\.exe$' } |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($found) {
      return $found.FullName
    }
  }
  $cmd = Get-Command devcon.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  return $null
}

function Find-RootDeviceInstaller {
  $candidate = Join-Path $root 'tools\RootDeviceInstaller\bin\Release\RootDeviceInstaller.exe'
  if (Test-Path $candidate) {
    return $candidate
  }
  return $null
}

function Test-Package {
  $required = @(
    'TabletAudioSample.sys',
    'ComponentizedAudioSample.inf',
    'ComponentizedAudioSampleExtension.inf',
    'ComponentizedApoSample.inf',
    'sysvad.cat',
    'SwapAPO.dll',
    'DelayAPO.dll',
    'KWSApo.dll',
    'AecApo.dll',
    'KeywordDetectorContosoAdapter.dll'
  )
  $missing = @()
  foreach ($name in $required) {
    if (-not (Test-Path (Join-Path $packageDir $name))) {
      $missing += $name
    }
  }
  return [ordered]@{
    package_dir = $packageDir
    exists = Test-Path $packageDir
    missing_files = $missing
    complete = ((Test-Path $packageDir) -and ($missing.Count -eq 0))
    certificate = $certificate
    certificate_exists = Test-Path $certificate
  }
}

function Get-RootHardwareId {
  $inf = Join-Path $packageDir 'ComponentizedAudioSample.inf'
  if ((Test-Path $inf) -and ((Get-Content -Raw -Path $inf) -match 'Root\\SensorBridge_VirtualMicrophone')) {
    return 'Root\SensorBridge_VirtualMicrophone'
  }
  return 'Root\Sysvad_ComponentizedAudioSample'
}

function Test-SensorBridgePackage {
  $paths = @(
    (Join-Path $packageDir 'ComponentizedAudioSample.inf'),
    (Join-Path $packageDir 'ComponentizedAudioSampleExtension.inf'),
    (Join-Path $packageDir 'ComponentizedApoSample.inf')
  )
  $text = ''
  foreach ($path in $paths) {
    if (Test-Path $path) {
      $text += "`n" + (Get-Content -Raw -Path $path)
    }
  }
  return ($text -match 'SensorBridge') -and ($text -match 'Root\\SensorBridge_VirtualMicrophone')
}

function Get-SensorBridgeMicrophoneVerification {
  $matchedDevices = @()
  $audioEndpoints = @()
  $captureEndpoints = @()
  $renderEndpoints = @()
  $errors = @()
  try {
    $devices = @(Get-PnpDevice -ErrorAction Stop)
    foreach ($device in $devices) {
      $name = [string]$device.FriendlyName
      $class = [string]$device.Class
      $instanceId = [string]$device.InstanceId
      $isSensorBridge = ($name -match 'SensorBridge') -or ($instanceId -match 'SensorBridge_VirtualMicrophone')
      $isMicClass = $class -in @('AudioEndpoint', 'MEDIA')
      if ($isSensorBridge -and $isMicClass) {
        $item = [pscustomobject][ordered]@{
          name = $name
          class = $class
          status = [string]$device.Status
          instance_id = $instanceId
        }
        $matchedDevices += ,$item
        if ($class -eq 'AudioEndpoint') {
          $audioEndpoints += ,$item
          if ($instanceId -match '\{0\.0\.1\.') {
            $captureEndpoints += ,$item
          }
          else {
            $renderEndpoints += ,$item
          }
        }
      }
    }
  }
  catch {
    $errors += $_.Exception.Message
  }

  return [ordered]@{
    checked = $true
    method = 'Get-PnpDevice SensorBridge capture AudioEndpoint/MEDIA match'
    installed = ($captureEndpoints.Count -gt 0)
    driver_node_present = ($matchedDevices.Count -gt 0)
    audio_endpoint_count = $captureEndpoints.Count
    capture_endpoint_count = $captureEndpoints.Count
    render_endpoint_count = $renderEndpoints.Count
    matched_device_count = $matchedDevices.Count
    matched_capture_endpoints = $captureEndpoints
    matched_render_endpoints = $renderEndpoints
    matched_devices = $matchedDevices
    errors = $errors
  }
}

function Invoke-Checked {
  param([string]$FilePath, [string[]]$Arguments)
  $output = & $FilePath @Arguments 2>&1 | Out-String
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  $isPnPUtilExpectedSuccess = (
    ([IO.Path]::GetFileName($FilePath) -ieq 'pnputil.exe') -and
    (
      (($exitCode -eq 259) -and ($output -match 'Driver package added successfully|Driver package is up-to-date|Added driver packages:\s+0')) -or
      (($exitCode -eq 3010) -and ($output -match 'Driver package added successfully|System reboot is needed'))
    )
  )
  $isDevConExpectedSuccess = (
    ([IO.Path]::GetFileName($FilePath) -ieq 'devcon.exe') -and
    ($output -match 'Drivers installed successfully|Device node created')
  )
  if (($exitCode -ne 0) -and (-not $isPnPUtilExpectedSuccess) -and (-not $isDevConExpectedSuccess)) {
    throw "$FilePath $($Arguments -join ' ') failed with exit code $exitCode`n$output"
  }
  return [ordered]@{
    command = "$FilePath $($Arguments -join ' ')"
    exit_code = $exitCode
    treated_as_success = [bool]($isPnPUtilExpectedSuccess -or $isDevConExpectedSuccess)
    output = $output.Trim()
  }
}

function ConvertTo-JsonReady {
  param($Value)

  if ($null -eq $Value) {
    return $null
  }
  if ($Value -is [string]) {
    return $Value
  }
  if ($Value -is [System.Collections.IDictionary]) {
    $copy = [ordered]@{}
    foreach ($key in $Value.Keys) {
      $copy[[string]$key] = ConvertTo-JsonReady $Value[$key]
    }
    return [pscustomobject]$copy
  }
  if ($Value -is [System.Collections.IEnumerable]) {
    $items = @()
    foreach ($item in $Value) {
      $items += ,(ConvertTo-JsonReady $item)
    }
    return ,$items
  }
  return $Value
}

function Write-JsonReport {
  param($Report)
  ConvertTo-JsonReady $Report | ConvertTo-Json -Depth 8
}

$admin = Test-Admin
$testSigning = Get-TestSigningStatus
$devcon = Find-DevCon
$rootDeviceInstaller = Find-RootDeviceInstaller
$package = Test-Package
$rootHardwareId = Get-RootHardwareId
$sensorBridgePackage = Test-SensorBridgePackage
$verification = Get-SensorBridgeMicrophoneVerification
$installBlocks = @()
if (-not $admin) {
  $installBlocks += 'Administrator shell is required.'
}
if (-not $testSigning.enabled) {
  $installBlocks += 'Windows test signing is disabled.'
}
if ((-not $devcon) -and (-not $rootDeviceInstaller)) {
  $installBlocks += 'WDK devcon.exe was not found and SensorBridge RootDeviceInstaller.exe has not been built.'
}
if (-not $package.complete) {
  $installBlocks += 'SysVAD driver package is incomplete.'
}
if (-not $package.certificate_exists) {
  $installBlocks += 'SysVAD test certificate is missing.'
}
if (-not $sensorBridgePackage) {
  $installBlocks += 'SensorBridge-patched SysVAD package has not been built.'
}

$report = [ordered]@{
  ok = $true
  component = 'Windows-driver-samples/audio/sysvad'
  mode = 'development-driver-install'
  source_dir = $sourceDir
  admin = $admin
  test_signing = $testSigning
  devcon = $devcon
  root_device_installer = $rootDeviceInstaller
  root_device_install_method = if ($devcon) { 'devcon' } elseif ($rootDeviceInstaller) { 'setupapi_root_device_installer' } else { $null }
  package = $package
  sensorbridge_package = $sensorBridgePackage
  root_hardware_id = $rootHardwareId
  verification = $verification
  status_requested = [bool]$Status
  install_requested = [bool]$Install
  verify_only_requested = [bool]$VerifyOnly
  install_attempted = $false
  can_install_now = ($installBlocks.Count -eq 0)
  install_blocks = $installBlocks
  reboot_required_before_install = (-not $testSigning.enabled)
  creates_windows_microphone_after_install = 'must_be_verified_after_install'
  creates_windows_microphone_now = [bool]$verification.installed
  requires_admin_for_install = $true
  requires_test_signing_for_development = $true
  requires_driver_signing_for_release = $true
  next_commands = @(
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\test-signing.ps1 -Enable',
    'shutdown /r /t 0',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\build-dev.ps1 -ApplySensorBridgePatch -Build',
    'powershell -ExecutionPolicy Bypass -File .\tools\RootDeviceInstaller\build.ps1',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -Install',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -VerifyOnly',
    'dotnet run --project .\tools\MediaDeviceProbe\MediaDeviceProbe.csproj'
  )
  notes = @(
    'Default mode is status-only and does not change the system.',
    'Development install requires a SensorBridge-patched package and test signing enabled before running -Install.',
    'If WDK devcon.exe is unavailable, the guarded SensorBridge RootDeviceInstaller helper can create the root-enumerated device through Windows SetupAPI.',
    'Run drivers\audio\test-signing.ps1 -Enable from an administrator shell, then reboot, before installing this test-signed package.'
  )
}

if ($VerifyOnly) {
  Write-JsonReport $report
  exit 0
}

if ($Install) {
  if (-not $admin) {
    throw 'Administrator shell is required to install a development audio driver.'
  }
  if (-not $testSigning.enabled) {
    throw 'Windows test signing is not enabled. Run: bcdedit /set testsigning on ; reboot ; then rerun this script with -Install.'
  }
  if ((-not $devcon) -and (-not $rootDeviceInstaller)) {
    throw 'Neither devcon.exe nor RootDeviceInstaller.exe was found. Build the helper with tools\RootDeviceInstaller\build.ps1 or install WDK tools before installing the root-enumerated SysVAD sample.'
  }
  if (-not $package.complete) {
    throw "Driver package is incomplete. Build it first with drivers\audio\build-dev.ps1 -Build."
  }
  if (-not $package.certificate_exists) {
    throw "Test certificate is missing: $certificate"
  }
  if (-not $sensorBridgePackage) {
    throw 'SensorBridge-patched SysVAD package has not been built. Run drivers\audio\build-dev.ps1 -ApplySensorBridgePatch -Build first.'
  }

  $report.install_attempted = $true
  $installResults = @()
  $rootImport = Import-Certificate -FilePath $certificate -CertStoreLocation Cert:\LocalMachine\Root
  $publisherImport = Import-Certificate -FilePath $certificate -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
  $installResults += [ordered]@{
    command = "Import-Certificate $certificate LocalMachine\Root"
    thumbprint = $rootImport.Thumbprint
  }
  $installResults += [ordered]@{
    command = "Import-Certificate $certificate LocalMachine\TrustedPublisher"
    thumbprint = $publisherImport.Thumbprint
  }

  Push-Location $packageDir
  try {
    if ($devcon) {
      $existingRootDevice = Get-PnpDevice -InstanceId 'ROOT\SENSORBRIDGE_VIRTUALMICROPHONE\0000' -ErrorAction SilentlyContinue
      $devconVerb = if ($existingRootDevice) { 'update' } else { 'install' }
      $installResults += Invoke-Checked $devcon @($devconVerb, 'ComponentizedAudioSample.inf', $rootHardwareId)
    } else {
      $installResults += Invoke-Checked $rootDeviceInstaller @(
        'install',
        '--inf',
        (Join-Path $packageDir 'ComponentizedAudioSample.inf'),
        '--hardware-id',
        $rootHardwareId
      )
    }
    $pnputil = (Get-Command pnputil.exe).Source
    $installResults += Invoke-Checked $pnputil @('/add-driver', 'ComponentizedApoSample.inf', '/install')
    $installResults += Invoke-Checked $pnputil @('/add-driver', 'ComponentizedAudioSampleExtension.inf', '/install')
  } finally {
    Pop-Location
  }
  $report.install_results = $installResults
  Start-Sleep -Seconds 2
  $report.verification_after_install = Get-SensorBridgeMicrophoneVerification
  $report.creates_windows_microphone_now = [bool]$report.verification_after_install.installed
}

Write-JsonReport $report
