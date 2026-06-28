param(
  [switch]$Plan,
  [switch]$InstallAndVerify,
  [switch]$VerifyOnly,
  [string]$ConfirmSystemChange = ''
)

$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $audioRoot)
$wizardScript = Join-Path $audioRoot 'dev-install-wizard.ps1'
$mediaProbeProject = Join-Path $root 'tools\MediaDeviceProbe\MediaDeviceProbe.csproj'
$bridgeCli = Join-Path $root 'bridge.py'
. (Join-Path $root 'tools\Resolve-Python.ps1')
$python = Resolve-SensorBridgePython

function Invoke-JsonCommand {
  param([string]$FilePath, [string[]]$Arguments)
  $output = & $FilePath @Arguments 2>&1 | Out-String
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  if ($exitCode -ne 0) {
    return [ordered]@{
      ok = $false
      command = "$FilePath $($Arguments -join ' ')"
      exit_code = $exitCode
      output = $output.Trim()
    }
  }
  try {
    $payload = $output | ConvertFrom-Json
    return [ordered]@{
      ok = $true
      command = "$FilePath $($Arguments -join ' ')"
      exit_code = $exitCode
      payload = $payload
    }
  }
  catch {
    return [ordered]@{
      ok = $false
      command = "$FilePath $($Arguments -join ' ')"
      exit_code = $exitCode
      output = $output.Trim()
      error = $_.Exception.Message
    }
  }
}

function Invoke-Wizard {
  param([string[]]$Arguments)
  $allArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $wizardScript) + $Arguments
  $result = Invoke-JsonCommand -FilePath 'powershell' -Arguments $allArguments
  return $result
}

function Invoke-BridgeCli {
  param([string[]]$Arguments)
  $allArguments = @($bridgeCli) + $Arguments
  $result = Invoke-JsonCommand -FilePath $python -Arguments $allArguments
  return $result
}

function Invoke-MediaProbe {
  if (-not (Test-Path $mediaProbeProject)) {
    return [ordered]@{
      ok = $false
      command = 'dotnet run MediaDeviceProbe'
      error = 'MediaDeviceProbe project was not found.'
      project = $mediaProbeProject
    }
  }
  $result = Invoke-JsonCommand -FilePath 'dotnet' -Arguments @('run', '--no-restore', '--project', $mediaProbeProject)
  return $result
}

$actionCount = @($InstallAndVerify, $VerifyOnly) | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
if ($actionCount -gt 1) {
  throw 'Choose only one of -InstallAndVerify or -VerifyOnly.'
}

$mode = 'plan'
if ($InstallAndVerify) { $mode = 'install-and-verify' }
elseif ($VerifyOnly) { $mode = 'verify-only' }

$changesSystem = [bool]$InstallAndVerify
$requiredConfirmation = if ($InstallAndVerify) { 'INSTALL_MICROPHONE_DRIVER' } else { '' }
$confirmationOk = (-not $changesSystem) -or ($ConfirmSystemChange -eq $requiredConfirmation)

$planReport = Invoke-Wizard -Arguments @()
$verifyOnlyReport = Invoke-Wizard -Arguments @('-VerifyOnly')

$report = [ordered]@{
  ok = $true
  command = 'microphone_post_reboot_install'
  mode = $mode
  root = $root
  changes_system = $changesSystem
  required_confirmation = $requiredConfirmation
  confirmation_provided = $ConfirmSystemChange
  confirmation_ok = $confirmationOk
  install_attempted = $false
  install_result = $null
  verification_before = $verifyOnlyReport
  plan = $planReport
  media_device_probe = $null
  microphone_route_status = $null
  next_commands = @(
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -EnableTestSigning -ConfirmSystemChange ENABLE_TEST_SIGNING',
    'shutdown /r /t 0',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\post-reboot-install.ps1 -InstallAndVerify -ConfirmSystemChange INSTALL_MICROPHONE_DRIVER',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\post-reboot-install.ps1 -VerifyOnly'
  )
  notes = @(
    'Default mode is plan-only and does not install a driver.',
    'Run this after enabling Windows test signing and rebooting.',
    'InstallAndVerify requires the INSTALL_MICROPHONE_DRIVER confirmation token.'
  )
}

if ($changesSystem -and -not $confirmationOk) {
  $report.ok = $false
  $report.blocked = 'confirmation_required'
  $report | ConvertTo-Json -Depth 12
  exit 2
}

if ($InstallAndVerify) {
  $report.install_attempted = $true
  $report.install_result = Invoke-Wizard -Arguments @('-InstallDriver', '-ConfirmSystemChange', 'INSTALL_DRIVER')
}

if ($VerifyOnly -or $InstallAndVerify) {
  $report.media_device_probe = Invoke-MediaProbe
  $report.microphone_route_status = Invoke-BridgeCli -Arguments @('microphone-route-status')
  $after = Invoke-Wizard -Arguments @('-VerifyOnly')
  $report.verification_after = $after
  $micPayload = $report.microphone_route_status.payload
  if ($null -ne $micPayload) {
    $report.creates_windows_microphone_now = [bool]$micPayload.normal_app_visible
  }
}

$report | ConvertTo-Json -Depth 12
