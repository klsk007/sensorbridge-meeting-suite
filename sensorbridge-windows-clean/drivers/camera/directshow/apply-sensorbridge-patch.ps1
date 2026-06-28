param()

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$sourceDir = Join-Path $root 'third_party\src\softcam'

function Update-TextFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][hashtable]$Replacements
  )
  if (-not (Test-Path $Path)) {
    throw "Missing file: $Path"
  }
  $content = Get-Content -Raw -Encoding UTF8 $Path
  $original = $content
  foreach ($key in $Replacements.Keys) {
    $content = $content.Replace([string]$key, [string]$Replacements[$key])
  }
  if ($content -ne $original) {
    Set-Content -Encoding UTF8 -NoNewline -Path $Path -Value $content
    return $true
  }
  return $false
}

$softcamCpp = Join-Path $sourceDir 'src\softcam\softcam.cpp'
$coreCpp = Join-Path $sourceDir 'src\softcamcore\DShowSoftcam.cpp'

$changed = @()
if (Update-TextFile -Path $softcamCpp -Replacements @{
  'const wchar_t FILTER_NAME[] = L"DirectShow Softcam";' = 'const wchar_t FILTER_NAME[] = L"SensorBridge Camera";'
}) {
  $changed += $softcamCpp
}

if (Update-TextFile -Path $coreCpp -Replacements @{
  'CSource(NAME("DirectShow Softcam"), lpunk, clsid)' = 'CSource(NAME("SensorBridge Camera"), lpunk, clsid)'
  'L"DirectShow Softcam Stream"' = 'L"SensorBridge Camera Stream"'
}) {
  $changed += $coreCpp
}

[ordered]@{
  ok = $true
  command = 'directshow_camera_apply_sensorbridge_patch'
  changes_system = $false
  source_dir = $sourceDir
  windows_camera_name = 'SensorBridge Camera'
  changed = $changed
  already_applied = $changed.Count -eq 0
  notes = @(
    'Patches the upstream softcam DirectShow filter friendly name to SensorBridge Camera.',
    'Does not register the filter, install drivers, enable test signing, or reboot.'
  )
} | ConvertTo-Json -Depth 4
