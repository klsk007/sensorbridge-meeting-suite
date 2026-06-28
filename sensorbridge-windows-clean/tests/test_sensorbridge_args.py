from __future__ import annotations

import unittest
from unittest.mock import patch

import sensorbridge


class SensorBridgeArgsTests(unittest.TestCase):
    def test_open_dashboard_flag_defaults_off(self) -> None:
        with patch("sys.argv", ["sensorbridge.py"]):
            args = sensorbridge.parse_args()

        self.assertFalse(args.open_dashboard)

    def test_open_dashboard_flag_can_be_enabled(self) -> None:
        with patch("sys.argv", ["sensorbridge.py", "--port", "9000", "--open-dashboard"]):
            args = sensorbridge.parse_args()

        self.assertEqual(args.port, 9000)
        self.assertTrue(args.open_dashboard)


if __name__ == "__main__":
    unittest.main()
