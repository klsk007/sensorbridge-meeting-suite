$python = Get-Command py -ErrorAction SilentlyContinue
$powershell = Get-Command powershell -ErrorAction SilentlyContinue
$msbuild = Get-Command msbuild -ErrorAction SilentlyContinue

[ordered]@{
  ok = [bool]$python -and [bool]$powershell
  command = 'check_build_prereqs'
  product = 'camera_only'
  python_launcher = if ($python) { $python.Source } else { $null }
  powershell = if ($powershell) { $powershell.Source } else { $null }
  msbuild = if ($msbuild) { $msbuild.Source } else { $null }
  can_build_windows_app = [bool]$powershell
  can_build_directshow_sender = [bool]$msbuild
  notes = @('Camera-only prerequisite check.')
} | ConvertTo-Json -Depth 4
