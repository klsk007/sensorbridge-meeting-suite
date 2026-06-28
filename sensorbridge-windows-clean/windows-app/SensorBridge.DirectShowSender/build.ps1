param(
  [switch]$Build,
  [string]$Configuration = 'Release',
  [string]$Platform = 'x64'
)

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$project = Join-Path $scriptDir 'SensorBridge.DirectShowSender.vcxproj'
$exe = Join-Path $scriptDir "$Platform\$Configuration\SensorBridge.DirectShowSender.exe"
$softcamLib = Join-Path $root 'third_party\src\softcam\dist\lib\x64\softcam.lib'
$softcamDll = Join-Path $root 'third_party\src\softcam\dist\bin\x64\softcam.dll'

function Find-MSBuild {
  $cmd = Get-Command msbuild.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
  if (Test-Path $vswhere) {
    $path = (& $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe 2>$null | Select-Object -First 1)
    if ($path) {
      return [string]$path
    }
  }
  return $null
}

$msbuild = Find-MSBuild
$report = [ordered]@{
  ok = $true
  command = 'directshow_camera_sender_build'
  changes_system = $false
  installs_driver_or_camera = $false
  component = 'SensorBridge.DirectShowSender'
  provider_api = 'DirectShow.softcam'
  project = $project
  project_exists = (Test-Path $project)
  msbuild = $msbuild
  configuration = $Configuration
  platform = $Platform
  build_requested = [bool]$Build
  build_attempted = $false
  exe = $exe
  exe_exists = (Test-Path $exe)
  softcam_lib = $softcamLib
  softcam_lib_exists = (Test-Path $softcamLib)
  softcam_dll = $softcamDll
  softcam_dll_exists = (Test-Path $softcamDll)
  notes = @(
    'Builds the SensorBridge frame-file to DirectShow softcam sender.',
    'This does not register the DirectShow filter, install drivers, enable test signing, or reboot.'
  )
}

$blocks = @()
if (-not (Test-Path $project)) {
  $blocks += 'SensorBridge.DirectShowSender.vcxproj is missing.'
}
if (-not $msbuild) {
  $blocks += 'MSBuild was not found. Install Visual Studio 2019/2022 Build Tools with Desktop development with C++.'
}
if (-not (Test-Path $softcamLib) -or -not (Test-Path $softcamDll)) {
  $blocks += 'softcam build artifacts are missing; run drivers\camera\directshow\build-dev.ps1 -Fetch -Build.'
}

if ($Build) {
  if ($blocks.Count -gt 0) {
    $report.ok = $false
  } else {
    $report.build_attempted = $true
    & $msbuild $project /m "/p:Configuration=$Configuration" "/p:Platform=$Platform"
    $exitCode = $LASTEXITCODE
    $report.msbuild_exit_code = $exitCode
    if ($exitCode -ne 0) {
      $report.ok = $false
      $blocks += "MSBuild failed with exit code $exitCode."
    }
  }
}

$report.exe_exists = (Test-Path $exe)
if ($blocks.Count -gt 0) {
  $report.blocks = $blocks
}

$report | ConvertTo-Json -Depth 6
