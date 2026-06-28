param(
  [switch]$Fetch,
  [switch]$Build,
  [switch]$SkipSensorBridgePatch,
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
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$sourceDir = Join-Path $root 'third_party\src\softcam'
$solution = Join-Path $sourceDir 'softcam.sln'
$vs2019Solution = Join-Path $sourceDir 'softcam_vs2019.sln'
$softcamProject = Join-Path $sourceDir 'src\softcam\softcam.vcxproj'
$softcamVs2019Project = Join-Path $sourceDir 'src\softcam\softcam_vs2019.vcxproj'
$installerSolution = Join-Path $sourceDir 'examples\softcam_installer\softcam_installer.sln'
$installerVs2019Project = Join-Path $sourceDir 'examples\softcam_installer\softcam_installer_vs2019.vcxproj'
$senderSolution = Join-Path $sourceDir 'examples\sender\sender.sln'
$senderVs2019Project = Join-Path $sourceDir 'examples\sender\sender_vs2019.vcxproj'
$patchScript = Join-Path $scriptDir 'apply-sensorbridge-patch.ps1'
$dllPath = Join-Path $sourceDir "dist\bin\$Platform\softcam.dll"
$installerExe = Join-Path $sourceDir "examples\softcam_installer\$Platform\$Configuration\softcam_installer.exe"
$senderExe = Join-Path $sourceDir "examples\sender\$Platform\$Configuration\sender.exe"

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

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-InstalledPlatformToolsets {
  $toolsets = @()
  $roots = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2019'),
    (Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\2022'),
    (Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\2019')
  )
  foreach ($rootPath in $roots) {
    if (-not (Test-Path $rootPath)) {
      continue
    }
    $toolsets += Get-ChildItem -Path $rootPath -Recurse -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match 'PlatformToolsets$' } |
      ForEach-Object { Get-ChildItem -Path $_.FullName -Directory -ErrorAction SilentlyContinue } |
      Select-Object -ExpandProperty Name
  }
  return @($toolsets | Sort-Object -Unique)
}

function Invoke-MSBuildChecked {
  param([Parameter(Mandatory=$true)][string]$ProjectPath)
  & $msbuild $ProjectPath /m "/p:Configuration=$Configuration" "/p:Platform=$Platform"
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "MSBuild failed with exit code $exitCode for $ProjectPath"
  }
}

function Sync-SoftcamVs2019Dist {
  $nestedDist = Join-Path $sourceDir 'src\softcam\dist'
  if (-not (Test-Path $nestedDist)) {
    return $false
  }
  $targets = @(
    @('include\softcam\softcam.h', 'include\softcam\softcam.h'),
    @("lib\$Platform\softcam.lib", "lib\$Platform\softcam.lib"),
    @("bin\$Platform\softcam.dll", "bin\$Platform\softcam.dll")
  )
  foreach ($pair in $targets) {
    $from = Join-Path $nestedDist $pair[0]
    $to = Join-Path (Join-Path $sourceDir 'dist') $pair[1]
    if (Test-Path $from) {
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
      Copy-Item -Force -LiteralPath $from -Destination $to
    }
  }
  return $true
}

if ($Fetch) {
  & (Join-Path $root 'third_party\fetch-third-party.ps1') -Component softcam -UpdateExisting
}

$msbuild = Find-MSBuild
$installedToolsets = Get-InstalledPlatformToolsets
$sourceExists = Test-Path $sourceDir
$solutionExists = Test-Path $solution
$vs2019SolutionExists = Test-Path $vs2019Solution
$useVs2019Projects = ($installedToolsets -contains 'v142') -and -not ($installedToolsets -contains 'v143')
$softcamProjectToBuild = if ($useVs2019Projects -and (Test-Path $softcamVs2019Project)) { $softcamVs2019Project } else { $softcamProject }
$installerProjectToBuild = if ($useVs2019Projects -and (Test-Path $installerVs2019Project)) { $installerVs2019Project } else { $installerSolution }
$senderProjectToBuild = if ($useVs2019Projects -and (Test-Path $senderVs2019Project)) { $senderVs2019Project } else { $senderSolution }
$dllExistsBefore = Test-Path $dllPath
$installerExistsBefore = Test-Path $installerExe
$senderExistsBefore = Test-Path $senderExe

$report = [ordered]@{
  ok = $true
  component = 'softcam'
  command = 'directshow_camera_build'
  purpose = 'Windows 10-compatible DirectShow SensorBridge Camera fallback'
  changes_system = $false
  installs_driver_or_camera = $false
  requires_admin = $false
  source_dir = $sourceDir
  source_exists = $sourceExists
  solution = $solution
  solution_exists = $solutionExists
  vs2019_solution = $vs2019Solution
  vs2019_solution_exists = $vs2019SolutionExists
  softcam_project = $softcamProjectToBuild
  installer_solution = $installerSolution
  installer_project = $installerProjectToBuild
  sender_solution = $senderSolution
  sender_project = $senderProjectToBuild
  configuration = $Configuration
  platform = $Platform
  msbuild = $msbuild
  installed_platform_toolsets = $installedToolsets
  fetch_requested = [bool]$Fetch
  build_requested = [bool]$Build
  build_attempted = $false
  sensorbridge_patch_requested = -not [bool]$SkipSensorBridgePatch
  sensorbridge_patch = $null
  synced_vs2019_dist = $false
  output = [ordered]@{
    softcam_dll = $dllPath
    softcam_dll_exists = $dllExistsBefore
    installer_exe = $installerExe
    installer_exe_exists = $installerExistsBefore
    sender_exe = $senderExe
    sender_exe_exists = $senderExistsBefore
  }
  readiness = [ordered]@{
    can_build_now = $false
    can_register_after_build = $false
    creates_windows_camera_now = $false
  }
  notes = @(
    'softcam is an MIT DirectShow Video Input Device filter and sender API.',
    'This script fetches/builds only; it does not register the camera filter or install drivers.',
    'Registration is handled by register-dev.ps1 and requires explicit -Register plus administrator permissions.'
  )
}

$blocks = @()
if (-not $sourceExists) {
  $blocks += 'softcam source is missing; run with -Fetch.'
}
if (-not $solutionExists) {
  $blocks += 'softcam.sln was not found under third_party\src\softcam.'
}
if (-not $msbuild) {
  $blocks += 'MSBuild was not found. Install Visual Studio 2022 or 2019 Build Tools with Desktop development with C++ and Windows 10 SDK.'
}
if ($sourceExists -and -not (Test-Path $softcamProjectToBuild)) {
  $blocks += "softcam runtime project was not found: $softcamProjectToBuild"
}

$report.readiness.can_build_now = ($blocks.Count -eq 0)

if ($Build) {
  if ($blocks.Count -gt 0) {
    $report.ok = $false
  }
  else {
    $report.build_attempted = $true
    try {
      if (-not $SkipSensorBridgePatch) {
        if (-not (Test-Path $patchScript)) {
          throw "Missing SensorBridge softcam patch script: $patchScript"
        }
        $patchOutput = & $patchScript
        try {
          $report.sensorbridge_patch = $patchOutput | ConvertFrom-Json
        } catch {
          $report.sensorbridge_patch = $patchOutput
        }
      }
      Invoke-MSBuildChecked -ProjectPath $softcamProjectToBuild
      if ($useVs2019Projects) {
        $report.synced_vs2019_dist = Sync-SoftcamVs2019Dist
      }
      if (Test-Path $installerProjectToBuild) {
        Invoke-MSBuildChecked -ProjectPath $installerProjectToBuild
      }
      if (Test-Path $senderProjectToBuild) {
        Invoke-MSBuildChecked -ProjectPath $senderProjectToBuild
      }
    } catch {
      $report.ok = $false
      $report.error = [ordered]@{
        code = 'softcam_build_failed'
        message = $_.Exception.Message
      }
      $blocks += $_.Exception.Message
    }
  }
}

$dllExistsAfter = Test-Path $dllPath
$installerExistsAfter = Test-Path $installerExe
$senderExistsAfter = Test-Path $senderExe
$report.output.softcam_dll_exists = $dllExistsAfter
$report.output.installer_exe_exists = $installerExistsAfter
$report.output.sender_exe_exists = $senderExistsAfter
$report.readiness.can_register_after_build = $dllExistsAfter -and $installerExistsAfter
$report.readiness.creates_windows_camera_now = $false
if ($blocks.Count -gt 0) {
  $report.blocks = $blocks
}

$report | ConvertTo-Json -Depth 8
