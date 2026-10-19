"""Constants for the OpenWrt LuCI integration."""

from homeassistant.const import Platform

DOMAIN = "openwrt_luci"

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
]

DEFAULT_NAME = "OpenWrt LuCI"
DEFAULT_HOST = "192.168.1.1"
DEFAULT_USERNAME = "root"
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = False
DEFAULT_POLL_INTERVAL = 30

CONF_POLL_INTERVAL = "poll_interval"
