"""Test the OpenWrt LuCI component initialization."""

from unittest.mock import MagicMock, patch
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_luci.const import DOMAIN
from custom_components.openwrt_luci.luci_client import LuciAuthError, LuciClientError

MOCK_CONFIG_ENTRY_DATA = {
    "host": "192.168.1.1",
    "username": "root",
    "password": "secret_password",
    "ssl": False,
    "verify_ssl": False,
    "poll_interval": 30,
}


async def test_setup_unload_entry_success(hass: HomeAssistant) -> None:
    """Test successful setup and unload of entry."""
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

    assert entry.state == ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_auth_failed(hass: HomeAssistant) -> None:
    """Test setup fails with ConfigEntryAuthFailed on auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.openwrt_luci.LuciClient.login",
        side_effect=LuciAuthError("Invalid credentials"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.SETUP_ERROR


async def test_setup_entry_not_ready(hass: HomeAssistant) -> None:
    """Test setup fails with ConfigEntryNotReady on connection error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_CONFIG_ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.openwrt_luci.LuciClient.login",
        side_effect=LuciClientError("Connection refused"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.SETUP_RETRY
