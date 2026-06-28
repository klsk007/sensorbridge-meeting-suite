from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bridgeclient.errors import BridgeClientError


class Transport(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        ...


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if value.startswith("http//"):
        value = "http://" + value[len("http//") :]
    elif value.startswith("https//"):
        value = "https://" + value[len("https//") :]
    elif "://" not in value:
        value = "http://" + value

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BridgeClientError(
            "base-url must look like http://host:port",
            code="invalid_base_url",
            detail={"base_url": base_url},
        )
    return value.rstrip("/")


class HttpTransport:
    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout

    def request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(dict(body)).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                response_bytes = response.read()
        except HTTPError as exc:
            raise self._http_error(exc, url) from exc
        except URLError as exc:
            diagnosis = self._connection_diagnosis(url)
            raise BridgeClientError(
                f"Failed to reach SensorBridge at {url}: {exc.reason}",
                code="transport_error",
                detail={"url": url, "reason": str(exc.reason), "diagnosis": diagnosis},
            ) from exc
        except TimeoutError as exc:
            diagnosis = self._connection_diagnosis(url)
            raise BridgeClientError(
                f"Timed out reaching SensorBridge at {url}",
                code="transport_timeout",
                detail={"url": url, "diagnosis": diagnosis},
            ) from exc

        if not response_bytes:
            return {"ok": True}
        try:
            payload = json.loads(response_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BridgeClientError(
                f"SensorBridge returned non-JSON response from {url}",
                code="invalid_json_response",
                detail={"url": url, "body_prefix": response_bytes[:200].decode("utf-8", "replace")},
            ) from exc
        if not isinstance(payload, dict):
            raise BridgeClientError(
                f"SensorBridge returned a JSON {type(payload).__name__}, expected object",
                code="invalid_json_response",
                detail={"url": url, "payload": payload},
            )
        return payload

    def _http_error(self, exc: HTTPError, url: str) -> BridgeClientError:
        body = exc.read()
        detail: dict[str, Any] = {"url": url, "status": exc.code}
        if body:
            body_text = body.decode("utf-8", "replace")
            try:
                detail["response"] = json.loads(body_text)
            except json.JSONDecodeError:
                detail["body_prefix"] = body_text[:500]
        return BridgeClientError(
            f"SensorBridge HTTP {exc.code} for {url}",
            code="http_error",
            detail=detail,
            status=exc.code,
        )

    def _connection_diagnosis(self, url: str) -> dict[str, Any]:
        return {
            "reason": "backend_unreachable",
            "base_url": self.base_url,
            "failed_url": url,
            "checks": [
                f"curl.exe {self.base_url}/health",
                f"curl.exe {self.base_url}/api/v1/network",
                f"curl.exe {self.base_url}/api/v1/status",
                f"curl.exe {self.base_url}/api/v1/product/status",
            ],
            "hints": [
                "Confirm the iPad SensorBridge app is running and on the same LAN.",
                "Use the Mac USBMux tunnel URL if the direct iPad LAN URL is unreachable.",
            ],
        }


class UsbMuxTransport:
    """HTTP transport over an iproxy/libusbmuxd local port forward."""

    def __init__(
        self,
        *,
        local_port: int = 27181,
        device_port: int = 27180,
        iproxy_path: str | None = None,
        start_proxy: bool = False,
        timeout: float = 10.0,
        startup_delay_s: float = 0.5,
        process_factory: Any = subprocess.Popen,
        command_resolver: Any = shutil.which,
    ) -> None:
        if local_port < 1 or device_port < 1:
            raise BridgeClientError(
                "USBMux ports must be positive integers.",
                code="invalid_usbmux_port",
                detail={"local_port": local_port, "device_port": device_port},
            )
        self.local_port = local_port
        self.device_port = device_port
        self.iproxy_path = iproxy_path
        self.start_proxy = start_proxy
        self.timeout = timeout
        self.startup_delay_s = max(startup_delay_s, 0.0)
        self._process_factory = process_factory
        self._command_resolver = command_resolver
        self._process: Any = None
        self._http = HttpTransport(f"http://127.0.0.1:{self.local_port}", timeout=timeout)

        if self.start_proxy:
            self.start_iproxy()

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def start_iproxy(self) -> dict[str, Any]:
        if self._process is not None and self._process.poll() is None:
            return self.status()

        executable = self.iproxy_path or self._command_resolver("iproxy")
        if not executable or (self.iproxy_path and not os.path.exists(executable)):
            raise BridgeClientError(
                "iproxy was not found. Install libusbmuxd/libimobiledevice tooling or pass --iproxy-path.",
                code="usbmux_iproxy_not_found",
                detail={"iproxy_path": self.iproxy_path, "local_port": self.local_port, "device_port": self.device_port},
            )

        command = [executable, str(self.local_port), str(self.device_port)]
        try:
            self._process = self._process_factory(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise BridgeClientError(
                f"Failed to start iproxy: {exc}",
                code="usbmux_iproxy_start_failed",
                detail={"command": command, "error": str(exc)},
            ) from exc
        if self.startup_delay_s:
            time.sleep(self.startup_delay_s)
        if self._process.poll() is not None:
            raise BridgeClientError(
                "iproxy exited before the USBMux tunnel was ready.",
                code="usbmux_iproxy_exited",
                detail={
                    "command": command,
                    "exit_code": self._process.poll(),
                    "local_port": self.local_port,
                    "device_port": self.device_port,
                },
            )
        return self.status()

    def close(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except Exception:
            self._process.kill()

    def status(self) -> dict[str, Any]:
        running = self._process is not None and self._process.poll() is None
        return {
            "ok": True,
            "transport": "usbmux",
            "mode": "iproxy",
            "base_url": self.base_url,
            "local_port": self.local_port,
            "device_port": self.device_port,
            "proxy_started_by_client": self._process is not None,
            "proxy_running": running,
            "requires_admin": False,
            "requires_apple_mobile_device_support": True,
        }

    def request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._http.request_json(method, path, body, timeout=timeout)
