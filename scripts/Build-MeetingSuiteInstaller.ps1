param(
  [string]$Configuration = 'Release',
  [string]$OutputDir = '',
  [string[]]$WheelPythonVersions = @('310', '311', '312'),
  [string]$WheelhouseCacheDir = '',
  [string]$PythonRuntimeVersion = '3.12.3',
  [string]$PythonRuntimeCacheDir = '',
  [string]$PipIndexUrl = '',
  [switch]$Json
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
if (-not $OutputDir) {
  $OutputDir = Join-Path $root 'dist'
}
$WheelPythonVersions = @(
  $WheelPythonVersions | ForEach-Object {
    ($_ -split '[,; ]+') | Where-Object { $_ }
  }
)

function Resolve-Csc {
  $candidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  $fromPath = Get-Command csc.exe -ErrorAction SilentlyContinue
  if ($fromPath) {
    return $fromPath.Source
  }
  return $null
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$packageScript = Join-Path $root 'scripts\Build-MeetingSuitePackage.ps1'
$packageArgs = @(
  '-NoProfile', '-ExecutionPolicy', 'Bypass',
  '-File', $packageScript,
  '-Configuration', $Configuration,
  '-OutputDir', $OutputDir,
  '-Json'
)
if ($WheelPythonVersions -and $WheelPythonVersions.Count -gt 0) {
  $packageArgs += @('-WheelPythonVersions', ($WheelPythonVersions -join ','))
}
if ($WheelhouseCacheDir) {
  $packageArgs += @('-WheelhouseCacheDir', $WheelhouseCacheDir)
}
if ($PythonRuntimeVersion) {
  $packageArgs += @('-PythonRuntimeVersion', $PythonRuntimeVersion)
}
if ($PythonRuntimeCacheDir) {
  $packageArgs += @('-PythonRuntimeCacheDir', $PythonRuntimeCacheDir)
}
if ($PipIndexUrl) {
  $packageArgs += @('-PipIndexUrl', $PipIndexUrl)
}
$packageOutput = & powershell.exe @packageArgs
$packageReport = $packageOutput | ConvertFrom-Json
if (-not [bool]$packageReport.ok) {
  throw "Package build failed: $packageOutput"
}

$csc = Resolve-Csc
if (-not $csc) {
  throw 'csc.exe was not found. Install .NET Framework developer tools or Visual Studio Build Tools.'
}

$source = Join-Path $root 'packaging\windows-installer\SensorBridgeMeetingInstaller.cs'
if (-not (Test-Path $source)) {
  throw "Installer source not found: $source"
}

$zipPath = [string]$packageReport.zip
if (-not (Test-Path $zipPath)) {
  throw "Package zip not found: $zipPath"
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$installerExe = Join-Path $OutputDir "SensorBridgeMeetingSuiteSetup-$stamp.exe"
$iconPath = Join-Path $root 'meeting-suite\windows-app\SensorBridge.Meeting.App\obj\SensorBridgeMeeting.ico'

$arguments = @(
  '/nologo',
  '/target:winexe',
  '/codepage:65001',
  '/platform:x64',
  '/optimize+',
  '/reference:System.dll',
  '/reference:System.Core.dll',
  '/reference:System.Drawing.dll',
  '/reference:System.Windows.Forms.dll',
  '/reference:System.IO.Compression.dll',
  '/reference:System.IO.Compression.FileSystem.dll',
  "/resource:$zipPath,SensorBridgeMeetingSuitePayload.zip",
  "/out:$installerExe"
)
if (Test-Path $iconPath) {
  $arguments += "/win32icon:$iconPath"
}
$arguments += $source

$compilerOutput = & $csc @arguments 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
  throw "Installer build failed with exit code $exitCode.`n$($compilerOutput | Out-String)"
}
if (-not (Test-Path $installerExe)) {
  throw "Installer exe was not created: $installerExe"
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installerExe
$item = Get-Item -LiteralPath $installerExe

$report = [ordered]@{
  ok = $true
  command = 'build_sensorbridge_meeting_suite_installer'
  root = $root
  configuration = $Configuration
  packageZip = $zipPath
  installer = $installerExe
  installerBytes = [int64]$item.Length
  sha256 = $hash.Hash
  csc = $csc
  compilerOutput = ($compilerOutput | Out-String).Trim()
  notes = @(
    'The installer embeds the package zip as a resource.',
    'The embedded package includes a local wheelhouse for offline pip dependency installation.',
    'Double-click the installer to show a progress UI and run installation steps.',
    'VB-CABLE is checked but not silently installed.'
  )
}

if ($Json) {
  $report | ConvertTo-Json -Depth 8
} else {
  Write-Host "SensorBridge Meeting Suite installer built:"
  Write-Host "  $installerExe"
  Write-Host "SHA256:"
  Write-Host "  $($hash.Hash)"
}
