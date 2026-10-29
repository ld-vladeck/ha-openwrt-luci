"""Test OpenWrt LuCI DataUpdateCoordinator."""

from unittest.mock import MagicMock, patch
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_luci.const import DOMAIN
from custom_components.openwrt_luci.coordinator import LuciCoordinator
from custom_components.openwrt_luci.luci_client import LuciClient, LuciClientError

MOCK_CONFIG_ENTRY_DATA = {
    "host": "192.168.1.1",
    "username": "root",
    "password": "secret_password",
    "ssl": False,
    "verify_ssl": False,
    "poll_interval": 30,
}


async def test_coordinator_fetch_all_data(hass: HomeAssistant) -> None:
    """Test coordinator fetches and aggregates router data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    client = LuciClient("192.168.1.1", "root", "secret_password")
    coordinator = LuciCoordinator(hass, entry, client)

    with patch.object(client, "get_system_info", return_value={"model": "OpenWrt Router", "kernel": "5.15.0"}), \
         patch.object(client, "exec") as mock_exec, \
         patch.object(client, "get_system_metrics", return_value={"uptime": 1200}), \
         patch.object(client, "get_network_interfaces", return_value={"eth0": {"rx_bytes": 100}}), \
         patch.object(client, "get_wireless_radios", return_value={
             "radio0": {
                 "channel": "6",
                 "interfaces": {"default_radio0": {"device": "radio0", "ssid": "MyWifi"}}
             }
         }), \
         patch.object(client, "get_wireless_stations", return_value={
             "02:00:00:00:00:01": {"signal_dbm": -50}
         }):

        mock_exec.side_effect = [
            "02:00:00:00:00:99\n",  # cat /sys/class/net/br-lan/address
            "IP address       HW type     Flags       HW address            Mask     Device\n192.168.1.50     0x1         0x2         02:00:00:00:00:01     *        br-lan\n",  # /proc/net/arp
        ]

        data = await coordinator._async_update_data()
        assert data["metrics"]["uptime"] == 1200
        assert coordinator.router_mac == "02:00:00:00:00:99"
        assert "02:00:00:00:00:01" in data["stations"]
        station = data["stations"]["02:00:00:00:00:01"]
        assert station["ip_address"] == "192.168.1.50"
        assert station["channel"] == "6"
        assert station["ssid"] == "MyWifi"


async def test_coordinator_fetch_error(hass: HomeAssistant) -> None:
    """Test coordinator wraps exceptions into UpdateFailed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    client = LuciClient("192.168.1.1", "root", "secret_password")
    coordinator = LuciCoordinator(hass, entry, client)

    with patch.object(coordinator, "_fetch_all_data", side_effect=LuciClientError("RPC Timeout")):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_coordinator_retries_system_info_if_fallback(hass: HomeAssistant) -> None:
    """Test coordinator re-attempts system_info if initial fetch had fallen back."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    client = LuciClient("192.168.1.1", "root", "secret_password")
    coordinator = LuciCoordinator(hass, entry, client)
    # Simulate initial failure fallback
    coordinator.system_info = {
        "model": "OpenWrt Router",
        "kernel": "",
        "hostname": "192.168.1.1",
    }

    with patch.object(client, "get_system_info", return_value={"model": "Real OpenWrt AP", "kernel": "6.6.0", "hostname": "OpenWrt-AP"}), \
         patch.object(client, "exec", return_value="02:00:00:00:00:99\n"), \
         patch.object(client, "get_system_metrics", return_value={"uptime": 100}), \
         patch.object(client, "get_network_interfaces", return_value={}), \
         patch.object(client, "get_wireless_radios", return_value={}):

        data = await coordinator._async_update_data()
        assert coordinator.system_info["model"] == "Real OpenWrt AP"
        assert coordinator.system_info["kernel"] == "6.6.0"

