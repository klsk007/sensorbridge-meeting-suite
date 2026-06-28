param(
  [string]$BaseUrl = 'http://192.168.0.24:27180',
  [int]$Frames = 5
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  & $py.Source -3 (Join-Path $root 'bridge.py') --base-url $BaseUrl --frames $Frames microphone-product-status
  exit $LASTEXITCODE
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
  & $python.Source (Join-Path $root 'bridge.py') --base-url $BaseUrl --frames $Frames microphone-product-status
  exit $LASTEXITCODE
}
throw 'No usable Python launcher was found on PATH.'
