"""Unit tests for LuciClient."""

import io
import json
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

# Ensure custom_components/openwrt_luci is on path
current_dir = Path(__file__).parent.resolve()
repo_root = current_dir.parent
component_path = repo_root / "custom_components" / "openwrt_luci"
if str(component_path) not in sys.path:
    sys.path.insert(0, str(component_path))

from luci_client import LuciAuthError, LuciClient, LuciClientError


class TestLuciClient(unittest.TestCase):
    """Test suite for LuciClient."""

    def setUp(self):
        """Set up client instance."""
        self.client = LuciClient("192.168.1.1", "root", "secret_password")

    def test_init(self):
        """Test initialization and URL scheme handling."""
        client_http = LuciClient("192.168.1.1", "admin", "secret", ssl=False)
        self.assertEqual(client_http.base_url, "http://192.168.1.1/cgi-bin/luci/rpc")
        self.assertIsNone(client_http.token)

        client_https = LuciClient("192.168.1.1", "admin", "secret", ssl=True)
        self.assertEqual(client_https.base_url, "https://192.168.1.1/cgi-bin/luci/rpc")

    @patch("urllib.request.urlopen")
    def test_call_success(self, mock_urlopen):
        """Test successful JSON-RPC execution."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"result": "pong", "error": None}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # Set token to avoid auto-login for non-auth endpoints
        self.client.token = "dummy_token"
        result = self.client._call("sys", "ping")
        self.assertEqual(result, "pong")

    @patch.object(LuciClient, "login")
    @patch("urllib.request.urlopen")
    def test_call_http_error_token_expired(self, mock_urlopen, mock_login):
        """Test HTTP 403 error triggers re-authentication."""
        self.client.token = "expired_token"

        mock_err_response = urllib.error.HTTPError(
            url="http://192.168.1.1", code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO()
        )
        mock_success_response = MagicMock()
        mock_success_response.read.return_value = json.dumps({"result": "success", "error": None}).encode("utf-8")
        mock_success_response.__enter__.return_value = mock_success_response

        mock_urlopen.side_effect = [mock_err_response, mock_success_response]

        res = self.client._call("sys", "test_retry")
        self.assertEqual(res, "success")
        self.assertEqual(mock_login.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_call_http_error_fatal(self, mock_urlopen):
        """Test fatal HTTP error raises LuciClientError."""
        self.client.token = "token"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://192.168.1.1", code=500, msg="Internal Server Error", hdrs={}, fp=io.BytesIO()
        )
        with self.assertRaises(LuciClientError):
            self.client._call("sys", "fail")

    @patch("urllib.request.urlopen")
    def test_call_network_error(self, mock_urlopen):
        """Test network / connection failure raises LuciClientError."""
        self.client.token = "token"
        mock_urlopen.side_effect = OSError("Connection refused")
        with self.assertRaises(LuciClientError):
            self.client._call("sys", "fail")

    @patch.object(LuciClient, "login")
    @patch("urllib.request.urlopen")
    def test_call_rpc_access_denied_retry(self, mock_urlopen, mock_login):
        """Test RPC level access denied triggers re-authentication."""
        self.client.token = "token"
        resp_denied = MagicMock()
        resp_denied.read.return_value = json.dumps({"result": None, "error": {"code": -32002, "message": "Access denied"}}).encode("utf-8")
        resp_denied.__enter__.return_value = resp_denied

        resp_ok = MagicMock()
        resp_ok.read.return_value = json.dumps({"result": "ok", "error": None}).encode("utf-8")
        resp_ok.__enter__.return_value = resp_ok

        mock_urlopen.side_effect = [resp_denied, resp_ok]

        res = self.client._call("sys", "test")
        self.assertEqual(res, "ok")
        mock_login.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_call_rpc_error_generic(self, mock_urlopen):
        """Test generic RPC error raises LuciClientError."""
        self.client.token = "token"
        resp_err = MagicMock()
        resp_err.read.return_value = json.dumps({"result": None, "error": {"code": -32601, "message": "Method not found"}}).encode("utf-8")
        resp_err.__enter__.return_value = resp_err
        mock_urlopen.return_value = resp_err

        with self.assertRaises(LuciClientError):
            self.client._call("sys", "non_existent")

    @patch.object(LuciClient, "_call")
    def test_login_success(self, mock_call):
        """Test login success sets and returns token."""
        mock_call.return_value = "session_token_123"
        token = self.client.login()
        self.assertEqual(token, "session_token_123")
        self.assertEqual(self.client.token, "session_token_123")
        mock_call.assert_called_once_with("auth", "login", ["root", "secret_password"], retry_auth=False)

    @patch.object(LuciClient, "_call")
    def test_login_failure_empty_token(self, mock_call):
        """Test login failure when response token is empty."""
        mock_call.return_value = None
        with self.assertRaises(LuciAuthError):
            self.client.login()

    @patch.object(LuciClient, "_call")
    def test_login_failure_exception(self, mock_call):
        """Test login failure when _call raises exception."""
        mock_call.side_effect = LuciClientError("Network error")
        with self.assertRaises(LuciAuthError):
            self.client.login()

    @patch.object(LuciClient, "_call")
    def test_exec(self, mock_call):
        """Test exec wrapper."""
        mock_call.return_value = "command output\n"
        output = self.client.exec("uptime")
        self.assertEqual(output, "command output\n")
        mock_call.assert_called_once_with("sys", "exec", ["uptime"])

    @patch.object(LuciClient, "exec")
    def test_get_system_info(self, mock_exec):
        """Test system info parsing."""
        mock_exec.return_value = "OpenWrt Router Device\nLinux 5.15.0 mips\nOpenWrt\n"
        info = self.client.get_system_info()
        self.assertEqual(info["model"], "OpenWrt Router Device")
        self.assertEqual(info["kernel"], "Linux 5.15.0 mips")
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
            "Station 02:00:00:00:00:01 (on wlan0)\n"
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
        self.assertIn("02:00:00:00:00:01", stations)
        st = stations["02:00:00:00:00:01"]
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

    @patch.object(LuciClient, "_call")
    def test_get_wireless_radios(self, mock_call):
        """Test wireless radios and interfaces parsing from UCI."""
        mock_call.return_value = {
            "radio0": {
                ".type": "wifi-device",
                "type": "mac80211",
                "channel": "6",
                "hwmode": "11g",
                "disabled": "0",
            },
            "default_radio0": {
                ".type": "wifi-iface",
                "device": "radio0",
                "mode": "ap",
                "ssid": "MyOpenWrtWifi",
                "encryption": "psk2",
                "network": "lan",
                "disabled": "0",
            },
        }

        radios = self.client.get_wireless_radios()
        self.assertIn("radio0", radios)
        radio0 = radios["radio0"]
        self.assertEqual(radio0["channel"], "6")
        self.assertFalse(radio0["disabled"])
        self.assertIn("default_radio0", radio0["interfaces"])
        iface = radio0["interfaces"]["default_radio0"]
        self.assertEqual(iface["ssid"], "MyOpenWrtWifi")
        self.assertFalse(iface["disabled"])

    @patch.object(LuciClient, "_call")
    def test_get_wireless_radios_invalid_response(self, mock_call):
        """Test get_wireless_radios with invalid or non-dict response."""
        mock_call.return_value = None
        radios = self.client.get_wireless_radios()
        self.assertEqual(radios, {})

    @patch.object(LuciClient, "exec")
    @patch.object(LuciClient, "_call")
    def test_set_wifi_state_success(self, mock_call, mock_exec):
        """Test enabling and disabling wifi state."""
        success = self.client.set_wifi_state("default_radio0", enabled=True)
        self.assertTrue(success)
        mock_call.assert_any_call("uci", "set", ["wireless", "default_radio0", "disabled", "0"])
        mock_call.assert_any_call("uci", "commit", ["wireless"])
        mock_exec.assert_called_with("wifi")

    @patch.object(LuciClient, "_call")
    def test_set_wifi_state_failure(self, mock_call):
        """Test failure when setting wifi state."""
        mock_call.side_effect = LuciClientError("UCI commit failed")
        success = self.client.set_wifi_state("default_radio0", enabled=False)
        self.assertFalse(success)

    @patch.object(LuciClient, "exec")
    def test_reboot_success(self, mock_exec):
        """Test router reboot command."""
        success = self.client.reboot()
        self.assertTrue(success)
        mock_exec.assert_called_once_with("sleep 1 && reboot &")

    @patch.object(LuciClient, "exec")
    def test_reboot_failure(self, mock_exec):
        """Test reboot failure handling."""
        mock_exec.side_effect = LuciClientError("Command execution failed")
        success = self.client.reboot()
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
