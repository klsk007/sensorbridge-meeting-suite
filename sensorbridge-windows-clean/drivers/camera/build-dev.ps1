param(
  [switch]$Fetch,
  [switch]$Build,
  [switch]$ApplyFrameFilePatch,
  [switch]$ApplySensorBridgePatch,
  [switch]$NoRestore,
  [string]$Configuration = 'Debug',
  [string]$Platform = 'x64',
  [string]$Toolset = ''
)

$ErrorActionPreference = 'Stop'
$cameraRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $cameraRoot)
$sourceDir = Join-Path $root 'third_party\src\VCamSample'

function Find-MSBuild {
  $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
  if (Test-Path $vswhere) {
    $found = & $vswhere -latest -products * -requiresAny -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\amd64\MSBuild.exe' | Select-Object -First 1
    if (-not $found) {
      $found = & $vswhere -latest -products * -find 'MSBuild\**\Bin\amd64\MSBuild.exe' | Select-Object -First 1
    }
    if (-not $found) {
      $found = & $vswhere -latest -products * -find 'MSBuild\**\Bin\MSBuild.exe' | Select-Object -First 1
    }
    if ($found) {
      return $found
    }
  }

  $commonRoots = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\amd64\MSBuild.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\amd64\MSBuild.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\MSBuild.exe')
  )
  foreach ($candidate in $commonRoots) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  $cmd = Get-Command msbuild.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  return $null
}

function Find-NuGet {
  $cmd = Get-Command nuget.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $wingetLink = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\nuget.exe'
  if (Test-Path $wingetLink) {
    return $wingetLink
  }

  $common = @(
    (Join-Path ${env:ProgramFiles(x86)} 'NuGet\nuget.exe'),
    (Join-Path $env:ProgramFiles 'NuGet\nuget.exe')
  )
  foreach ($candidate in $common) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  return $null
}

function Test-PlatformToolset {
  param([string]$Name)
  if (-not $Name) {
    return $false
  }

  $roots = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\BuildTools\MSBuild\Microsoft\VC\v170\Platforms\$Platform\PlatformToolsets\$Name"),
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2019\BuildTools\MSBuild\Microsoft\VC\v160\Platforms\$Platform\PlatformToolsets\$Name")
  )
  foreach ($rootPath in $roots) {
    if (Test-Path $rootPath) {
      return $true
    }
  }

  return $false
}

function Get-EffectiveToolset {
  if ($Toolset) {
    return $Toolset
  }
  if (Test-PlatformToolset 'v145') {
    return ''
  }
  if (Test-PlatformToolset 'v143') {
    return 'v143'
  }
  return ''
}

if ($Fetch) {
  & (Join-Path $root 'third_party\fetch-third-party.ps1') -Component VCamSample
}

$frameFilePatchReport = $null
if ($ApplySensorBridgePatch) {
  $patchOutput = & (Join-Path $cameraRoot 'apply-sensorbridge-patch.ps1') -SourceDir $sourceDir
  $frameFilePatchReport = $patchOutput | ConvertFrom-Json
} elseif ($ApplyFrameFilePatch) {
  $patchOutput = & (Join-Path $cameraRoot 'apply-frame-file-patch.ps1') -SourceDir $sourceDir
  $frameFilePatchReport = $patchOutput | ConvertFrom-Json
}

$msbuild = Find-MSBuild
$nuget = Find-NuGet
$effectiveToolset = Get-EffectiveToolset
$sourceExists = Test-Path $sourceDir
$project = $null
if ($sourceExists) {
  $project = Get-ChildItem -Path $sourceDir -Recurse -Include *.sln,*.vcxproj -File |
    Sort-Object FullName |
    Select-Object -First 1
}

$report = [ordered]@{
  ok = $true
  component = 'VCamSample'
  purpose = 'SensorBridge virtual camera development build check'
  source_dir = $sourceDir
  source_exists = $sourceExists
  msbuild = $msbuild
  nuget = $nuget
  project = if ($project) { $project.FullName } else { $null }
  configuration = $Configuration
  platform = $Platform
  requested_toolset = $Toolset
  effective_toolset = $effectiveToolset
  build_requested = [bool]$Build
  build_attempted = $false
  frame_file_patch_requested = [bool]$ApplyFrameFilePatch
  sensorbridge_patch_requested = [bool]$ApplySensorBridgePatch
  frame_file_patch = $frameFilePatchReport
  restore_attempted = $false
  restore_skipped = [bool]$NoRestore
  outputs = @()
  installs_driver_or_camera = $false
  requires_admin_for_registration = $true
  notes = @(
    'This script fetches/checks/builds the upstream camera sample only.',
    'It does not register a Media Foundation virtual camera device.',
    'Use -ApplySensorBridgePatch before -Build to name the development camera SensorBridge Camera and read ProgramData\SensorBridge\camera\latest.bmp.',
    'Use -ApplyFrameFilePatch for the legacy frame-file-only patch.'
  )
}

if ($Build) {
  if (-not $sourceExists) {
    throw "Missing VCamSample source. Run with -Fetch first."
  }
  if (-not $msbuild) {
    throw 'MSBuild was not found. Install Visual Studio with the C++ workload.'
  }
  if (-not $project) {
    throw "No .sln or .vcxproj file found under $sourceDir"
  }

  $packagesConfig = Get-ChildItem -Path $sourceDir -Recurse -Filter packages.config -File -ErrorAction SilentlyContinue | Select-Object -First 1
  $packagesDir = Join-Path $sourceDir 'packages'
  if ($packagesConfig -and -not $NoRestore) {
    if (-not $nuget) {
      throw 'nuget.exe was not found. Install NuGet CLI or run with -NoRestore after restoring packages.'
    }
    $report.restore_attempted = $true
    & $nuget restore (Join-Path $sourceDir 'VCamSample.sln') -PackagesDirectory $packagesDir
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
  }

  $report.build_attempted = $true
  $msbuildArgs = @($project.FullName, '/m', "/p:Configuration=$Configuration", "/p:Platform=$Platform")
  if ($effectiveToolset) {
    $msbuildArgs += "/p:PlatformToolset=$effectiveToolset"
  }
  & $msbuild @msbuildArgs
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  $outputDir = Join-Path $sourceDir "$Platform\$Configuration"
  if (Test-Path $outputDir) {
    $report.outputs = @(Get-ChildItem -Path $outputDir -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Extension -in @('.exe', '.dll', '.pdb') } |
      Sort-Object Name |
      ForEach-Object { $_.FullName })
  }
}

$report | ConvertTo-Json -Depth 5
