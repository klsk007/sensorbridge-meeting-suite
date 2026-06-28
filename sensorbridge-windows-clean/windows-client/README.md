# SensorBridge Windows Client

The active Python package is currently `bridgeclient` at the repository root. This folder is reserved for the installable Windows client layout requested for the next packaging stage.

Development entry points:

- `python sensorbridge.py --host 0.0.0.0 --port 8765`
- `python bridge.py --base-url http://127.0.0.1:8765 capabilities`
- `python tools/system_check.py`

The package will be moved or wrapped here when the GUI shell and installer are promoted from prototype to packaged application.
