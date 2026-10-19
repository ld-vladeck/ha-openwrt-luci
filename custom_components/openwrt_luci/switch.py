"""Switches for OpenWrt LuCI."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up OpenWrt LuCI switches."""
    coordinator = entry.runtime_data
    tracked_switches: set[str] = set()

    @callback
    def _async_add_wifi_switches() -> None:
        new_switches: list[SwitchEntity] = []
        radios = coordinator.data.get("radios", {})
        for radio_name, radio_info in radios.items():
            for iface_sec, iface_data in radio_info.get("interfaces", {}).items():
                if iface_sec not in tracked_switches:
                    tracked_switches.add(iface_sec)
                    new_switches.append(
                        OpenWrtWifiSwitch(coordinator, iface_sec, iface_data)
                    )
        if new_switches:
            async_add_entities(new_switches)

    _async_add_wifi_switches()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_wifi_switches))


class OpenWrtWifiSwitch(CoordinatorEntity[LuciCoordinator], SwitchEntity):
    """Switch to toggle Wi-Fi interfaces on OpenWrt."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LuciCoordinator,
        iface_section: str,
        iface_data: dict[str, Any],
    ) -> None:
        """Initialize Wi-Fi switch."""
        super().__init__(coordinator)
        self.iface_section = iface_section
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_wifi_{iface_section}"
        ssid = iface_data.get("ssid", "Wireless")
        self._attr_name = f"Wi-Fi {ssid}"
        self._attr_icon = "mdi:wifi"

        sys_info = coordinator.system_info
        model = sys_info.get("model", "OpenWrt Router")
        kernel = sys_info.get("kernel", "")
        connections = set()
        if coordinator.router_mac:
            connections.add((CONNECTION_NETWORK_MAC, coordinator.router_mac))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            connections=connections,
            name=f"{model} ({coordinator.client.host})",
            manufacturer="OpenWrt",
            model=model,
            sw_version=kernel,
            configuration_url=f"http://{coordinator.client.host}",
        )

    @property
    def is_on(self) -> bool:
        """Return True if Wi-Fi interface is enabled."""
        radios = self.coordinator.data.get("radios", {})
        for r_name, r_data in radios.items():
            iface = r_data.get("interfaces", {}).get(self.iface_section)
            if iface:
                return not iface.get("disabled", False)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Wi-Fi interface."""
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_wifi_state, self.iface_section, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Wi-Fi interface."""
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_wifi_state, self.iface_section, False
        )
        await self.coordinator.async_request_refresh()
