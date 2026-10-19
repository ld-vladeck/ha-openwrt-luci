"""Buttons for OpenWrt LuCI."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
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
    """Set up OpenWrt LuCI buttons."""
    coordinator = entry.runtime_data
    async_add_entities([OpenWrtRebootButton(coordinator)])


class OpenWrtRebootButton(CoordinatorEntity[LuciCoordinator], ButtonEntity):
    """Button to restart OpenWrt router."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_name = "Reboot"

    def __init__(self, coordinator: LuciCoordinator) -> None:
        """Initialize reboot button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_reboot"

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

    async def async_press(self) -> None:
        """Press the button to reboot."""
        _LOGGER.warning("Reboot triggered for %s", self.coordinator.client.host)
        await self.hass.async_add_executor_job(self.coordinator.client.reboot)
