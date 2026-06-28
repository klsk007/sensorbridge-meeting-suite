from __future__ import annotations

import unittest

from bridgeclient.errors import BridgeClientError
from bridgeclient.transport import UsbMuxTransport, normalize_base_url


class FakeHttp:
    def __init__(self) -> None:
        self.base_url = "http://127.0.0.1:29001"
        self.calls: list[tuple[str, str, object, float | None]] = []

    def request_json(self, method: str, path: str, body: object = None, *, timeout: float | None = None) -> dict[str, object]:
        self.calls.append((method, path, body, timeout))
        return {"ok": True, "path": path}


class FakeProcess:
    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.exit_code or 0

    def kill(self) -> None:
        self.killed = True
        self.exit_code = -9


class TransportTests(unittest.TestCase):
    def test_normalize_base_url_accepts_compact_http_typo(self) -> None:
        self.assertEqual(
            normalize_base_url("http//172.18.8.44:27180/"),
            "http://172.18.8.44:27180",
        )

    def test_usbmux_transport_delegates_to_forwarded_http_port(self) -> None:
        transport = UsbMuxTransport(local_port=29001, device_port=27180)
        fake = FakeHttp()
        transport._http = fake  # type: ignore[assignment]

        payload = transport.request_json("GET", "/health", timeout=3.0)

        self.assertTrue(payload["ok"])
        self.assertEqual(fake.calls, [("GET", "/health", None, 3.0)])
        self.assertEqual(transport.status()["base_url"], "http://127.0.0.1:29001")

    def test_usbmux_transport_reports_missing_iproxy(self) -> None:
        transport = UsbMuxTransport(command_resolver=lambda name: None)

        with self.assertRaises(BridgeClientError) as raised:
            transport.start_iproxy()

        self.assertEqual(raised.exception.code, "usbmux_iproxy_not_found")

    def test_usbmux_transport_reports_missing_explicit_iproxy_path(self) -> None:
        transport = UsbMuxTransport(iproxy_path="Z:\\missing\\iproxy.exe")

        with self.assertRaises(BridgeClientError) as raised:
            transport.start_iproxy()

        self.assertEqual(raised.exception.code, "usbmux_iproxy_not_found")

    def test_usbmux_transport_can_start_and_close_iproxy(self) -> None:
        calls: list[list[str]] = []
        process = FakeProcess()

        def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
            calls.append(command)
            return process

        transport = UsbMuxTransport(
            local_port=29002,
            device_port=27180,
            start_proxy=True,
            startup_delay_s=0,
            process_factory=fake_popen,
            command_resolver=lambda name: "iproxy.exe",
        )

        self.assertEqual(calls, [["iproxy.exe", "29002", "27180"]])
        self.assertTrue(transport.status()["proxy_running"])
        transport.close()
        self.assertTrue(process.terminated)

    def test_usbmux_transport_rejects_invalid_ports(self) -> None:
        with self.assertRaises(BridgeClientError) as raised:
            UsbMuxTransport(local_port=0)

        self.assertEqual(raised.exception.code, "invalid_usbmux_port")


if __name__ == "__main__":
    unittest.main()
