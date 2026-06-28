param(
  [int]$Port = 8765,
  [string]$HostName = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root 'windows-app\SensorBridge.App\bin\Release\SensorBridge.App.exe'
if (-not (Test-Path $app)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'windows-app\SensorBridge.App\build.ps1') | Out-Null
}

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'SensorBridge Camera.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $app
$shortcut.WorkingDirectory = Split-Path $app -Parent
$shortcut.Arguments = "--project-root `"$root`" --port $Port --host-name `"$HostName`""
$shortcut.Description = 'SensorBridge camera-only Windows app'
$shortcut.IconLocation = "$app,0"
$shortcut.Save()

[ordered]@{
  ok = $true
  command = 'install_dev'
  product = 'camera_only'
  shortcut = $shortcutPath
  target = $app
} | ConvertTo-Json -Depth 4
