param(
  [string]$Configuration = 'Release',
  [string]$BaseUrl = 'http://192.168.0.24:27180',
  [string]$RelayUrl = 'http://192.168.0.23:27181',
  [string]$OutputDevice = 'CABLE Input',
  [string]$ShortcutName = 'SensorBridge Microphone.lnk',
  [switch]$NoBuild,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $projectDir)
$exe = Join-Path $projectDir "bin\$Configuration\SensorBridge.Microphone.App.exe"
$buildScript = Join-Path $projectDir 'build.ps1'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop $ShortcutName

$report = [ordered]@{
  ok = $false
  command = 'install_sensorbridge_microphone_shortcut'
  changes_system = $true
  exe = $exe
  shortcut = $shortcutPath
  base_url = $BaseUrl
  relay_url = $RelayUrl
  output_device = $OutputDevice
  build_attempted = $false
  build_ok = $null
  build_report = $null
  errors = @()
}

if (-not (Test-Path $exe)) {
  if ($NoBuild) {
    $report.errors += "App executable was not found: $exe"
  } elseif (-not (Test-Path $buildScript)) {
    $report.errors += "App executable was not found and build.ps1 was missing: $exe"
  } else {
    $report.build_attempted = $true
    $buildJson = & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript -Configuration $Configuration -Json
    $buildReport = $buildJson | ConvertFrom-Json
    $report.build_report = $buildReport
    $report.build_ok = [bool]$buildReport.ok
    if (-not $report.build_ok) {
      $report.errors += "App build failed; run build.ps1 for details."
    }
  }
}

if ((Test-Path $exe) -and ($report.errors.Count -eq 0)) {
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $exe
  $shortcut.Arguments = "--project-root `"$root`" --base-url `"$BaseUrl`" --relay-url `"$RelayUrl`" --output-device `"$OutputDevice`""
  $shortcut.WorkingDirectory = $root
  $shortcut.IconLocation = "$exe,0"
  $shortcut.Description = 'SensorBridge Microphone'
  $shortcut.Save()
}

$report.shortcut_exists = Test-Path $shortcutPath
$report.ok = ($report.errors.Count -eq 0) -and [bool]$report.shortcut_exists

if ($Json) {
  Write-Output ($report | ConvertTo-Json -Depth 5)
} elseif ($report.ok) {
  Write-Host "Shortcut installed:"
  Write-Host "  $shortcutPath"
} else {
  Write-Host "Shortcut install failed:"
  foreach ($errorItem in $report.errors) { Write-Host "  $errorItem" }
  exit 1
}
