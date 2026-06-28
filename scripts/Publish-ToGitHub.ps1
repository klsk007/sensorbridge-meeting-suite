param(
  [string]$Repository = "sensorbridge-meeting-suite",
  [string]$Owner = "",
  [string]$RemoteUrl = "",
  [switch]$Private,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Invoke-Step {
  param(
    [string]$Description,
    [scriptblock]$Action
  )
  Write-Host "==> $Description"
  if (-not $DryRun) {
    & $Action
  }
}

function Test-CommandAvailable {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Push-Location $Root
try {
  $branch = (& git branch --show-current).Trim()
  if (-not $branch) {
    throw 'No current Git branch was found.'
  }
  if ($branch -ne 'main') {
    Invoke-Step "Rename current branch to main" { git branch -M main }
    $branch = 'main'
  }

  $dirty = (& git status --porcelain)
  $trackedDirty = $dirty | Where-Object { $_ -notmatch '^\?\? (sensorbridge-ipad-preview|wemeet-.*)\.png$' }
  if ($trackedDirty) {
    throw "Tracked project files are not clean. Commit or stash them before publishing.`n$($trackedDirty -join [Environment]::NewLine)"
  }

  if ($RemoteUrl) {
    if ((git remote) -contains 'origin') {
      Invoke-Step "Set origin to $RemoteUrl" { git remote set-url origin $RemoteUrl }
    } else {
      Invoke-Step "Add origin $RemoteUrl" { git remote add origin $RemoteUrl }
    }
    Invoke-Step "Push main to origin" { git push -u origin main }
    return
  }

  if (-not (Test-CommandAvailable 'gh')) {
    throw 'GitHub CLI (gh) is not installed. Install gh, authenticate with gh auth login, or pass -RemoteUrl https://github.com/<owner>/<repo>.git.'
  }

  $authStatus = & gh auth status 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is installed but not authenticated. Run gh auth login first.`n$authStatus"
  }

  $visibility = if ($Private) { '--private' } else { '--public' }
  $fullName = if ($Owner) { "$Owner/$Repository" } else { $Repository }
  Invoke-Step "Create GitHub repository $fullName" {
    gh repo create $fullName $visibility --source . --remote origin --push
  }
} finally {
  Pop-Location
}
