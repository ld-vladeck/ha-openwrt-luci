"""Test OpenWrt LuCI button entities."""

from unittest.mock import patch
import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
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


async def test_reboot_button(hass: HomeAssistant) -> None:
    """Test pressing the reboot button calls client.reboot."""
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
             "stations": {},
         }):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    button_state = hass.states.get("button.openwrt_router_192_168_1_1_reboot")
    assert button_state is not None

    with patch("custom_components.openwrt_luci.LuciClient.reboot", return_value=True) as mock_reboot:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.openwrt_router_192_168_1_1_reboot"},
            blocking=True,
        )
        mock_reboot.assert_called_once()
