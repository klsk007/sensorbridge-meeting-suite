param(
    [int]$Port = 8765,
    [string]$HostName = "0.0.0.0",
    [switch]$OpenDashboard
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'tools\Resolve-Python.ps1')

$python = Resolve-SensorBridgePython
$args = @('sensorbridge.py', '--host', $HostName, '--port', $Port)
if ($OpenDashboard) {
    $args += '--open-dashboard'
}
& $python @args
exit $LASTEXITCODE
