param(
  [string]$Configuration = 'Release'
)

$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $toolDir 'Program.cs'
$outDir = Join-Path $toolDir "bin\$Configuration"
$outExe = Join-Path $outDir 'RootDeviceInstaller.exe'

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
  $cmd = Get-Command csc.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  return $null
}

$report = [ordered]@{
  ok = $false
  command = 'root_device_installer_build'
  changes_system = $false
  source = $source
  output = $outExe
  csc = $null
  errors = @()
}

$csc = Resolve-Csc
$report.csc = $csc
if (-not $csc) {
  $report.errors += 'csc.exe was not found.'
  $report | ConvertTo-Json -Depth 4
  exit 1
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$arguments = @(
  '/nologo',
  '/optimize+',
  '/target:exe',
  "/out:$outExe",
  $source
)
$output = & $csc @arguments 2>&1
if ($LASTEXITCODE -ne 0) {
  $report.errors += "csc.exe failed with exit code $LASTEXITCODE."
  $report.compiler_output = ($output | Out-String).Trim()
  $report | ConvertTo-Json -Depth 4
  exit $LASTEXITCODE
}

$report.ok = Test-Path $outExe
$report.length = if ($report.ok) { (Get-Item $outExe).Length } else { 0 }
$report | ConvertTo-Json -Depth 4
