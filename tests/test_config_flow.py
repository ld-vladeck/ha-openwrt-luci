"""Test the OpenWrt LuCI config flow."""

from unittest.mock import patch
import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_luci.const import (
    CONF_POLL_INTERVAL,
    DOMAIN,
)
from custom_components.openwrt_luci.luci_client import LuciAuthError, LuciClientError

MOCK_USER_INPUT = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "root",
    CONF_PASSWORD: "secret_password",
    CONF_SSL: False,
    CONF_VERIFY_SSL: False,
    CONF_POLL_INTERVAL: 30,
}


async def test_form_user(hass: HomeAssistant) -> None:
    """Test showing the user configuration form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


async def test_user_step_success(hass: HomeAssistant) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.openwrt_luci.config_flow.LuciClient.login",
        return_value="token123",
    ), patch(
        "custom_components.openwrt_luci.config_flow.LuciClient.get_system_info",
        return_value={"model": "OpenWrt Router", "hostname": "OpenWrt"},
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_USER_INPUT,
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "OpenWrt Router (192.168.1.1)"
    assert result2["data"] == MOCK_USER_INPUT


async def test_user_step_invalid_auth(hass: HomeAssistant) -> None:
    """Test invalid auth error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.openwrt_luci.config_flow.LuciClient.login",
        side_effect=LuciAuthError("Invalid credentials"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_USER_INPUT,
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Test cannot connect error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.openwrt_luci.config_flow.LuciClient.login",
        side_effect=LuciClientError("Connection refused"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_USER_INPUT,
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_step_unknown_error(hass: HomeAssistant) -> None:
    """Test unexpected error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.openwrt_luci.config_flow.LuciClient.login",
        side_effect=RuntimeError("Unexpected error"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_USER_INPUT,
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_duplicate_host(hass: HomeAssistant) -> None:
    """Test duplicate host aborts the flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_USER_INPUT,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        MOCK_USER_INPUT,
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow updates poll interval."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.1",
        data=MOCK_USER_INPUT,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_POLL_INTERVAL: 60},
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_POLL_INTERVAL: 60}

