param(
  [switch]$Plan,
  [switch]$EnableTestSigning,
  [switch]$InstallDriver,
  [switch]$VerifyOnly,
  [string]$ConfirmSystemChange = ''
)

$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $audioRoot)
$testSigningScript = Join-Path $audioRoot 'test-signing.ps1'
$installScript = Join-Path $audioRoot 'install-dev.ps1'

function Invoke-JsonScript {
  param([string]$Script, [string[]]$Arguments)
  $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>&1 | Out-String
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  if ($exitCode -ne 0) {
    throw "$Script $($Arguments -join ' ') failed with exit code $exitCode`n$output"
  }
  return $output | ConvertFrom-Json
}

$actionCount = @($EnableTestSigning, $InstallDriver, $VerifyOnly) | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
if ($actionCount -gt 1) {
  throw 'Choose only one of -EnableTestSigning, -InstallDriver, or -VerifyOnly.'
}

$mode = 'plan'
if ($EnableTestSigning) { $mode = 'enable-test-signing' }
elseif ($InstallDriver) { $mode = 'install-driver' }
elseif ($VerifyOnly) { $mode = 'verify-only' }

$changesSystem = [bool]($EnableTestSigning -or $InstallDriver)
$requiredConfirmation = ''
if ($EnableTestSigning) { $requiredConfirmation = 'ENABLE_TEST_SIGNING' }
if ($InstallDriver) { $requiredConfirmation = 'INSTALL_DRIVER' }

$testSigning = Invoke-JsonScript -Script $testSigningScript -Arguments @('-Status')
$installStatus = Invoke-JsonScript -Script $installScript -Arguments @('-VerifyOnly')

$report = [ordered]@{
  ok = $true
  command = 'microphone_dev_install_wizard'
  mode = $mode
  root = $root
  changes_system = $changesSystem
  required_confirmation = $requiredConfirmation
  confirmation_provided = $ConfirmSystemChange
  confirmation_ok = (-not $changesSystem) -or ($ConfirmSystemChange -eq $requiredConfirmation)
  test_signing = $testSigning
  install_status = $installStatus
  action_attempted = $false
  action_result = $null
  next_commands = @(
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -EnableTestSigning -ConfirmSystemChange ENABLE_TEST_SIGNING',
    'shutdown /r /t 0',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -InstallDriver -ConfirmSystemChange INSTALL_DRIVER',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\dev-install-wizard.ps1 -VerifyOnly'
  )
  notes = @(
    'Default mode is plan-only and does not change Windows boot configuration or install a driver.',
    'Changing test signing or installing the development microphone driver requires the matching -ConfirmSystemChange token.',
    'A reboot is required after enabling test signing before Windows can load the development driver.'
  )
}

if ($changesSystem -and -not $report.confirmation_ok) {
  $report.ok = $false
  $report.blocked = 'confirmation_required'
  $report | ConvertTo-Json -Depth 10
  exit 2
}

if ($EnableTestSigning) {
  $report.action_attempted = $true
  $report.action_result = Invoke-JsonScript -Script $testSigningScript -Arguments @('-Enable')
}
elseif ($InstallDriver) {
  $report.action_attempted = $true
  $report.action_result = Invoke-JsonScript -Script $installScript -Arguments @('-Install')
}
elseif ($VerifyOnly) {
  $report.action_attempted = $true
  $report.action_result = Invoke-JsonScript -Script $installScript -Arguments @('-VerifyOnly')
}

$report | ConvertTo-Json -Depth 10
