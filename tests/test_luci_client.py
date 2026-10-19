"""Unit tests for LuciClient."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath("ha-openwrt-luci/custom_components/openwrt_luci"))
from luci_client import LuciClient


class TestLuciClient(unittest.TestCase):
    """Test suite for LuciClient parsing logic."""

    def setUp(self):
        """Set up client instance."""
        self.client = LuciClient("192.168.1.102", "root", "password")

    @patch.object(LuciClient, "exec")
    def test_get_system_info(self, mock_exec):
        """Test system info parsing."""
        mock_exec.return_value = "Huawei EchoLife HG553\nLinux 4.9.184 mips\nOpenWrt\n"
        info = self.client.get_system_info()
        self.assertEqual(info["model"], "Huawei EchoLife HG553")
        self.assertEqual(info["kernel"], "Linux 4.9.184 mips")
        self.assertEqual(info["hostname"], "OpenWrt")

    @patch.object(LuciClient, "exec")
    @patch.object(LuciClient, "_call")
    def test_get_system_metrics(self, mock_call, mock_exec):
        """Test metrics parsing."""
        mock_call.return_value = 3600
        mock_exec.side_effect = [
            "0.15 0.10 0.05 1/45 1234\n",  # loadavg
            "cpu  100 0 100 800 0 0 0 0 0 0\n",  # stat (total 1000, idle 800 -> 20%)
            "MemTotal: 60000 kB\nMemFree: 20000 kB\nMemAvailable: 30000 kB\n",  # meminfo
        ]
        metrics = self.client.get_system_metrics()
        self.assertEqual(metrics["uptime"], 3600)
        self.assertEqual(metrics["loadavg_1m"], 0.15)
        self.assertEqual(metrics["loadavg_5m"], 0.10)
        self.assertEqual(metrics["loadavg_15m"], 0.05)
        self.assertEqual(metrics["cpu_usage_pct"], 20.0)
        self.assertEqual(metrics["memory_total_kb"], 60000)
        self.assertEqual(metrics["memory_available_kb"], 30000)
        self.assertEqual(metrics["memory_used_kb"], 30000)
        self.assertEqual(metrics["memory_usage_pct"], 50.0)

        # Test subsequent poll with delta calculation
        mock_exec.side_effect = [
            "0.20 0.15 0.10 1/45 1235\n",  # loadavg
            "cpu  200 0 200 1600 0 0 0 0 0 0\n",  # stat (delta total 1000, delta idle 800 -> 20%)
            "MemTotal: 60000 kB\nMemFree: 20000 kB\nMemAvailable: 30000 kB\n",  # meminfo
        ]
        metrics2 = self.client.get_system_metrics()
        self.assertEqual(metrics2["cpu_usage_pct"], 20.0)

    @patch.object(LuciClient, "exec")
    def test_get_wireless_stations(self, mock_exec):
        """Test wireless station dump parsing."""
        mock_exec.return_value = (
            "Station 7E:F8:E1:DD:03:BB (on wlan0)\n"
            "\tinactive time:\t500 ms\n"
            "\trx bytes:\t1000000\n"
            "\ttx bytes:\t2000000\n"
            "\trx packets:\t5000\n"
            "\ttx packets:\t8000\n"
            "\tsignal:  \t-55 dBm\n"
            "\tsignal avg:\t-57 dBm\n"
            "\ttx bitrate:\t54.0 MBit/s\n"
            "\trx bitrate:\t48.0 MBit/s\n"
            "\tconnected time:\t1200 seconds\n"
        )
        stations = self.client.get_wireless_stations("wlan0")
        self.assertIn("7E:F8:E1:DD:03:BB", stations)
        st = stations["7E:F8:E1:DD:03:BB"]
        self.assertEqual(st["signal_dbm"], -55)
        self.assertEqual(st["signal_avg_dbm"], -57)
        self.assertEqual(st["tx_bitrate_mbit"], 54.0)
        self.assertEqual(st["rx_bitrate_mbit"], 48.0)
        self.assertEqual(st["connected_time_sec"], 1200)

    @patch.object(LuciClient, "exec")
    def test_get_network_interfaces(self, mock_exec):
        """Test network interfaces /proc/net/dev parsing."""
        mock_exec.return_value = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
            "  eth0: 100000   1000    0    0    0     0          0         0  200000   2000    0    0    0     0       0          0\n"
            " wlan0:  50000    500    0    0    0     0          0         0   60000    600    0    0    0     0       0          0\n"
        )
        ifaces = self.client.get_network_interfaces()
        self.assertIn("eth0", ifaces)
        self.assertIn("wlan0", ifaces)
        self.assertEqual(ifaces["eth0"]["rx_bytes"], 100000)
        self.assertEqual(ifaces["eth0"]["tx_bytes"], 200000)
        self.assertEqual(ifaces["wlan0"]["rx_bytes"], 50000)


if __name__ == "__main__":
    unittest.main()
