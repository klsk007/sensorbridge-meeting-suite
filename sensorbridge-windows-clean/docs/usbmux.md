# USBMux Transport

Current status: experimental `iproxy` transport.

The Python transport layer exposes `UsbMuxTransport`, which talks HTTP through a local USBMux port forward:

1. Run or reuse `iproxy <local-port> 27180`.
2. Forward local `127.0.0.1:<local-port>` to the iPhone/iPad SensorBridge HTTP port `27180`.
3. Reuse the existing `HttpTransport` over the forwarded local port.

CLI examples:

```powershell
python .\bridge.py --transport usbmux --usbmux-local-port 27181 health
python .\bridge.py --usb --local-port 27181 product-status
python .\bridge.py --transport usbmux --usbmux-start-proxy --iproxy-path C:\tools\iproxy.exe health
```

If `--usbmux-start-proxy` is omitted, start `iproxy` yourself first:

```powershell
iproxy 27181 27180
python .\bridge.py --transport usbmux --usbmux-local-port 27181 smoke
```

Windows caveats:

- This does not install Apple Mobile Device Support.
- This does not replace the Windows Apple usbmux service.
- `--usbmux-start-proxy` requires `iproxy.exe` on `PATH` or an explicit `--iproxy-path`.
- The libimobiledevice project notes that usbmuxd is not fully supported on Windows as a daemon replacement, and Windows setups commonly depend on Apple Mobile Device Support.

Failure mode:

- If `iproxy` cannot be found, the CLI returns JSON with `error.code = usbmux_iproxy_not_found`.
- If `iproxy` exits before the tunnel is ready, the CLI returns JSON with `error.code = usbmux_iproxy_exited`.
