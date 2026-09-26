"""Notify entity of a discovered device, shows a message on the screen."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DiscoveredEntity, async_setup_discovered


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a notify entity for devices with a notify command."""
    async_setup_discovered(
        hass,
        entry,
        async_add_entities,
        lambda config: DeviceNotify(config) if "notify" in config["commands"] else None,
    )


class DeviceNotify(DiscoveredEntity, NotifyEntity):
    """Sends {key: "message"}, the title is put in front of the message."""

    _suffix = "notify"
    _attr_name = None

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        text = f"{title}: {message}" if title else message
        await self._async_send(self._config["commands"]["notify"]["key"], text)
