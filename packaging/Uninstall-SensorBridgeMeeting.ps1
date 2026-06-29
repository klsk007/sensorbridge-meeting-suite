param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'SensorBridgeMeetingSuite'),
  [switch]$RemoveFiles,
  [switch]$Json
)

$ErrorActionPreference = 'Continue'

function Resolve-FullPathIfExists {
  param([string]$Path)
  try {
    if (Test-Path $Path) {
      return (Resolve-Path -LiteralPath $Path).ProviderPath
    }
    return [System.IO.Path]::GetFullPath($Path)
  } catch {
    return $Path
  }
}

function Remove-ShortcutIfExists {
  param([string]$Path)
  if (Test-Path $Path) {
    Remove-Item -LiteralPath $Path -Force
    return $true
  }
  return $false
}

$targetRoot = Resolve-FullPathIfExists $InstallDir
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'SensorBridge Meeting Suite.lnk'
$startMenuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'SensorBridge Meeting Suite'
$startShortcut = Join-Path $startMenuDir 'SensorBridge Meeting Suite.lnk'
$stopScript = Join-Path $targetRoot 'meeting-suite\Stop-SensorBridgeMeeting.ps1'

$stopResult = $null
if (Test-Path $stopScript) {
  try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript 2>&1
    $stopResult = @{
      ok = ($LASTEXITCODE -eq 0)
      exitCode = $LASTEXITCODE
      output = ($output -join "`n")
    }
  } catch {
    $stopResult = @{ ok = $false; error = $_.Exception.Message }
  }
}

$removedShortcuts = @()
if (Remove-ShortcutIfExists -Path $desktopShortcut) {
  $removedShortcuts += $desktopShortcut
}
if (Remove-ShortcutIfExists -Path $startShortcut) {
  $removedShortcuts += $startShortcut
}
try {
  if ((Test-Path $startMenuDir) -and -not @(Get-ChildItem -LiteralPath $startMenuDir -Force).Count) {
    Remove-Item -LiteralPath $startMenuDir -Force
  }
} catch {
}

$removedFiles = $false
$removeFilesError = $null
if ($RemoveFiles) {
  try {
    $resolved = Resolve-FullPathIfExists $targetRoot
    $leaf = Split-Path -Leaf $resolved.TrimEnd('\')
    if ($leaf -ne 'SensorBridgeMeetingSuite') {
      throw "Refusing to remove unexpected install directory: $resolved"
    }
    if (Test-Path $resolved) {
      Remove-Item -LiteralPath $resolved -Recurse -Force
      $removedFiles = $true
    }
  } catch {
    $removeFilesError = $_.Exception.Message
  }
}

$report = [ordered]@{
  ok = -not [bool]$removeFilesError
  command = 'uninstall_sensorbridge_meeting_suite'
  installDir = $targetRoot
  stopResult = $stopResult
  removedShortcuts = $removedShortcuts
  removeFilesRequested = [bool]$RemoveFiles
  removedFiles = $removedFiles
  removeFilesError = $removeFilesError
  notes = @(
    'This removes app shortcuts and optionally the installed app files.',
    'VB-CABLE and the registered DirectShow camera filter are not removed automatically.'
  )
}

if ($Json) {
  $report | ConvertTo-Json -Depth 6
} else {
  Write-Host "SensorBridge Meeting Suite uninstall cleanup completed."
  if ($removedShortcuts.Count -gt 0) {
    Write-Host "Removed shortcuts:"
    foreach ($shortcut in $removedShortcuts) {
      Write-Host "  $shortcut"
    }
  }
  if ($RemoveFiles) {
    Write-Host "Removed files: $removedFiles"
    if ($removeFilesError) {
      Write-Host "Remove files error: $removeFilesError"
    }
  }
}
