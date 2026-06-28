param(
  [switch]$Status,
  [switch]$Enable,
  [switch]$Disable
)

$ErrorActionPreference = 'Stop'

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-TestSigningStatus {
  $text = (& bcdedit /enum "{current}" 2>&1 | Out-String)
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  return [ordered]@{
    checked = ($exitCode -eq 0)
    exit_code = $exitCode
    enabled = ($text -match '(?im)^\s*testsigning\s+Yes\s*$')
    raw_contains_testsigning = ($text -match '(?im)^\s*testsigning\s+')
  }
}

function Invoke-Bcdedit {
  param([string]$Value)
  $output = & bcdedit /set testsigning $Value 2>&1 | Out-String
  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  if ($exitCode -ne 0) {
    throw "bcdedit /set testsigning $Value failed with exit code $exitCode`n$output"
  }
  return [ordered]@{
    command = "bcdedit /set testsigning $Value"
    exit_code = $exitCode
    output = $output.Trim()
  }
}

$admin = Test-Admin
$before = Get-TestSigningStatus
$changesSystem = [bool]($Enable -or $Disable)

$report = [ordered]@{
  ok = $true
  component = 'Windows test signing'
  mode = 'development-driver-test-signing'
  admin = $admin
  status_requested = [bool]$Status
  enable_requested = [bool]$Enable
  disable_requested = [bool]$Disable
  changes_system = $changesSystem
  before = $before
  attempted = $false
  reboot_required_after_change = $false
  next_commands = @(
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\test-signing.ps1 -Enable',
    'shutdown /r /t 0',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -Install',
    'powershell -ExecutionPolicy Bypass -File .\drivers\audio\install-dev.ps1 -VerifyOnly'
  )
  notes = @(
    'Default mode is status-only and does not change boot configuration.',
    'Enabling or disabling test signing changes Windows boot configuration and requires an administrator shell.',
    'A reboot is required before Windows will load development test-signed drivers.'
  )
}

if ($Enable -and $Disable) {
  throw 'Choose only one of -Enable or -Disable.'
}

if ($changesSystem) {
  if (-not $admin) {
    throw 'Administrator shell is required to change Windows test signing.'
  }
  $report.attempted = $true
  if ($Enable) {
    $report.change = Invoke-Bcdedit -Value 'on'
  } else {
    $report.change = Invoke-Bcdedit -Value 'off'
  }
  $report.after = Get-TestSigningStatus
  $report.reboot_required_after_change = $true
} else {
  $report.after = $before
}

$report | ConvertTo-Json -Depth 6
