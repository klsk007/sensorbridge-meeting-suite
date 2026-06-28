$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
powershell -ExecutionPolicy Bypass -File .\tools\readiness-report.ps1 -EnsureServer
