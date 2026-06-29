param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'SensorBridgeMeetingSuite'),
  [switch]$InstallPythonDeps,
  [switch]$RegisterCamera,
  [switch]$NoShortcuts,
  [switch]$Progress,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
$VbCableUrl = 'https://vb-audio.com/Cable/'

function Write-InstallerProgress {
  param(
    [int]$Percent,
    [string]$Message
  )

  if ($Progress -and -not $Json) {
    Write-Host ("SENSORBRIDGE_PROGRESS|{0}|{1}" -f $Percent, $Message)
  }
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

function Resolve-FullPath {
  param([string]$Path)
  return [System.IO.Path]::GetFullPath($Path)
}

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-PythonCommand {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    try {
      $exe = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe.Trim())) {
        return @{ File = $py.Source; Prefix = @('-3') }
      }
    } catch {
    }
  }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @{ File = $python.Source; Prefix = @() }
  }

  return $null
}

function New-Shortcut {
  param(
    [string]$Path,
    [string]$TargetPath,
    [string]$Arguments,
    [string]$WorkingDirectory,
    [string]$Description
  )

  $parent = Split-Path -Parent $Path
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($Path)
  $shortcut.TargetPath = $TargetPath
  $shortcut.Arguments = $Arguments
  $shortcut.WorkingDirectory = $WorkingDirectory
  $shortcut.Description = $Description
  $shortcut.IconLocation = $TargetPath
  $shortcut.Save()
}

function Invoke-PythonModuleCheck {
  param($Python)

  if (-not $Python) {
    return @{ ok = $false; error = 'Python 3.10+ was not found on PATH.' }
  }

  $code = "import importlib.util, json; mods=['aiortc','av','numpy','sounddevice']; print(json.dumps({m: importlib.util.find_spec(m) is not None for m in mods}, sort_keys=True))"
  try {
    $result = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + @('-c', $code))
    $output = $result.output
    $exitCode = [int]$result.exitCode
    if ($exitCode -ne 0) {
      return @{ ok = $false; exitCode = $exitCode; output = ($output -join "`n") }
    }
    $modules = ($output -join "`n") | ConvertFrom-Json
    $missing = @()
    foreach ($name in @('aiortc', 'av', 'numpy', 'sounddevice')) {
      if (-not [bool]$modules.$name) {
        $missing += $name
      }
    }
    return @{
      ok = ($missing.Count -eq 0)
      modules = $modules
      missing = $missing
    }
  } catch {
    return @{ ok = $false; error = $_.Exception.Message }
  }
}

function Test-WheelhousePresent {
  param([string]$Root)

  $wheelhouse = Join-Path $Root 'wheelhouse'
  if (-not (Test-Path $wheelhouse)) {
    return $false
  }
  $wheels = @(Get-ChildItem -LiteralPath $wheelhouse -Filter '*.whl' -File -ErrorAction SilentlyContinue)
  return ($wheels.Count -gt 0)
}

function Test-VbCablePresent {
  try {
    $devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object {
      $_.Name -match 'CABLE Input|CABLE Output|VB-Audio|VB-CABLE'
    })
    return @{
      ok = ($devices.Count -gt 0)
      devices = @($devices | Select-Object -First 12 | ForEach-Object { $_.Name })
    }
  } catch {
    return @{ ok = $false; error = $_.Exception.Message; devices = @() }
  }
}

function Invoke-PipInstall {
  param(
    $Python,
    [string]$Root
  )

  if (-not $Python) {
    return @{ ok = $false; error = 'Python 3.10+ was not found on PATH.' }
  }

  $pipCheck = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + @('-m', 'pip', '--version'))
  $pipCheckExit = [int]$pipCheck.exitCode
  $ensurePip = $null
  if ($pipCheckExit -ne 0) {
    $ensure = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + @('-m', 'ensurepip', '--upgrade'))
    $ensurePip = @{
      ok = ([int]$ensure.exitCode -eq 0)
      exitCode = [int]$ensure.exitCode
      output = ($ensure.output -join "`n")
    }
    if ([int]$ensure.exitCode -ne 0) {
      return @{
        ok = $false
        error = 'pip is unavailable and ensurepip could not initialize it.'
        ensurepip = $ensurePip
      }
    }
  }

  $wheelhouse = Join-Path $Root 'wheelhouse'
  $offline = Test-WheelhousePresent -Root $Root
  $findLinksArgs = @()
  if ($offline) {
    $findLinksArgs = @('--no-index', '--find-links', $wheelhouse)
  }

  $bootstrapArgs = @('-m', 'pip', 'install') + $findLinksArgs + @('--upgrade', 'setuptools', 'wheel')
  $bootstrapResult = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + $bootstrapArgs)
  $bootstrapOutput = $bootstrapResult.output
  $bootstrapExit = [int]$bootstrapResult.exitCode
  $bootstrap = @{
    ok = ($bootstrapExit -eq 0)
    exitCode = $bootstrapExit
    output = ($bootstrapOutput -join "`n")
  }
  if ($bootstrapExit -ne 0) {
    return @{
      ok = $false
      offline = $offline
      wheelhouse = if ($offline) { $wheelhouse } else { $null }
      ensurepip = $ensurePip
      bootstrap = $bootstrap
      error = 'Could not install Python build helpers.'
    }
  }

  $cameraSpec = (Join-Path $Root 'sensorbridge-windows-clean') + '[webrtc]'
  $microphoneDir = Join-Path $Root 'sensorbridge-microphone-windows'
  $speakerDir = Join-Path $Root 'sensorbridge-speaker-windows'
  $args = @('-m', 'pip', 'install') + $findLinksArgs
  if ($offline) {
    $args += '--no-build-isolation'
  }
  $args += @('-e', $cameraSpec, '-e', $microphoneDir, '-e', $speakerDir)
  $installResult = Invoke-NativeCapture -File $Python.File -Arguments @($Python.Prefix + $args)
  $output = $installResult.output
  return @{
    ok = ([int]$installResult.exitCode -eq 0)
    exitCode = [int]$installResult.exitCode
    offline = $offline
    wheelhouse = if ($offline) { $wheelhouse } else { $null }
    ensurepip = $ensurePip
    bootstrap = $bootstrap
    output = ($output -join "`n")
  }
}

function Invoke-CameraRegister {
  param([string]$Root)

  $script = Join-Path $Root 'sensorbridge-windows-clean\drivers\camera\directshow\register-dev.ps1'
  if (-not (Test-Path $script)) {
    return @{ ok = $false; error = "Camera registration script missing: $script" }
  }
  if (-not (Test-Admin)) {
    return @{ ok = $false; error = 'Administrator rights are required to register SensorBridge Camera.' }
  }
  $result = Invoke-NativeCapture -File 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script, '-Register')
  return @{
    ok = ([int]$result.exitCode -eq 0)
    exitCode = [int]$result.exitCode
    output = ($result.output -join "`n")
  }
}

$sourceRoot = Resolve-FullPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
$targetRoot = Resolve-FullPath $InstallDir
$sourceTrimmed = $sourceRoot.TrimEnd('\')
$targetTrimmed = $targetRoot.TrimEnd('\')

Write-InstallerProgress -Percent 5 -Message 'Checking install paths'

if ($targetTrimmed.StartsWith($sourceTrimmed + '\', [StringComparison]::OrdinalIgnoreCase)) {
  throw "InstallDir cannot be inside the extracted package folder: $targetRoot"
}

$copiedFiles = $false
if (-not [String]::Equals($sourceTrimmed, $targetTrimmed, [StringComparison]::OrdinalIgnoreCase)) {
  Write-InstallerProgress -Percent 18 -Message 'Copying application files'
  New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
  foreach ($item in Get-ChildItem -LiteralPath $sourceRoot -Force) {
    Copy-Item -LiteralPath $item.FullName -Destination $targetRoot -Recurse -Force
  }
  $copiedFiles = $true
} else {
  Write-InstallerProgress -Percent 18 -Message 'Using current folder as install directory'
}

$appExe = Join-Path $targetRoot 'meeting-suite\windows-app\SensorBridge.Meeting.App\bin\Release\SensorBridge.Meeting.App.exe'
if (-not (Test-Path $appExe)) {
  throw "Desktop app executable was not found after install: $appExe"
}

$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'SensorBridge Meeting Suite.lnk'
$startMenuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'SensorBridge Meeting Suite'
$startShortcut = Join-Path $startMenuDir 'SensorBridge Meeting Suite.lnk'
$shortcutArgs = '--project-root "' + $targetRoot + '"'
if (-not $NoShortcuts) {
  Write-InstallerProgress -Percent 42 -Message 'Creating desktop and Start menu shortcuts'
  New-Shortcut -Path $desktopShortcut -TargetPath $appExe -Arguments $shortcutArgs -WorkingDirectory $targetRoot -Description 'SensorBridge Meeting Suite'
  New-Shortcut -Path $startShortcut -TargetPath $appExe -Arguments $shortcutArgs -WorkingDirectory $targetRoot -Description 'SensorBridge Meeting Suite'
} else {
  Write-InstallerProgress -Percent 42 -Message 'Skipping shortcuts'
}

$python = Resolve-PythonCommand
$pipInstall = $null
if ($InstallPythonDeps) {
  if (Test-WheelhousePresent -Root $targetRoot) {
    Write-InstallerProgress -Percent 58 -Message 'Installing Python bridge dependencies from local wheelhouse'
  } else {
    Write-InstallerProgress -Percent 58 -Message 'Installing Python bridge dependencies from pip index'
  }
  $pipInstall = Invoke-PipInstall -Python $python -Root $targetRoot
} else {
  Write-InstallerProgress -Percent 58 -Message 'Skipping Python dependency install'
}

$cameraRegister = $null
if ($RegisterCamera) {
  Write-InstallerProgress -Percent 74 -Message 'Registering SensorBridge Camera'
  $cameraRegister = Invoke-CameraRegister -Root $targetRoot
} else {
  Write-InstallerProgress -Percent 74 -Message 'Skipping camera registration'
}

Write-InstallerProgress -Percent 86 -Message 'Checking installed environment'
$pythonModules = Invoke-PythonModuleCheck -Python $python
$vbCable = Test-VbCablePresent
$cameraArtifacts = @{
  directshowSender = Test-Path (Join-Path $targetRoot 'sensorbridge-windows-clean\windows-app\SensorBridge.DirectShowSender\x64\Release\SensorBridge.DirectShowSender.exe')
  softcamDll = Test-Path (Join-Path $targetRoot 'sensorbridge-windows-clean\third_party\src\softcam\dist\bin\x64\softcam.dll')
}

$report = [ordered]@{
  ok = $true
  command = 'install_sensorbridge_meeting_suite'
  installDir = $targetRoot
  source = $sourceRoot
  copiedFiles = $copiedFiles
  shortcuts = [ordered]@{
    created = -not [bool]$NoShortcuts
    desktop = $desktopShortcut
    startMenu = $startShortcut
  }
  checks = [ordered]@{
    python = [ordered]@{
      found = [bool]$python
      command = if ($python) { $python.File } else { $null }
      modules = $pythonModules
    }
    wheelhouse = [ordered]@{
      present = (Test-WheelhousePresent -Root $targetRoot)
      path = (Join-Path $targetRoot 'wheelhouse')
    }
    vbCable = $vbCable
    cameraArtifacts = $cameraArtifacts
  }
  actions = [ordered]@{
    pipInstall = $pipInstall
    cameraRegister = $cameraRegister
  }
  externalDependencies = [ordered]@{
    vbCableUrl = $VbCableUrl
  }
  nextSteps = @()
}

if (-not $python) {
  $report.ok = $false
  $report.nextSteps += 'Install Python 3.10+ and run this installer again with -InstallPythonDeps.'
} elseif (-not [bool]$pythonModules.ok) {
  $report.ok = $false
  $report.nextSteps += 'Run Install-SensorBridgeMeeting.ps1 -InstallPythonDeps to install Python bridge dependencies. If the package contains wheelhouse, this step runs offline.'
}

if (-not [bool]$vbCable.ok) {
  $report.ok = $false
  $report.nextSteps += "VB-CABLE was not detected. Download, install, or uninstall it from: $VbCableUrl"
  $report.nextSteps += 'After VB-CABLE is installed, use the meeting roles: Microphone = Cable Microphone (may show as CABLE Output), Speaker = Cable Speaker (may show as CABLE Input). If the Windows names differ, use Refresh audio devices in the main app and choose the matching channels manually.'
}

if (-not ([bool]$cameraArtifacts.directshowSender -and [bool]$cameraArtifacts.softcamDll)) {
  $report.ok = $false
  $report.nextSteps += 'Camera artifacts are missing from the package; rebuild the package on the development machine.'
}

if ($RegisterCamera -and $cameraRegister -and -not [bool]$cameraRegister.ok) {
  $report.ok = $false
  $report.nextSteps += 'Run the installer from an elevated PowerShell window with -RegisterCamera to register SensorBridge Camera.'
}

if ($Json) {
  $report | ConvertTo-Json -Depth 8
} else {
  Write-InstallerProgress -Percent 100 -Message 'Install finished'
  Write-Host "Installed SensorBridge Meeting Suite:"
  Write-Host "  $targetRoot"
  if ($NoShortcuts) {
    Write-Host "Shortcuts skipped."
  } else {
    Write-Host "Desktop shortcut:"
    Write-Host "  $desktopShortcut"
    Write-Host "Start menu shortcut:"
    Write-Host "  $startShortcut"
  }
  if ($report.nextSteps.Count -gt 0) {
    Write-Host ""
    Write-Host "Next steps:"
    foreach ($step in $report.nextSteps) {
      Write-Host "  - $step"
    }
  }
  if (-not [bool]$vbCable.ok) {
    Write-Host ""
    Write-Host "VB-CABLE official page:"
    Write-Host "  $VbCableUrl"
    if ($Progress) {
      Write-Host ("SENSORBRIDGE_VBCABLE_MISSING|{0}" -f $VbCableUrl)
    }
  }
}
