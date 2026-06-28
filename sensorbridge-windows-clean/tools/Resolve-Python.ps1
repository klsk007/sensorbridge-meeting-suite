function Resolve-SensorBridgePython {
  $candidates = @('py', 'python', 'python3')
  foreach ($name in $candidates) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $command) {
      continue
    }

    try {
      & $command.Source --version *> $null
      if ($LASTEXITCODE -eq 0) {
        return $command.Source
      }
    } catch {
      continue
    }
  }

  throw 'Python 3.10+ was not found. Install Python or make sure py/python is runnable from PATH.'
}
