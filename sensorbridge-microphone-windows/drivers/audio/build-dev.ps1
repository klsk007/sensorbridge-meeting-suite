param(
  [switch]$Fetch,
  [switch]$Build,
  [switch]$ApplySensorBridgePatch,
  [string]$Configuration = 'Debug',
  [string]$Platform = 'x64'
)

$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $audioRoot)
$sourceDir = Join-Path $root 'third_party\src\Windows-driver-samples\audio\sysvad'

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

function Test-WDK {
  $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
  return (Test-Path (Join-Path $kits 'Include')) -and (Test-Path (Join-Path $kits 'Lib'))
}

function Get-VSRoots {
  $roots = @()
  foreach ($year in @('2022', '2019')) {
    $base = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\$year"
    foreach ($edition in @('BuildTools', 'Community', 'Professional', 'Enterprise')) {
      $candidate = Join-Path $base $edition
      if (Test-Path $candidate) {
        $roots += $candidate
      }
    }
  }
  return $roots
}

function Get-DriverBuildPrerequisites {
  $vsRoots = @(Get-VSRoots)
  $driverToolset = $null
  $atlHeader = $null
  $spectreLib = $null
  foreach ($vsRoot in $vsRoots) {
    $toolsets = Join-Path $vsRoot 'MSBuild\Microsoft\VC\v170\Platforms\x64\PlatformToolsets'
    $kernelToolset = Join-Path $toolsets 'WindowsKernelModeDriver10.0'
    $appToolset = Join-Path $toolsets 'WindowsApplicationForDrivers10.0'
    if ((-not $driverToolset) -and (Test-Path $kernelToolset) -and (Test-Path $appToolset)) {
      $driverToolset = [ordered]@{
        kernel = $kernelToolset
        application = $appToolset
      }
    }

    $msvcRoot = Join-Path $vsRoot 'VC\Tools\MSVC'
    if (Test-Path $msvcRoot) {
      foreach ($versionDir in @(Get-ChildItem -Path $msvcRoot -Directory -ErrorAction SilentlyContinue)) {
        $atlCandidate = Join-Path $versionDir.FullName 'atlmfc\include\atlbase.h'
        if ((-not $atlHeader) -and (Test-Path $atlCandidate)) {
          $atlHeader = $atlCandidate
        }
        $spectreCandidate = Join-Path $versionDir.FullName 'lib\spectre\x64\vcruntime.lib'
        if ((-not $spectreLib) -and (Test-Path $spectreCandidate)) {
          $spectreLib = $spectreCandidate
        }
      }
    }
  }

  $sourceRoot = Split-Path -Parent (Split-Path -Parent $sourceDir)
  $wilHeader = Join-Path $sourceRoot 'wil\include\wil\com.h'
  $packageDir = Join-Path $sourceDir "$Platform\$Configuration\package"
  $requiredPackageFiles = @(
    'TabletAudioSample.sys',
    'ComponentizedAudioSample.inf',
    'ComponentizedAudioSampleExtension.inf',
    'ComponentizedApoSample.inf',
    'sysvad.cat'
  )
  $missingPackageFiles = @()
  foreach ($name in $requiredPackageFiles) {
    if (-not (Test-Path (Join-Path $packageDir $name))) {
      $missingPackageFiles += $name
    }
  }

  return [ordered]@{
    visual_studio_roots = $vsRoots
    driver_toolset_available = [bool]$driverToolset
    driver_toolset_paths = $driverToolset
    atl_available = [bool]$atlHeader
    atl_header = $atlHeader
    spectre_libs_available = [bool]$spectreLib
    spectre_lib = $spectreLib
    wil_available = Test-Path $wilHeader
    wil_header = $wilHeader
    package_dir = $packageDir
    package_built = ((Test-Path $packageDir) -and ($missingPackageFiles.Count -eq 0))
    missing_package_files = $missingPackageFiles
    certificate = Join-Path (Join-Path $sourceDir "$Platform\$Configuration") 'package.cer'
  }
}

function Get-LatestWindowsKitVersion {
  $libRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Lib'
  if (-not (Test-Path $libRoot)) {
    return $null
  }
  $versions = @(Get-ChildItem -Path $libRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
  foreach ($version in $versions) {
    if (Test-Path (Join-Path $version.FullName 'um\x64\onecoreuap.lib')) {
      return $version.Name
    }
  }
  return $null
}

if ($Fetch) {
  & (Join-Path $root 'third_party\fetch-third-party.ps1') -Component Windows-driver-samples
}

$sensorBridgePatchReport = $null
if ($ApplySensorBridgePatch) {
  $patchOutput = & (Join-Path $audioRoot 'apply-sensorbridge-patch.ps1') -SourceDir $sourceDir
  $sensorBridgePatchReport = $patchOutput | ConvertFrom-Json
}

$msbuild = Find-MSBuild
$wdkAvailable = Test-WDK
$prerequisites = Get-DriverBuildPrerequisites
$sourceExists = Test-Path $sourceDir
$project = $null
if ($sourceExists) {
  $preferredSolution = Join-Path $sourceDir 'sysvad.sln'
  if (Test-Path $preferredSolution) {
    $project = Get-Item $preferredSolution
  } else {
    $project = Get-ChildItem -Path $sourceDir -Recurse -Include *.sln,*.vcxproj -File |
      Sort-Object @{ Expression = { if ($_.Extension -eq '.sln') { 0 } else { 1 } } }, FullName |
      Select-Object -First 1
  }
}

$report = [ordered]@{
  ok = $true
  component = 'Windows-driver-samples/audio/sysvad'
  purpose = 'SensorBridge virtual microphone development build check'
  source_dir = $sourceDir
  source_exists = $sourceExists
  msbuild = $msbuild
  wdk_available = $wdkAvailable
  build_prerequisites = $prerequisites
  project = if ($project) { $project.FullName } else { $null }
  build_requested = [bool]$Build
  build_attempted = $false
  sensorbridge_patch_requested = [bool]$ApplySensorBridgePatch
  sensorbridge_patch = $sensorBridgePatchReport
  installs_driver_or_microphone = $false
  requires_admin_for_install = $true
  requires_test_signing_for_development = $true
  requires_driver_signing_for_release = $true
  notes = @(
    'This script fetches/checks/builds the SysVAD development source only.',
    'It does not install an INF, enable test signing, reboot, or create a SensorBridge microphone endpoint.',
    'Use -ApplySensorBridgePatch before -Build to generate a SensorBridge-named development virtual microphone package.'
  )
}

if ($Build) {
  if (-not $sourceExists) {
    throw "Missing Windows-driver-samples SysVAD source. Run with -Fetch first."
  }
  if (-not $msbuild) {
    throw 'MSBuild was not found. Install Visual Studio with the C++ workload.'
  }
  if (-not $wdkAvailable) {
    throw 'Windows Driver Kit was not found under Program Files (x86)\Windows Kits\10.'
  }
  if (-not $prerequisites.driver_toolset_available) {
    throw 'Visual Studio DriverKit build tools were not found. Install Component.Microsoft.Windows.DriverKit.BuildTools.'
  }
  if (-not $prerequisites.atl_available) {
    throw 'ATL headers were not found. Install the Visual C++ ATL component for the active MSVC toolset.'
  }
  if (-not $prerequisites.spectre_libs_available) {
    throw 'Spectre-mitigated x64 MSVC libraries were not found.'
  }
  if (-not $prerequisites.wil_available) {
    throw 'WIL was not found. Run third_party\fetch-third-party.ps1 -Component Windows-driver-samples to initialize the wil submodule.'
  }
  if (-not $project) {
    throw "No .sln or .vcxproj file found under $sourceDir"
  }

  $report.build_attempted = $true
  $msvcRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $prerequisites.atl_header))
  $atlLib = Join-Path $msvcRoot "atlmfc\lib\$Platform"
  $vcLib = Join-Path $msvcRoot "lib\$Platform"
  $vcOneCoreLib = Join-Path $msvcRoot "lib\onecore\$Platform"
  $vcSpectreOneCoreLib = Join-Path $msvcRoot "lib\spectre\onecore\$Platform"
  $kitVersion = Get-LatestWindowsKitVersion
  $kitUmLib = if ($kitVersion) { Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\Lib\$kitVersion\um\$Platform" } else { $null }
  $previousLib = $env:LIB
  $libraryPaths = @($atlLib, $vcSpectreOneCoreLib, $vcOneCoreLib, $vcLib, $kitUmLib) | Where-Object { $_ -and (Test-Path $_) }
  if ($libraryPaths.Count -gt 0) {
    $prefix = $libraryPaths -join ';'
    $env:LIB = if ($previousLib) { "$prefix;$previousLib" } else { $prefix }
  }
  if (Test-Path $atlLib) {
    $propsPath = Join-Path $sourceDir 'Directory.Build.props'
    $escapedAtlLib = [System.Security.SecurityElement]::Escape($atlLib)
    $props = @"
<Project>
  <ItemDefinitionGroup Condition="'`$(Platform)'=='$Platform'">
    <Link>
      <AdditionalLibraryDirectories>$escapedAtlLib;%(AdditionalLibraryDirectories)</AdditionalLibraryDirectories>
    </Link>
  </ItemDefinitionGroup>
</Project>
"@
    Set-Content -Path $propsPath -Value $props -Encoding Ascii
  }
  $msbuildArgs = @($project.FullName, '/m', "/p:Configuration=$Configuration", "/p:Platform=$Platform")
  & $msbuild @msbuildArgs
  $buildExitCode = $LASTEXITCODE
  $env:LIB = $previousLib
  if ($buildExitCode -ne 0) {
    exit $buildExitCode
  }
  $prerequisites = Get-DriverBuildPrerequisites
  $report.build_prerequisites = $prerequisites
}

$report | ConvertTo-Json -Depth 5
