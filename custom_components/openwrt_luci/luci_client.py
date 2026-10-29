"""Client for communicating with OpenWrt LuCI RPC."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any

_LOGGER = logging.getLogger(__name__)


class LuciClientError(Exception):
    """General error communicating with LuCI RPC."""


class LuciAuthError(LuciClientError):
    """Authentication failure."""


class LuciClient:
    """Client for OpenWrt LuCI RPC interface."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        ssl: bool = False,
        verify_ssl: bool = False,
        timeout: int = 10,
        retries: int = 1,
    ) -> None:
        """Initialize the LuCI client."""
        self.host = host
        self.username = username
        self.password = password
        self.ssl = ssl
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.retries = retries
        self.token: str | None = None
        self._last_cpu_stat: tuple[int, int] | None = None

        protocol = "https" if ssl else "http"
        self.base_url = f"{protocol}://{host}/cgi-bin/luci/rpc"

    def _call(
        self,
        endpoint: str,
        method: str,
        params: list[Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        """Execute a JSON-RPC call."""
        if params is None:
            params = []

        if endpoint != "auth" and not self.token:
            self.login()

        url = f"{self.base_url}/{endpoint}"
        if self.token and endpoint != "auth":
            url = f"{url}?auth={self.token}"

        payload = json.dumps({"method": method, "params": params}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as err:
                if err.code in (401, 403) and retry_auth and endpoint != "auth":
                    _LOGGER.debug("LuCI token expired, re-authenticating...")
                    try:
                        self.login()
                    except Exception:
                        self.token = None
                        raise
                    return self._call(endpoint, method, params, retry_auth=False)
                if err.code in (401, 403):
                    self.token = None
                    raise LuciAuthError(f"HTTP error {err.code}: {err.reason}") from err
                raise LuciClientError(f"HTTP error {err.code}: {err.reason}") from err
            except Exception as err:
                if attempt < self.retries:
                    attempt += 1
                    _LOGGER.debug(
                        "Transient network error connecting to %s (%s), retrying (attempt %d/%d)...",
                        self.host,
                        err,
                        attempt,
                        self.retries,
                    )
                    time.sleep(1)
                    continue
                raise LuciClientError(f"Network error communicating with {self.host}: {err}") from err

        if data.get("error"):
            err = data["error"]
            if isinstance(err, dict):
                err_msg = err.get("message", "Unknown error")
                err_code = err.get("code", 0)
            else:
                err_msg = str(err)
                err_code = 0

            if "Access denied" in err_msg or "unauthorized" in err_msg.lower() or err_code == -32002:
                if retry_auth and endpoint != "auth":
                    try:
                        self.login()
                    except Exception:
                        self.token = None
                        raise
                    return self._call(endpoint, method, params, retry_auth=False)
                self.token = None
                raise LuciAuthError(f"LuCI Auth Error: {err_msg}")
            raise LuciClientError(f"RPC error from {endpoint}.{method}: {err_msg}")

        return data.get("result")

    def login(self) -> str:
        """Authenticate with the router and obtain a session token."""
        try:
            result = self._call("auth", "login", [self.username, self.password], retry_auth=False)
        except Exception as err:
            self.token = None
            raise LuciAuthError(f"Cannot login to {self.host}: {err}") from err

        if not result:
            self.token = None
            raise LuciAuthError(f"Invalid credentials for {self.username}@{self.host}")

        self.token = result
        return self.token

    def exec(self, command: str) -> str:
        """Execute a shell command on OpenWrt."""
        res = self._call("sys", "exec", [command])
        return str(res or "")

    def get_system_info(self) -> dict[str, Any]:
        """Fetch model, release, and kernel information."""
        info: dict[str, Any] = {
            "model": "OpenWrt Device",
            "release": "OpenWrt",
            "kernel": "",
            "hostname": self.host,
        }

        raw_info = self.exec("cat /tmp/sysinfo/model 2>/dev/null; uname -srm; cat /proc/sys/kernel/hostname")
        lines = [line.strip() for line in raw_info.strip().splitlines() if line.strip()]

        if len(lines) >= 1:
            info["model"] = lines[0]
        if len(lines) >= 2:
            info["kernel"] = lines[1]
        if len(lines) >= 3:
            info["hostname"] = lines[2]

        return info

    def get_system_metrics(self) -> dict[str, Any]:
        """Fetch uptime, load averages, and memory statistics."""
        metrics: dict[str, Any] = {
            "uptime": 0,
            "loadavg_1m": 0.0,
            "loadavg_5m": 0.0,
            "loadavg_15m": 0.0,
            "cpu_usage_pct": 0.0,
            "memory_total_kb": 0,
            "memory_free_kb": 0,
            "memory_available_kb": 0,
            "memory_used_kb": 0,
            "memory_usage_pct": 0.0,
        }

        # 1. Uptime
        try:
            metrics["uptime"] = int(self._call("sys", "uptime", []) or 0)
        except Exception:
            raw_up = self.exec("cat /proc/uptime")
            if raw_up:
                try:
                    metrics["uptime"] = int(float(raw_up.split()[0]))
                except (IndexError, ValueError):
                    pass

        # 2. Load Average
        raw_load = self.exec("cat /proc/loadavg")
        if raw_load:
            parts = raw_load.strip().split()
            if len(parts) >= 3:
                try:
                    metrics["loadavg_1m"] = float(parts[0])
                    metrics["loadavg_5m"] = float(parts[1])
                    metrics["loadavg_15m"] = float(parts[2])
                except ValueError:
                    pass

        # 3. CPU Utilization Percentage (/proc/stat)
        raw_stat = self.exec("head -n 1 /proc/stat")
        total_ticks = 0
        idle_ticks = 0
        for line in raw_stat.splitlines():
            if line.startswith("cpu "):
                try:
                    p_ints = [int(p) for p in line.split()[1:]]
                    total_ticks = sum(p_ints)
                    idle_ticks = p_ints[3] + (p_ints[4] if len(p_ints) > 4 else 0)
                except (ValueError, IndexError):
                    pass
                break

        if total_ticks > 0:
            if self._last_cpu_stat is None:
                busy = max(0, total_ticks - idle_ticks)
                metrics["cpu_usage_pct"] = round((busy / total_ticks) * 100, 1)
            else:
                prev_tot, prev_idl = self._last_cpu_stat
                d_tot = total_ticks - prev_tot
                d_idl = idle_ticks - prev_idl
                if d_tot > 0:
                    busy = max(0, d_tot - d_idl)
                    metrics["cpu_usage_pct"] = round((busy / d_tot) * 100, 1)
                else:
                    metrics["cpu_usage_pct"] = 0.0

            self._last_cpu_stat = (total_ticks, idle_ticks)

        # 4. Memory Info
        raw_mem = self.exec("cat /proc/meminfo")
        mem_data: dict[str, int] = {}
        for line in raw_mem.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                num = re.search(r"\d+", v)
                if num:
                    mem_data[k.strip()] = int(num.group(0))

        total = mem_data.get("MemTotal", 0)
        free = mem_data.get("MemFree", 0)
        available = mem_data.get("MemAvailable")
        if available is None:
            # Fallback for older Linux kernels without MemAvailable
            buffers = mem_data.get("Buffers", 0)
            cached = mem_data.get("Cached", 0)
            available = free + buffers + cached

        used = max(0, total - available)
        pct = round((used / total * 100), 1) if total > 0 else 0.0

        metrics["memory_total_kb"] = total
        metrics["memory_free_kb"] = free
        metrics["memory_available_kb"] = available
        metrics["memory_used_kb"] = used
        metrics["memory_usage_pct"] = pct

        return metrics

    def get_network_interfaces(self) -> dict[str, dict[str, int]]:
        """Parse /proc/net/dev to obtain byte and packet statistics per interface."""
        interfaces: dict[str, dict[str, int]] = {}
        raw = self.exec("cat /proc/net/dev")
        lines = raw.strip().splitlines()

        for line in lines[2:]:
            if ":" not in line:
                continue
            iface, stats_str = line.split(":", 1)
            iface = iface.strip()
            parts = stats_str.strip().split()
            if len(parts) >= 16:
                try:
                    interfaces[iface] = {
                        "rx_bytes": int(parts[0]),
                        "rx_packets": int(parts[1]),
                        "rx_errors": int(parts[2]),
                        "rx_drops": int(parts[3]),
                        "tx_bytes": int(parts[8]),
                        "tx_packets": int(parts[9]),
                        "tx_errors": int(parts[10]),
                        "tx_drops": int(parts[11]),
                    }
                except ValueError:
                    continue

        return interfaces

    def get_wireless_radios(self) -> dict[str, dict[str, Any]]:
        """Query UCI wireless configuration to discover radios and SSIDs."""
        res = self._call("uci", "get_all", ["wireless"])
        radios: dict[str, dict[str, Any]] = {}
        if not isinstance(res, dict):
            return radios

        # Find wifi-devices
        for sec_name, sec_val in res.items():
            if isinstance(sec_val, dict) and sec_val.get(".type") == "wifi-device":
                radios[sec_name] = {
                    "section": sec_name,
                    "channel": sec_val.get("channel", "auto"),
                    "type": sec_val.get("type", "mac80211"),
                    "hwmode": sec_val.get("hwmode", "11g"),
                    "disabled": sec_val.get("disabled") == "1",
                    "interfaces": {},
                }

        # Find wifi-ifaces
        for sec_name, sec_val in res.items():
            if isinstance(sec_val, dict) and sec_val.get(".type") == "wifi-iface":
                dev = sec_val.get("device", "radio0")
                if dev not in radios:
                    radios[dev] = {
                        "section": dev,
                        "channel": "auto",
                        "disabled": False,
                        "interfaces": {},
                    }
                ssid = sec_val.get("ssid", "Wireless")
                disabled = sec_val.get("disabled") == "1" or radios[dev]["disabled"]
                radios[dev]["interfaces"][sec_name] = {
                    "section": sec_name,
                    "device": dev,
                    "ssid": ssid,
                    "mode": sec_val.get("mode", "ap"),
                    "network": sec_val.get("network", "lan"),
                    "encryption": sec_val.get("encryption", "none"),
                    "disabled": disabled,
                }

        return radios

    def get_wireless_stations(self, iface: str = "wlan0") -> dict[str, dict[str, Any]]:
        """Retrieve connected Wi-Fi stations using 'iw dev <iface> station dump'."""
        stations: dict[str, dict[str, Any]] = {}
        raw = self.exec(f"iw dev {iface} station dump")
        current_mac: str | None = None

        for line in raw.splitlines():
            line = line.strip()
            match_st = re.match(r"^Station\s+([0-9a-fA-F:]{17})", line)
            if match_st:
                current_mac = match_st.group(1).upper()
                stations[current_mac] = {
                    "mac": current_mac,
                    "interface": iface,
                    "signal_dbm": None,
                    "signal_avg_dbm": None,
                    "rx_bytes": 0,
                    "tx_bytes": 0,
                    "rx_packets": 0,
                    "tx_packets": 0,
                    "rx_bitrate_mbit": None,
                    "tx_bitrate_mbit": None,
                    "connected_time_sec": None,
                    "inactive_time_ms": None,
                }
                continue

            if not current_mac or current_mac not in stations:
                continue

            st = stations[current_mac]
            if line.startswith("signal:"):
                val = re.search(r"(-?\d+)", line)
                if val:
                    st["signal_dbm"] = int(val.group(1))
            elif line.startswith("signal avg:"):
                val = re.search(r"(-?\d+)", line)
                if val:
                    st["signal_avg_dbm"] = int(val.group(1))
            elif line.startswith("rx bytes:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["rx_bytes"] = int(val.group(1))
            elif line.startswith("tx bytes:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["tx_bytes"] = int(val.group(1))
            elif line.startswith("rx packets:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["rx_packets"] = int(val.group(1))
            elif line.startswith("tx packets:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["tx_packets"] = int(val.group(1))
            elif line.startswith("tx bitrate:"):
                val = re.search(r"([\d\.]+)\s*MBit/s", line)
                if val:
                    st["tx_bitrate_mbit"] = float(val.group(1))
            elif line.startswith("rx bitrate:"):
                val = re.search(r"([\d\.]+)\s*MBit/s", line)
                if val:
                    st["rx_bitrate_mbit"] = float(val.group(1))
            elif line.startswith("connected time:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["connected_time_sec"] = int(val.group(1))
            elif line.startswith("inactive time:"):
                val = re.search(r"(\d+)", line)
                if val:
                    st["inactive_time_ms"] = int(val.group(1))

        return stations

    def set_wifi_state(self, iface_section: str, enabled: bool) -> bool:
        """Enable or disable a Wi-Fi interface in UCI and reload Wi-Fi."""
        disabled_val = "0" if enabled else "1"
        try:
            self._call("uci", "set", ["wireless", iface_section, "disabled", disabled_val])
            self._call("uci", "commit", ["wireless"])
            self.exec("wifi")
            return True
        except Exception as err:
            _LOGGER.error("Failed to toggle Wi-Fi for %s: %s", iface_section, err)
            return False

    def reboot(self) -> bool:
        """Reboot the OpenWrt router."""
        try:
            self.exec("sleep 1 && reboot &")
            return True
        except Exception as err:
            _LOGGER.error("Failed to trigger reboot: %s", err)
            return False
