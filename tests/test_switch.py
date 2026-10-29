"""Test OpenWrt LuCI switch entities."""

from unittest.mock import patch
import pytest

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.const import ATTR_ENTITY_ID
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

MOCK_RADIOS_DATA = {
    "radio0": {
        "section": "radio0",
        "channel": "auto",
        "disabled": False,
        "interfaces": {
            "default_radio0": {
                "section": "default_radio0",
                "device": "radio0",
                "ssid": "MyWifi",
                "disabled": False,
            }
        },
    }
}


async def test_wifi_switch(hass: HomeAssistant) -> None:
    """Test Wi-Fi switch turn on and turn off."""
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
             "radios": MOCK_RADIOS_DATA,
             "stations": {},
         }):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    switch_state = hass.states.get("switch.openwrt_router_192_168_1_1_wi_fi_mywifi")
    assert switch_state is not None
    assert switch_state.state == "on"

    with patch("custom_components.openwrt_luci.LuciClient.set_wifi_state", return_value=True) as mock_set_wifi, \
         patch("custom_components.openwrt_luci.coordinator.LuciCoordinator._fetch_all_data", return_value={
             "metrics": {"uptime": 100},
             "interfaces": {},
             "radios": {
                 "radio0": {
                     "section": "radio0",
                     "channel": "auto",
                     "disabled": False,
                     "interfaces": {
                         "default_radio0": {
                             "section": "default_radio0",
                             "device": "radio0",
                             "ssid": "MyWifi",
                             "disabled": True,
                         }
                     },
                 }
             },
             "stations": {},
         }):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.openwrt_router_192_168_1_1_wi_fi_mywifi"},
            blocking=True,
        )
        mock_set_wifi.assert_called_with("default_radio0", False)

        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.openwrt_router_192_168_1_1_wi_fi_mywifi"},
            blocking=True,
        )
        mock_set_wifi.assert_called_with("default_radio0", True)
