from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bridgeclient import (
    HttpTransport,
    SensorBridgeClient,
    UsbMuxTransport,
    build_directshow_camera_sender,
    inspect_camera_provider_status,
    inspect_directshow_camera_build_status,
    inspect_directshow_camera_open_status,
    inspect_directshow_camera_register_status,
    inspect_directshow_camera_sender_status,
    register_camera_provider,
    register_directshow_camera,
    start_camera_provider,
    start_directshow_camera_sender,
    stop_camera_provider,
    stop_directshow_camera_sender,
    unregister_directshow_camera,
)
from bridgeclient.errors import BridgeClientError


ROOT = Path(__file__).resolve().parent

ALIASES = {
    "health": "health",
    "status": "status",
    "network": "network",
    "capabilities": "capabilities",
    "doctor": "doctor",
    "product-status": "product_status",
    "product-contract": "product_contract",
    "product-start": "product_start",
    "product-stop": "product_stop",
    "webrtc-status": "webrtc_status",
    "webrtc-connect": "webrtc_connect",
    "webrtc-receiver-offer": "webrtc_receiver_offer",
    "webrtc-local-ice": "webrtc_local_ice",
    "webrtc-receiver-stats": "webrtc_receiver_stats",
    "camera-provider-status": "camera_provider_status",
    "camera-provider-start": "camera_provider_start",
    "camera-provider-stop": "camera_provider_stop",
    "camera-provider-register": "camera_provider_register",
    "directshow-camera-build-status": "directshow_camera_build_status",
    "directshow-camera-build": "directshow_camera_build",
    "directshow-camera-register-status": "directshow_camera_register_status",
    "directshow-camera-register": "directshow_camera_register",
    "directshow-camera-unregister": "directshow_camera_unregister",
    "directshow-camera-sender-status": "directshow_camera_sender_status",
    "directshow-camera-sender-start": "directshow_camera_sender_start",
    "directshow-camera-sender-stop": "directshow_camera_sender_stop",
    "directshow-camera-open-status": "directshow_camera_open_status",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SensorBridge camera-only CLI")
    parser.add_argument("command", nargs="?", default="product-status", help="Camera-only command to run.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="SensorBridge HTTP base URL.")
    parser.add_argument("--usb", action="store_true", help="Use iproxy to reach the iPad-hosted service.")
    parser.add_argument("--local-port", type=int, default=29001, help="Local forwarded port for --usb.")
    parser.add_argument("--device-port", type=int, default=27180, help="Device port for --usb.")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="Timeout for camera open probe commands.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def make_client(args: argparse.Namespace) -> SensorBridgeClient:
    if args.usb:
        return SensorBridgeClient(UsbMuxTransport(local_port=args.local_port, device_port=args.device_port, start_proxy=True))
    return SensorBridgeClient(HttpTransport(args.base_url))


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    command = ALIASES.get(args.command.lower(), args.command.lower().replace("-", "_"))
    client = make_client(args)
    try:
        if command == "health":
            return client.health()
        if command == "status":
            return client.status()
        if command == "network":
            return client.network()
        if command == "capabilities":
            return client.capabilities()
        if command == "doctor":
            return client.doctor()
        if command == "product_status":
            return client.product_status()
        if command == "product_contract":
            return client.product_contract()
        if command == "product_start":
            return client.start_product_mode()
        if command == "product_stop":
            return client.stop_product_mode()
        if command == "webrtc_status":
            return client.webrtc_status().to_json()
        if command == "webrtc_connect":
            return client.connect_webrtc_receiver()
        if command == "webrtc_receiver_offer":
            return client.create_webrtc_receiver_offer()
        if command == "webrtc_local_ice":
            return client.webrtc_local_ice_candidates().to_json()
        if command == "webrtc_receiver_stats":
            return client.receiver_stats()
    finally:
        transport = client.transport
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    if command == "camera_provider_status":
        return inspect_camera_provider_status(ROOT)
    if command == "camera_provider_start":
        return start_camera_provider(ROOT)
    if command == "camera_provider_stop":
        return stop_camera_provider(ROOT)
    if command == "camera_provider_register":
        return register_camera_provider(ROOT)
    if command == "directshow_camera_build_status":
        return inspect_directshow_camera_build_status(ROOT)
    if command == "directshow_camera_build":
        return build_directshow_camera_sender(ROOT)
    if command == "directshow_camera_register_status":
        return inspect_directshow_camera_register_status(ROOT)
    if command == "directshow_camera_register":
        return register_directshow_camera(ROOT)
    if command == "directshow_camera_unregister":
        return unregister_directshow_camera(ROOT)
    if command == "directshow_camera_sender_status":
        return inspect_directshow_camera_sender_status(ROOT)
    if command == "directshow_camera_sender_start":
        return start_directshow_camera_sender(ROOT)
    if command == "directshow_camera_sender_stop":
        return stop_directshow_camera_sender(ROOT)
    if command == "directshow_camera_open_status":
        return inspect_directshow_camera_open_status(ROOT, timeout_ms=args.timeout_ms)
    raise BridgeClientError(
        f"Unknown camera-only command: {args.command}",
        code="unknown_command",
        detail={"available_commands": sorted(ALIASES)},
    )


def main() -> int:
    args = parse_args()
    try:
        payload = run_command(args)
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0 if payload.get("ok", True) else 1
    except BridgeClientError as exc:
        print(json.dumps(exc.to_json(), ensure_ascii=False, indent=2 if args.pretty else None), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
