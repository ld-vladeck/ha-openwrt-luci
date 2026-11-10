"""Test OpenWrt LuCI device tracker entities."""

from unittest.mock import patch
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_luci.const import DOMAIN

MOCK_CONFIG_ENTRY_DATA = {
    "host": "192.168.1.1",
    "username": "root",
    "password": "secret_password",
    "ssl": False,
    "verify_ssl": False,
    "poll_interval": 30,
}

MOCK_STATIONS_DATA = {
    "02:00:00:00:00:01": {
        "mac": "02:00:00:00:00:01",
        "ip_address": "192.168.1.50",
        "signal_dbm": -60,
        "tx_bitrate_mbit": 150.0,
        "interface": "wlan0",
    }
}


async def test_device_tracker(hass: HomeAssistant) -> None:
    """Test device tracker adds connected stations and registers standard device info."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.openwrt_luci.LuciClient.login", return_value="token123"), \
         patch("custom_components.openwrt_luci.coordinator.LuciCoordinator._fetch_all_data", return_value={
             "metrics": {"uptime": 100},
             "interfaces": {},
             "radios": {},
             "stations": MOCK_STATIONS_DATA,
         }):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    tracker_state = hass.states.get("device_tracker.wi_fi_client_02_00_00_00_00_01")
    assert tracker_state is not None
    assert tracker_state.state == "home"
    assert tracker_state.attributes.get("ip") == "192.168.1.50"
    assert tracker_state.attributes.get("signal_dbm") == -60

    # Verify entity registry uses MAC as unique_id
    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get("device_tracker.wi_fi_client_02_00_00_00_00_01")
    assert entity_entry is not None
    assert entity_entry.unique_id == "02:00:00:00:00:01"

    # Verify device registry entry has CONNECTION_NETWORK_MAC, no domain identifiers,
    # and is connected via the router device
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(
        connections={(CONNECTION_NETWORK_MAC, "02:00:00:00:00:01")}
    )
    assert device is not None
    assert device.name == "Wi-Fi Client 02:00:00:00:00:01"
    assert len(device.identifiers) == 0
    router_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert router_device is not None
    assert device.via_device_id == router_device.id

    # Test disconnection: station no longer in coordinator data
    with patch("custom_components.openwrt_luci.coordinator.LuciCoordinator._fetch_all_data", return_value={
        "metrics": {"uptime": 130},
        "interfaces": {},
        "radios": {},
        "stations": {},
    }):
        coordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    tracker_state = hass.states.get("device_tracker.wi_fi_client_02_00_00_00_00_01")
    assert tracker_state is not None
    assert tracker_state.state == "not_home"
