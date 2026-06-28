$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root 'windows-app\SensorBridge.App\bin\Release\SensorBridge.App.exe'
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SensorBridge Camera.lnk'

[ordered]@{
  ok = $true
  command = 'install_status'
  product = 'camera_only'
  app_exists = Test-Path $app
  shortcut_exists = Test-Path $shortcut
  app = $app
  shortcut = $shortcut
} | ConvertTo-Json -Depth 4
