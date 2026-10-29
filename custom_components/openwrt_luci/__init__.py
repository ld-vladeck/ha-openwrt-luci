"""The OpenWrt LuCI component."""

from __future__ import annotations

import logging

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from .const import DEFAULT_SSL, DEFAULT_VERIFY_SSL, DOMAIN, PLATFORMS
from .coordinator import LuciConfigEntry, LuciCoordinator
from .luci_client import LuciAuthError, LuciClient, LuciClientError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: LuciConfigEntry) -> bool:
    """Set up OpenWrt LuCI from a config entry."""
    client = LuciClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        ssl=entry.data.get(CONF_SSL, DEFAULT_SSL),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )

    try:
        await hass.async_add_executor_job(client.login)
    except LuciAuthError as err:
        raise ConfigEntryAuthFailed(f"Invalid credentials for {entry.data[CONF_HOST]}: {err}") from err
    except LuciClientError as err:
        raise ConfigEntryNotReady(f"Cannot connect to OpenWrt router at {entry.data[CONF_HOST]}: {err}") from err

    coordinator = LuciCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    # Pre-register parent router device in Device Registry to obtain parent_device_id
    device_registry = dr.async_get(hass)
    connections = set()
    if coordinator.router_mac:
        connections.add((CONNECTION_NETWORK_MAC, coordinator.router_mac))

    sys_info = coordinator.system_info
    model = sys_info.get("model", "OpenWrt Router")
    kernel = sys_info.get("kernel", "")

    parent_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        connections=connections,
        name=f"{model} ({coordinator.client.host})",
        manufacturer="OpenWrt",
        model=model,
        sw_version=kernel,
        configuration_url=f"http://{coordinator.client.host}",
    )
    coordinator.parent_device_id = parent_device.id

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: LuciConfigEntry) -> None:
    """Reload config entry on options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LuciConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
