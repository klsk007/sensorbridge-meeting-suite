$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SensorBridge Camera.lnk'
if (Test-Path $shortcut) {
  Remove-Item -LiteralPath $shortcut -Force
}

[ordered]@{
  ok = $true
  command = 'uninstall_dev'
  product = 'camera_only'
  removed_shortcut = $shortcut
} | ConvertTo-Json -Depth 4
