"""Support for tracking OpenWrt LuCI wireless devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LuciConfigEntry, LuciCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuciConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker for OpenWrt LuCI component."""
    coordinator = entry.runtime_data
    tracked_macs: set[str] = set()

    @callback
    def _async_add_stations() -> None:
        """Add entities for stations seen for the first time."""
        current_stations = coordinator.data.get("stations", {})
        new_macs = set(current_stations.keys()) - tracked_macs
        if new_macs:
            tracked_macs.update(new_macs)
            async_add_entities(
                LuciStationTrackerEntity(coordinator, mac) for mac in new_macs
            )

    _async_add_stations()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_stations))


class LuciStationTrackerEntity(CoordinatorEntity[LuciCoordinator], ScannerEntity):
    """Representation of a wireless device connected to OpenWrt."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: LuciCoordinator, mac: str) -> None:
        """Initialize the station tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_mac_address = mac
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, mac)},
            name=f"Wi-Fi Client {mac}",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info for this client."""
        return self._attr_device_info

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity is enabled by default."""
        return self._attr_entity_registry_enabled_default

    @property
    def station_data(self) -> dict[str, Any]:
        """Return station dictionary from coordinator data."""
        return self.coordinator.data.get("stations", {}).get(self._mac, {})

    @property
    def ip_address(self) -> str | None:
        """Return the IP address if matched in ARP table."""
        return self.station_data.get("ip_address")

    @property
    def is_connected(self) -> bool:
        """Return true if the device is currently associated."""
        return self._mac in self.coordinator.data.get("stations", {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed network attributes for topology and network mapping."""
        st = self.station_data
        attrs: dict[str, Any] = {
            "mac_address": self._mac,
            "is_wireless": True,
            "connection_type": "Wi-Fi",
            "interface": st.get("interface", "wlan0"),
            "channel": st.get("channel", "1"),
            "ssid": st.get("ssid", "Wireless"),
        }
        for key in (
            "signal_dbm",
            "signal_avg_dbm",
            "tx_bitrate_mbit",
            "rx_bitrate_mbit",
            "rx_bytes",
            "tx_bytes",
            "connected_time_sec",
        ):
            if st.get(key) is not None:
                attrs[key] = st[key]

        return attrs
