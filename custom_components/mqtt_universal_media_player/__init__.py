"""MQTT Universal Media Player.

Creates one full media_player entity (device class, power, volume, mute,
source and sound mode selection, transport controls) from a single retained
MQTT discovery message, which the built-in MQTT integration cannot do.
Optional screen switch and notify entities are created on the same device.
"""

from __future__ import annotations

import json
import logging

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import discovery
from .const import CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX, SIGNAL_DISCOVERY

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.SWITCH, Platform.NOTIFY]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the platforms, then subscribe to discovery and dispatch to them."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT integration is not available")

    # The platforms listen for discovery first, retained configs arrive right after subscribing
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    prefix = entry.options.get(
        CONF_DISCOVERY_PREFIX,
        entry.data.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX),
    )
    signal = f"{SIGNAL_DISCOVERY}_{entry.entry_id}"

    @callback
    def _async_discovery(msg: mqtt.ReceiveMessage) -> None:
        object_id = msg.topic.split("/")[-2]
        payload = msg.payload

        # Empty retained payload removes the device.
        if not payload or (isinstance(payload, str) and not payload.strip()):
            async_dispatcher_send(hass, signal, object_id, None)
            return

        try:
            data = json.loads(payload)
        except ValueError:
            _LOGGER.debug("Ignoring non JSON discovery payload on %s", msg.topic)
            return
        if not discovery.is_ours(data):
            return

        try:
            config = discovery.validate(data)
        except vol.Invalid as err:
            _LOGGER.warning("Invalid discovery payload on %s: %s", msg.topic, err)
            return

        async_dispatcher_send(hass, signal, object_id, config)

    entry.async_on_unload(
        await mqtt.async_subscribe(
            hass, f"{prefix}/media_player/+/config", _async_discovery, qos=1
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a device from the UI, e.g. one that is no longer published."""
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after the options (discovery prefix) change."""
    await hass.config_entries.async_reload(entry.entry_id)
