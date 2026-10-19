"""DataUpdateCoordinator for OpenWrt LuCI."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN
from .luci_client import LuciClient, LuciClientError

_LOGGER = logging.getLogger(__name__)

type LuciConfigEntry = ConfigEntry[LuciCoordinator]


class LuciCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching OpenWrt LuCI data."""

    config_entry: LuciConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: LuciConfigEntry,
        client: LuciClient,
    ) -> None:
        """Initialize coordinator."""
        poll_interval = config_entry.options.get(
            CONF_POLL_INTERVAL,
            config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.system_info: dict[str, Any] = {}
        self.router_mac: str | None = None
        self.parent_device_id: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all data from OpenWrt router."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_all_data)
        except LuciClientError as err:
            raise UpdateFailed(f"Error communicating with OpenWrt LuCI: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with OpenWrt LuCI: {err}") from err

    def _fetch_all_data(self) -> dict[str, Any]:
        """Synchronous method to fetch metrics and status."""
        if not self.system_info:
            try:
                self.system_info = self.client.get_system_info()
            except Exception as err:
                _LOGGER.warning("Could not fetch system info: %s", err)
                self.system_info = {
                    "model": "OpenWrt Router",
                    "kernel": "",
                    "hostname": self.client.host,
                }

        if not self.router_mac:
            try:
                raw_mac = self.client.exec(
                    "cat /sys/class/net/br-lan/address 2>/dev/null || cat /sys/class/net/eth0/address"
                ).strip().upper()
                if len(raw_mac) == 17:
                    self.router_mac = raw_mac
            except Exception as err:
                _LOGGER.debug("Could not determine router MAC: %s", err)

        metrics = self.client.get_system_metrics()
        interfaces = self.client.get_network_interfaces()
        radios = self.client.get_wireless_radios()

        # Parse ARP table for IP mappings
        arp_map: dict[str, str] = {}
        try:
            raw_arp = self.client.exec("cat /proc/net/arp")
            for line in raw_arp.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = parts[3].upper()
                    if mac != "00:00:00:00:00:00":
                        arp_map[mac] = ip
        except Exception:
            pass

        # Query stations on all active wireless interfaces
        stations: dict[str, dict[str, Any]] = {}
        for radio_name, radio_data in radios.items():
            ch = radio_data.get("channel", "auto")
            for iface_sec, iface_data in radio_data.get("interfaces", {}).items():
                ssid = iface_data.get("ssid", "")
                iface_name = iface_data.get("device", "wlan0")
                # Look for matching station dump on wlan0, wlan1, etc.
                # In OpenWrt Linux kernel, typical wireless ifaces are wlan0, wlan1
                target_iface = "wlan0"
                st_dict = self.client.get_wireless_stations(target_iface)
                for mac, st in st_dict.items():
                    st["channel"] = ch
                    st["ssid"] = ssid
                    st["ip_address"] = arp_map.get(mac)
                    stations[mac] = st

        return {
            "system_info": self.system_info,
            "metrics": metrics,
            "interfaces": interfaces,
            "radios": radios,
            "stations": stations,
            "arp": arp_map,
        }
