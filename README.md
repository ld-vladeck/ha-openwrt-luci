# OpenWrt LuCI Integration for Home Assistant

<p align="center">
  <img src="images/logo.png" alt="OpenWrt LuCI" width="350">
</p>

Custom component for Home Assistant providing complete monitoring, control, and wireless topology tracking for **OpenWrt routers and Access Points** using standard **LuCI RPC** (`luci-mod-rpc`).

Ideal for legacy routers (like Huawei EchoLife HG553 / Vodafone Station 1) and standalone Access Points where `ubus` HTTP or DHCP server capabilities are not available or not configured.

---

## Features

* **📡 Wireless Station Tracking (AP-Ready):**
  * Tracks connected Wi-Fi devices directly at the radio layer (`iw dev station dump` / `iwinfo`).
  * Works even when OpenWrt acts as a **dumb Access Point / Bridge** with DHCP disabled!
  * Exposes MAC address, signal strength (dBm), average signal, TX/RX bitrate, connected time, SSID, and channel.
  * Links all client trackers directly under the router in the Home Assistant Device Registry via `via_device`, making it 100% compatible with topology cards like [Network Map Card](https://github.com/ld-vladeck/net_map).
* **📊 System Monitoring:**
  * CPU Utilization Percentage (`%`)
  * CPU Load Average (1m, 5m, 15m)
  * RAM Memory Used, Free, Available, and Percentage
  * System Uptime
* **🌐 Network Interface Traffic:**
  * Real-time received and transmitted data (bytes) and packet counters for all network interfaces (`br-lan`, `wlan0`, `eth0`, etc.).
* **🔘 Device Control:**
  * **Wi-Fi Switches:** Toggle Wi-Fi interfaces on/off directly from Home Assistant via UCI.
  * **Reboot Button:** Safely restart the OpenWrt router from the UI.
* **⚡ Zero Router-side Overhead:**
  * Requires only `luci-mod-rpc` on OpenWrt.
  * Does not require `uhttpd-mod-ubus`, `rpcd` ACL configuration, or external Python libraries on Home Assistant.

---

## Router Requirements

On your OpenWrt router:
```bash
opkg update
opkg install luci-mod-rpc
/etc/init.d/uhttpd restart
```

---

## Installation

### Method 1: Manual Copy / FTP
1. Copy the folder `custom_components/openwrt_luci` into your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.

### Method 2: HACS Custom Repository
1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right > **Custom repositories**.
3. Add this repository URL, choose **Integration**, and click **Add**.
4. Download and restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **OpenWrt LuCI**.
3. Enter your router IP (e.g. `192.168.1.102`), username (`root`), and password.
4. Click **Submit**.
