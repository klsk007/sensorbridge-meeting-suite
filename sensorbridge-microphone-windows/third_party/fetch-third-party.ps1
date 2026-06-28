param(
  [string[]]$Component = @('all'),
  [switch]$List,
  [switch]$Status,
  [switch]$DryRun,
  [switch]$Unlocked,
  [switch]$UpdateExisting
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $root 'third-party-manifest.json'
$lockPath = Join-Path $root 'third-party-lock.json'
$src = Join-Path $root 'src'

if (-not (Test-Path $manifestPath)) {
  throw "Missing third-party manifest: $manifestPath"
}

$manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
$components = @($manifest.components)
$lock = $null
$lockComponents = @{}
if (Test-Path $lockPath) {
  $lock = Get-Content -Raw -Path $lockPath | ConvertFrom-Json
  foreach ($entry in @($lock.components)) {
    $lockComponents[$entry.name.ToLowerInvariant()] = $entry
  }
}

if ($List) {
  $components | ForEach-Object {
    $locked = $lockComponents[$_.name.ToLowerInvariant()]
    [pscustomobject]@{
      name = $_.name
      license = $_.license
      repository = $_.repository
      path = $_.path
      purpose = $_.purpose
      locked_commit = if ($locked) { $locked.commit } else { $null }
    }
  } |
    ConvertTo-Json -Depth 4
  exit 0
}

function Get-ArrayProperty($entry, $name) {
  if ($entry.PSObject.Properties.Name -contains $name) {
    foreach ($item in @($entry.$name)) {
      if ($null -ne $item -and [string]$item -ne '') {
        [string]$item
      }
    }
    return
  }
}

$selectedNames = @(
  $Component |
    ForEach-Object { [string]$_ -split ',' } |
    ForEach-Object { $_.Trim().ToLowerInvariant() } |
    Where-Object { $_ }
)
if ($selectedNames.Count -eq 0) {
  $selectedNames = @('all')
}

$selected = @()
foreach ($entry in $components) {
  if ($selectedNames -contains 'all' -or $selectedNames -contains $entry.name.ToLowerInvariant()) {
    $selected += $entry
  }
}

if ($selected.Count -eq 0) {
  $available = ($components | ForEach-Object { $_.name }) -join ', '
  throw "No matching components requested. Available components: $available"
}

New-Item -ItemType Directory -Force -Path $src | Out-Null

function Get-LockedCommit($entry) {
  if ($Unlocked) {
    return $null
  }
  $locked = $lockComponents[$entry.name.ToLowerInvariant()]
  if ($locked -and $locked.commit) {
    return [string]$locked.commit
  }
  return $null
}

function Set-SparseCheckout($target, $paths) {
  if (@($paths).Count -eq 0) {
    return
  }
  git -C $target sparse-checkout init --cone
  git -C $target sparse-checkout set @paths
}

function Invoke-GitFetchLocked($target, $commit) {
  git -C $target fetch --depth 1 origin $commit
  git -C $target checkout --detach $commit
}

function Get-ComponentStatus($entry) {
  $target = Join-Path $root $entry.path
  $lockedCommit = Get-LockedCommit $entry
  $sourceExists = Test-Path $target
  $gitDir = Join-Path $target '.git'
  $isGitCheckout = Test-Path $gitDir
  $currentCommit = $null
  $isDirty = $false
  $sparseCheckout = $false
  if ($isGitCheckout) {
    $currentCommit = (git -C $target rev-parse HEAD 2>$null | Out-String).Trim()
    $dirtyText = (git -C $target status --porcelain 2>$null | Out-String).Trim()
    $isDirty = [bool]$dirtyText
    $sparseText = (git -C $target config --bool core.sparseCheckout 2>$null | Out-String).Trim()
    $sparseCheckout = $sparseText -eq 'true'
  }

  $subpath = if ($entry.PSObject.Properties.Name -contains 'subpath') { [string]$entry.subpath } else { $null }
  $sparsePaths = @(Get-ArrayProperty $entry 'sparse_paths')
  $submodules = @(Get-ArrayProperty $entry 'submodules')
  $sparsePathStatus = @()
  foreach ($path in $sparsePaths) {
    $sparsePathStatus += [ordered]@{
      path = [string]$path
      exists = Test-Path (Join-Path $target ([string]$path))
    }
  }

  return [ordered]@{
    name = [string]$entry.name
    repository = [string]$entry.repository
    license = [string]$entry.license
    path = [string]$entry.path
    target = $target
    source_exists = $sourceExists
    is_git_checkout = $isGitCheckout
    current_commit = $currentCommit
    locked_commit = $lockedCommit
    locked_commit_match = if ($lockedCommit -and $currentCommit) { $currentCommit -eq $lockedCommit } else { $null }
    dirty = $isDirty
    sparse_paths = @($sparsePaths)
    sparse_checkout = $sparseCheckout
    sparse_path_status = $sparsePathStatus
    submodules = @($submodules)
    submodule_status = @(
      foreach ($submodule in $submodules) {
        $submoduleTarget = Join-Path $target $submodule
        [ordered]@{
          path = [string]$submodule
          exists = Test-Path $submoduleTarget
          initialized = Test-Path (Join-Path $submoduleTarget '.git')
        }
      }
    )
    subpath = $subpath
    subpath_exists = if ($subpath) { Test-Path (Join-Path $target $subpath) } else { $null }
    required_for = @(Get-ArrayProperty $entry 'required_for')
  }
}

function Initialize-Submodules($entry, $target) {
  $submodules = @(Get-ArrayProperty $entry 'submodules')
  if ($submodules.Count -eq 0) {
    return
  }
  foreach ($submodule in $submodules) {
    if ($DryRun) {
      Write-Host "[dry-run] git -C $target submodule update --init $submodule"
    } else {
      git -C $target submodule update --init $submodule
    }
  }
}

if ($Status) {
  $statuses = @()
  foreach ($entry in $selected) {
    $statuses += Get-ComponentStatus $entry
  }
  [ordered]@{
    ok = $true
    source_root = $src
    dry_run = [bool]$DryRun
    components = $statuses
  } | ConvertTo-Json -Depth 8
  exit 0
}

function Clone-IfMissing($entry) {
  $target = Join-Path $root $entry.path
  $lockedCommit = Get-LockedCommit $entry
  $sparsePaths = @(Get-ArrayProperty $entry 'sparse_paths')
  if (Test-Path $target) {
    Write-Host "$($entry.name) already exists at $target"
    if ($lockedCommit -and (Test-Path (Join-Path $target '.git'))) {
      $current = (git -C $target rev-parse HEAD).Trim()
      Write-Host "$($entry.name) current commit: $current"
      Write-Host "$($entry.name) locked commit:  $lockedCommit"
      if ($UpdateExisting -and $current -ne $lockedCommit) {
        $dirty = git -C $target status --porcelain
        if ($dirty) {
          throw "$($entry.name) has local changes. Commit/stash them or remove $target before -UpdateExisting."
        }
        if ($DryRun) {
          Write-Host "[dry-run] git -C $target fetch --depth 1 origin $lockedCommit"
          Write-Host "[dry-run] git -C $target checkout --detach $lockedCommit"
        } else {
          Invoke-GitFetchLocked $target $lockedCommit
        }
      }
    }
    if ($UpdateExisting -and @($sparsePaths).Count -gt 0) {
      if ($DryRun) {
        Write-Host "[dry-run] git -C $target sparse-checkout set $($sparsePaths -join ' ')"
      } else {
        Set-SparseCheckout $target $sparsePaths
      }
    }
    Initialize-Submodules $entry $target
    return
  }

  $message = if (@($sparsePaths).Count -gt 0) {
    $sparse = $sparsePaths -join ' '
    if ($lockedCommit) {
      "git clone --filter=blob:none --no-checkout $($entry.repository) $target; git -C $target sparse-checkout set $sparse; git -C $target fetch --depth 1 origin $lockedCommit; git -C $target checkout --detach $lockedCommit"
    } else {
      "git clone --filter=blob:none --no-checkout $($entry.repository) $target; git -C $target sparse-checkout set $sparse; git -C $target checkout"
    }
  } elseif ($lockedCommit) {
    "git clone --depth 1 $($entry.repository) $target; git -C $target checkout --detach $lockedCommit"
  } else {
    "git clone --depth 1 $($entry.repository) $target"
  }
  if ($DryRun) {
    Write-Host "[dry-run] $message"
    return
  }

  if (@($sparsePaths).Count -gt 0) {
    git clone --filter=blob:none --no-checkout $entry.repository $target
    Set-SparseCheckout $target $sparsePaths
  } else {
    git clone --depth 1 $entry.repository $target
  }
  if ($lockedCommit) {
    Invoke-GitFetchLocked $target $lockedCommit
  } elseif (@($sparsePaths).Count -gt 0) {
    git -C $target checkout
  }
  Initialize-Submodules $entry $target
}

foreach ($entry in $selected) {
  Clone-IfMissing $entry
}

Write-Host 'Optional sources processed. Read third_party/README.md before building or redistributing.'
