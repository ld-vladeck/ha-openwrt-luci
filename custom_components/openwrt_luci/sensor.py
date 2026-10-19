"""Sensors for OpenWrt LuCI."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LuciConfigEntry, LuciCoordinator

_LOGGER = logging.getLogger(__name__)

SYSTEM_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="loadavg_1m",
        name="CPU Load (1m)",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
    ),
    SensorEntityDescription(
        key="loadavg_5m",
        name="CPU Load (5m)",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
    ),
    SensorEntityDescription(
        key="loadavg_15m",
        name="CPU Load (15m)",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
    ),
    SensorEntityDescription(
        key="cpu_usage_pct",
        name="CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
    ),
    SensorEntityDescription(
        key="memory_usage_pct",
        name="Memory Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
    ),
    SensorEntityDescription(
        key="memory_used_kb",
        name="Memory Used",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
    ),
    SensorEntityDescription(
        key="memory_free_kb",
        name="Memory Free",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
    ),
    SensorEntityDescription(
        key="memory_total_kb",
        name="Memory Total",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="wifi_clients_count",
        name="Connected Wi-Fi Clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi-star",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuciConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up OpenWrt LuCI sensors."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        LuciSystemSensor(coordinator, description) for description in SYSTEM_SENSORS
    ]

    # Add network interface sensors
    tracked_ifaces: set[str] = set()

    @callback
    def _async_add_iface_sensors() -> None:
        new_entities: list[SensorEntity] = []
        interfaces = coordinator.data.get("interfaces", {})
        for iface in interfaces:
            if iface not in tracked_ifaces:
                tracked_ifaces.add(iface)
                # Filter noise (e.g. lo)
                if iface != "lo":
                    new_entities.extend(
                        [
                            LuciInterfaceSensor(coordinator, iface, "rx_bytes", "Received Data", UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE),
                            LuciInterfaceSensor(coordinator, iface, "tx_bytes", "Transmitted Data", UnitOfInformation.BYTES, SensorDeviceClass.DATA_SIZE),
                            LuciInterfaceSensor(coordinator, iface, "rx_packets", "Received Packets", None, None),
                            LuciInterfaceSensor(coordinator, iface, "tx_packets", "Transmitted Packets", None, None),
                        ]
                    )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_iface_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_iface_sensors))

    async_add_entities(entities)


class LuciBaseSensor(CoordinatorEntity[LuciCoordinator], SensorEntity):
    """Base class for OpenWrt sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuciCoordinator) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
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


class LuciSystemSensor(LuciBaseSensor):
    """Sensor for general system status."""

    def __init__(
        self, coordinator: LuciCoordinator, description: SensorEntityDescription
    ) -> None:
        """Initialize system sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return native value of the sensor."""
        if self.entity_description.key == "wifi_clients_count":
            return len(self.coordinator.data.get("stations", {}))
        return self.coordinator.data.get("metrics", {}).get(self.entity_description.key)


class LuciInterfaceSensor(LuciBaseSensor):
    """Sensor for network interface metrics."""

    def __init__(
        self,
        coordinator: LuciCoordinator,
        interface: str,
        metric_key: str,
        metric_name: str,
        unit: Any,
        device_class: Any,
    ) -> None:
        """Initialize interface sensor."""
        super().__init__(coordinator)
        self.interface = interface
        self.metric_key = metric_key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{interface}_{metric_key}"
        self._attr_name = f"{interface} {metric_name}"
        if unit:
            self._attr_native_unit_of_measurement = unit
        if device_class:
            self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> Any:
        """Return current value."""
        iface_data = self.coordinator.data.get("interfaces", {}).get(self.interface, {})
        return iface_data.get(self.metric_key)
