"""Test OpenWrt LuCI sensors."""

from unittest.mock import patch
import pytest

from homeassistant.core import HomeAssistant
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

MOCK_COORDINATOR_DATA = {
    "metrics": {
        "uptime": 7200,
        "loadavg_1m": 0.25,
        "loadavg_5m": 0.15,
        "loadavg_15m": 0.10,
        "cpu_usage_pct": 15.0,
        "memory_usage_pct": 45.0,
        "memory_used_kb": 27000,
        "memory_free_kb": 33000,
        "memory_total_kb": 60000,
    },
    "interfaces": {
        "eth0": {
            "rx_bytes": 1000000,
            "tx_bytes": 500000,
            "rx_packets": 2000,
            "tx_packets": 1000,
        }
    },
    "radios": {},
    "stations": {
        "02:00:00:00:00:01": {},
        "02:00:00:00:00:02": {},
        "02:00:00:00:00:03": {},
    },
}


async def test_sensors(hass: HomeAssistant) -> None:
    """Test sensors setup and state values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.openwrt_luci.LuciClient.login", return_value="token123"), \
         patch("custom_components.openwrt_luci.coordinator.LuciCoordinator._fetch_all_data", return_value=MOCK_COORDINATOR_DATA):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state_uptime = hass.states.get("sensor.openwrt_router_192_168_1_1_uptime")
    assert state_uptime is not None
    assert state_uptime.state == "7200"

    state_cpu = hass.states.get("sensor.openwrt_router_192_168_1_1_cpu_usage")
    assert state_cpu is not None
    assert state_cpu.state == "15.0"

    state_clients = hass.states.get("sensor.openwrt_router_192_168_1_1_connected_wi_fi_clients")
    assert state_clients is not None
    assert state_clients.state == "3"

    state_rx_bytes = hass.states.get("sensor.openwrt_router_192_168_1_1_eth0_received_data")
    assert state_rx_bytes is not None
    assert state_rx_bytes.state == "1000000"
