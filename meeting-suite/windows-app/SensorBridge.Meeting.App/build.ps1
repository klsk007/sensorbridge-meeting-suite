param(
  [string]$Configuration = 'Release',
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$objDir = Join-Path $projectDir 'obj'
$outDir = Join-Path $projectDir "bin\$Configuration"
$iconPath = Join-Path $objDir 'SensorBridgeMeeting.ico'
$exePath = Join-Path $outDir 'SensorBridge.Meeting.App.exe'
New-Item -ItemType Directory -Force -Path $objDir, $outDir | Out-Null

function Resolve-Csc {
  $candidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return $candidate }
  }
  $fromPath = Get-Command csc.exe -ErrorAction SilentlyContinue
  if ($fromPath) { return $fromPath.Source }
  return $null
}

function New-MeetingIcon {
  param([string]$Path)
  Add-Type -AssemblyName System.Drawing
  $bitmap = New-Object System.Drawing.Bitmap 64, 64
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $graphics.Clear([System.Drawing.Color]::FromArgb(27, 92, 108))
  $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (New-Object System.Drawing.Rectangle 0, 0, 64, 64),
    [System.Drawing.Color]::FromArgb(38, 155, 132),
    [System.Drawing.Color]::FromArgb(27, 92, 108),
    35
  )
  $graphics.FillRectangle($brush, 0, 0, 64, 64)
  $font = New-Object System.Drawing.Font 'Segoe UI', 20, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
  $format = New-Object System.Drawing.StringFormat
  $format.Alignment = [System.Drawing.StringAlignment]::Center
  $format.LineAlignment = [System.Drawing.StringAlignment]::Center
  $graphics.DrawString('AV', $font, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF 0, 0, 64, 64), $format)
  $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
  $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create)
  try { $icon.Save($stream) } finally {
    $stream.Dispose(); $icon.Dispose(); $format.Dispose(); $font.Dispose(); $brush.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
  }
}

$csc = Resolve-Csc
$report = [ordered]@{
  ok = $false
  command = 'build_sensorbridge_meeting_app'
  changes_system = $false
  project_dir = $projectDir
  configuration = $Configuration
  csc = $csc
  exe = $exePath
  icon = $iconPath
  errors = @()
}

if (-not $csc) {
  $report.errors += 'csc.exe was not found. Install .NET Framework developer tools or Visual Studio Build Tools.'
} else {
  try {
    New-MeetingIcon -Path $iconPath
    $source = Join-Path $projectDir 'Program.cs'
    $references = @(
      '/reference:System.dll',
      '/reference:System.Core.dll',
      '/reference:System.Windows.Forms.dll',
      '/reference:System.Drawing.dll',
      '/reference:System.Web.Extensions.dll'
    )
    $arguments = @(
      '/nologo',
      '/target:winexe',
      '/codepage:65001',
      '/platform:x64',
      '/optimize+',
      "/out:$exePath",
      "/win32icon:$iconPath"
    ) + $references + @($source)
    $output = & $csc @arguments 2>&1
    $report.compiler_output = ($output | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
      $report.errors += "csc.exe failed with exit code $LASTEXITCODE."
    }
  } catch {
    $report.errors += $_.Exception.Message
  }
}

$report.exe_exists = Test-Path $exePath
$report.ok = ($report.errors.Count -eq 0) -and [bool]$report.exe_exists

if ($Json) {
  Write-Output ($report | ConvertTo-Json -Depth 5)
} elseif ($report.ok) {
  Write-Host "SensorBridge Meeting Suite app built:"
  Write-Host "  $exePath"
} else {
  Write-Host "SensorBridge Meeting Suite app build failed:"
  foreach ($errorItem in $report.errors) { Write-Host "  $errorItem" }
  exit 1
}
