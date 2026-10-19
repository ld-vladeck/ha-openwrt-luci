"""Support for tracking OpenWrt LuCI wireless devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LuciConfigEntry, LuciCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuciConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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

    def __init__(self, coordinator: LuciCoordinator, mac: str) -> None:
        """Initialize the station tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{mac}"

    @property
    def station_data(self) -> dict[str, Any]:
        """Return station dictionary from coordinator data."""
        return self.coordinator.data.get("stations", {}).get(self._mac, {})

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER

    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def name(self) -> str:
        """Return the display name."""
        return f"Client {self._mac}"

    @property
    def hostname(self) -> str | None:
        """Return the hostname if known."""
        return None

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
        if st.get("signal_dbm") is not None:
            attrs["signal_dbm"] = st["signal_dbm"]
        if st.get("signal_avg_dbm") is not None:
            attrs["signal_avg_dbm"] = st["signal_avg_dbm"]
        if st.get("tx_bitrate_mbit") is not None:
            attrs["tx_bitrate_mbit"] = st["tx_bitrate_mbit"]
        if st.get("rx_bitrate_mbit") is not None:
            attrs["rx_bitrate_mbit"] = st["rx_bitrate_mbit"]
        if st.get("rx_bytes"):
            attrs["rx_bytes"] = st["rx_bytes"]
        if st.get("tx_bytes"):
            attrs["tx_bytes"] = st["tx_bytes"]
        if st.get("connected_time_sec"):
            attrs["connected_time_sec"] = st["connected_time_sec"]

        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Link this client device to the OpenWrt router parent in the Device Registry."""
        info: dict[str, Any] = {
            "connections": {(CONNECTION_NETWORK_MAC, self._mac)},
            "identifiers": {(DOMAIN, f"{self.coordinator.config_entry.entry_id}_{self._mac}")},
            "name": f"Wi-Fi Client {self._mac}",
        }
        if self.coordinator.parent_device_id:
            info["via_device_id"] = self.coordinator.parent_device_id

        return DeviceInfo(**info)
