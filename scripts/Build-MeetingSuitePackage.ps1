param(
  [string]$Configuration = 'Release',
  [string]$OutputDir = '',
  [string[]]$WheelPythonVersions = @('310', '311', '312'),
  [string]$WheelhouseCacheDir = '',
  [string]$PipIndexUrl = '',
  [switch]$SkipWheelhouse,
  [switch]$NoZip,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
if (-not $OutputDir) {
  $OutputDir = Join-Path $root 'dist'
}
if (-not $WheelhouseCacheDir) {
  $WheelhouseCacheDir = Join-Path $OutputDir 'wheelhouse-cache'
}
$WheelPythonVersions = @(
  $WheelPythonVersions | ForEach-Object {
    ($_ -split '[,; ]+') | Where-Object { $_ }
  }
)

function Get-RelativePathCompat {
  param(
    [string]$BasePath,
    [string]$Path
  )

  $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
  $pathFull = [System.IO.Path]::GetFullPath($Path)
  $baseUri = New-Object System.Uri($baseFull)
  $pathUri = New-Object System.Uri($pathFull)
  return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

$skipDirectoryNames = @(
  '.git',
  '.github',
  '.pytest_cache',
  '.mypy_cache',
  '__pycache__',
  '.venv',
  '.git-nested-backups',
  'captures',
  'downloads',
  'logs',
  'obj',
  'Debug',
  'third_party',
  'tests'
)

$skipFilePatterns = @(
  '*.pyc',
  '*.pyo',
  '*.log',
  '*.tmp',
  '*.jsonl',
  '*.wav',
  '*.pcm',
  '*.zip',
  '*.suo',
  '*.user',
  '*.ipdb',
  '*.iobj',
  '*.obj',
  '*.pdb',
  '*.tlog',
  '*.lastbuildstate',
  '*.recipe',
  'unsuccessfulbuild',
  'sensorbridge-ipad-preview.png',
  'wemeet-*.png'
)

function Test-SkipRelativePath {
  param(
    [string]$RelativePath,
    [bool]$IsDirectory
  )

  $parts = @($RelativePath -split '[\\/]' | Where-Object { $_ })
  foreach ($part in $parts) {
    if ($skipDirectoryNames -contains $part) {
      return $true
    }
  }

  if (-not $IsDirectory) {
    $leaf = Split-Path -Leaf $RelativePath
    foreach ($pattern in $skipFilePatterns) {
      if ($leaf -like $pattern) {
        return $true
      }
    }
  }

  return $false
}

function Copy-TreeFiltered {
  param(
    [string]$Source,
    [string]$Destination
  )

  $sourceFull = (Resolve-Path -LiteralPath $Source).ProviderPath
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  foreach ($item in Get-ChildItem -LiteralPath $sourceFull -Recurse -Force) {
    $relative = Get-RelativePathCompat -BasePath $sourceFull -Path $item.FullName
    $skip = Test-SkipRelativePath -RelativePath $relative -IsDirectory $item.PSIsContainer
    if ($skip) {
      continue
    }

    $target = Join-Path $Destination $relative
    if ($item.PSIsContainer) {
      New-Item -ItemType Directory -Force -Path $target | Out-Null
    } else {
      $parent = Split-Path -Parent $target
      New-Item -ItemType Directory -Force -Path $parent | Out-Null
      Copy-Item -LiteralPath $item.FullName -Destination $target -Force
    }
  }
}

function Copy-RootFile {
  param(
    [string]$Name,
    [string]$DestinationRoot
  )

  $source = Join-Path $root $Name
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $DestinationRoot $Name) -Force
  }
}

function Resolve-PythonCommand {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return @{ File = $py.Source; Prefix = @('-3') }
  }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @{ File = $python.Source; Prefix = @() }
  }

  return $null
}

function Invoke-NativeCapture {
  param(
    [string]$File,
    [string[]]$Arguments
  )

  $oldErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $output = & $File @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $oldErrorActionPreference
  }

  return @{
    exitCode = $exitCode
    output = ($output | ForEach-Object { "$_" })
  }
}

function Invoke-PipDownload {
  param(
    [hashtable]$Python,
    [string]$RequirementsPath,
    [string]$Wheelhouse,
    [string[]]$PythonVersions,
    [string]$CacheDir,
    [string]$IndexUrl
  )

  if (-not $Python) {
    throw 'Python was not found. Build without offline wheels by passing -SkipWheelhouse, or install Python 3.10+ on the build machine.'
  }
  if (-not (Test-Path $RequirementsPath)) {
    throw "Runtime requirements file was not found: $RequirementsPath"
  }

  New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null
  if ($CacheDir -and (Test-Path $CacheDir)) {
    Copy-Item -Path (Join-Path $CacheDir '*') -Destination $Wheelhouse -Force -ErrorAction SilentlyContinue
  }
  Copy-Item -LiteralPath $RequirementsPath -Destination (Join-Path $Wheelhouse 'runtime-requirements.txt') -Force

  $downloads = @()
  foreach ($version in $PythonVersions) {
    $normalized = ($version -replace '[^\d]', '')
    if ($normalized.Length -lt 2) {
      throw "Invalid Python wheel target version: $version"
    }
    $abi = "cp$normalized"
    $args = @(
      '-m', 'pip', 'download',
      '--only-binary=:all:',
      '--dest', $Wheelhouse,
      '--platform', 'win_amd64',
      '--implementation', 'cp',
      '--python-version', $normalized,
      '--abi', $abi,
      '--timeout', '600',
      '--retries', '10',
      '--progress-bar', 'off',
      '-r', $RequirementsPath
    )
    if ($IndexUrl) {
      $args += @('--index-url', $IndexUrl)
    }
    $result = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + $args)
    $output = $result.output
    $exitCode = [int]$result.exitCode
    $downloads += [ordered]@{
      pythonVersion = $normalized
      abi = $abi
      exitCode = $exitCode
      output = ($output | Out-String).Trim()
    }
    if ($exitCode -ne 0) {
      throw "pip download failed for Python $normalized / $abi.`n$($output | Out-String)"
    }
  }

  $wheels = @(Get-ChildItem -LiteralPath $Wheelhouse -Filter '*.whl' -File -Force)
  if ($wheels.Count -eq 0) {
    throw "No wheels were downloaded into $Wheelhouse"
  }

  if ($CacheDir) {
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    Copy-Item -Path (Join-Path $Wheelhouse '*') -Destination $CacheDir -Force -ErrorAction SilentlyContinue
  }

  $bytes = 0
  foreach ($wheel in $wheels) {
    $bytes += [int64]$wheel.Length
  }

  return [ordered]@{
    ok = $true
    wheelhouse = $Wheelhouse
    requirements = (Join-Path $Wheelhouse 'runtime-requirements.txt')
    targetPythonVersions = $PythonVersions
    cacheDir = $CacheDir
    indexUrl = $IndexUrl
    wheelCount = $wheels.Count
    bytes = $bytes
    downloads = $downloads
  }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$buildScript = Join-Path $root 'meeting-suite\windows-app\SensorBridge.Meeting.App\build.ps1'
$buildOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript -Configuration $Configuration -Json
$buildReport = $buildOutput | ConvertFrom-Json
if (-not [bool]$buildReport.ok) {
  throw "Desktop app build failed: $buildOutput"
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$packageName = "SensorBridgeMeetingSuite-$stamp"
$stage = Join-Path $OutputDir $packageName
if (Test-Path $stage) {
  throw "Package staging directory already exists: $stage"
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-RootFile -Name 'README.md' -DestinationRoot $stage

foreach ($dir in @(
  'meeting-suite',
  'docs',
  'sensorbridge-windows-clean',
  'sensorbridge-microphone-windows',
  'sensorbridge-speaker-windows'
)) {
  Copy-TreeFiltered -Source (Join-Path $root $dir) -Destination (Join-Path $stage $dir)
}

$softcamSource = Join-Path $root 'sensorbridge-windows-clean\third_party\src\softcam'
$softcamDest = Join-Path $stage 'sensorbridge-windows-clean\third_party\src\softcam'
Copy-TreeFiltered -Source (Join-Path $softcamSource 'dist') -Destination (Join-Path $softcamDest 'dist')
foreach ($softcamFile in @('LICENSE', 'README.md')) {
  $source = Join-Path $softcamSource $softcamFile
  if (Test-Path $source) {
    New-Item -ItemType Directory -Force -Path $softcamDest | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $softcamDest $softcamFile) -Force
  }
}

$packagingDir = Join-Path $root 'packaging'
Copy-Item -LiteralPath (Join-Path $packagingDir 'Install-SensorBridgeMeeting.ps1') -Destination (Join-Path $stage 'Install-SensorBridgeMeeting.ps1') -Force
Copy-Item -LiteralPath (Join-Path $packagingDir 'Uninstall-SensorBridgeMeeting.ps1') -Destination (Join-Path $stage 'Uninstall-SensorBridgeMeeting.ps1') -Force
Copy-Item -LiteralPath (Join-Path $packagingDir 'README-PACKAGE.md') -Destination (Join-Path $stage 'README-PACKAGE.md') -Force

$wheelhouseReport = $null
if (-not $SkipWheelhouse) {
  $requirementsPath = Join-Path $packagingDir 'python-runtime-requirements.txt'
  $wheelhouseReport = Invoke-PipDownload `
    -Python (Resolve-PythonCommand) `
    -RequirementsPath $requirementsPath `
    -Wheelhouse (Join-Path $stage 'wheelhouse') `
    -PythonVersions $WheelPythonVersions `
    -CacheDir $WheelhouseCacheDir `
    -IndexUrl $PipIndexUrl
}

$requiredPaths = @(
  'meeting-suite\windows-app\SensorBridge.Meeting.App\bin\Release\SensorBridge.Meeting.App.exe',
  'meeting-suite\Start-SensorBridgeMeeting.ps1',
  'meeting-suite\Stop-SensorBridgeMeeting.ps1',
  'meeting-suite\Test-SensorBridgeMeeting.ps1',
  'meeting-suite\meeting_audio_bridge.py',
  'sensorbridge-windows-clean\sensorbridge.py',
  'sensorbridge-windows-clean\windows-app\SensorBridge.DirectShowSender\x64\Release\SensorBridge.DirectShowSender.exe',
  'sensorbridge-windows-clean\third_party\src\softcam\dist\bin\x64\softcam.dll',
  'sensorbridge-microphone-windows\bridge.py',
  'sensorbridge-speaker-windows\speaker_bridge.py',
  'Install-SensorBridgeMeeting.ps1',
  'Uninstall-SensorBridgeMeeting.ps1'
)
if (-not $SkipWheelhouse) {
  $requiredPaths += 'wheelhouse\runtime-requirements.txt'
}

$missing = @()
foreach ($relative in $requiredPaths) {
  $candidate = Join-Path $stage $relative
  if (-not (Test-Path $candidate)) {
    $missing += $relative
  }
}
if ($missing.Count -gt 0) {
  throw "Package is missing required files: $($missing -join ', ')"
}

$zipPath = $null
if (-not $NoZip) {
  $zipPath = Join-Path $OutputDir "$packageName.zip"
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -Force
}

$files = @(Get-ChildItem -LiteralPath $stage -Recurse -File -Force)
$bytes = 0
foreach ($file in $files) {
  $bytes += [int64]$file.Length
}

$report = [ordered]@{
  ok = $true
  command = 'build_sensorbridge_meeting_suite_package'
  root = $root
  configuration = $Configuration
  stage = $stage
  zip = $zipPath
  fileCount = $files.Count
  bytes = $bytes
  offlineWheelhouse = $wheelhouseReport
  requiredFilesChecked = $requiredPaths
  build = $buildReport
  installCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-SensorBridgeMeeting.ps1"
}

if ($Json) {
  $report | ConvertTo-Json -Depth 8
} else {
  Write-Host "SensorBridge Meeting Suite package built:"
  Write-Host "  Stage: $stage"
  if ($zipPath) {
    Write-Host "  Zip:   $zipPath"
  }
  Write-Host "  Files: $($files.Count)"
}
