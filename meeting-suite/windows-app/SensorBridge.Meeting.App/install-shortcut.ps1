param(
  [string]$Configuration = 'Release',
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $projectDir 'build.ps1'
$exe = Join-Path $projectDir "bin\$Configuration\SensorBridge.Meeting.App.exe"

if (-not (Test-Path $exe)) {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript -Configuration $Configuration | Out-Null
}

$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop 'SensorBridge Meeting Suite.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $projectDir)))
$shortcut.Description = 'SensorBridge Meeting Suite'
$shortcut.Save()

$report = [ordered]@{
  ok = (Test-Path $shortcutPath)
  command = 'install_sensorbridge_meeting_shortcut'
  changes_system = $false
  exe = $exe
  shortcut = $shortcutPath
}

if ($Json) {
  $report | ConvertTo-Json -Depth 4
} else {
  Write-Host "Shortcut installed: $shortcutPath"
}
