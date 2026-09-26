"""Screen switch of a discovered device, like the LG webOS TV integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DiscoveredEntity, async_setup_discovered


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a screen switch for devices with a screen command."""
    async_setup_discovered(
        hass,
        entry,
        async_add_entities,
        lambda config: ScreenSwitch(config) if "screen" in config["commands"] else None,
    )


class ScreenSwitch(DiscoveredEntity, SwitchEntity):
    """Turns the screen off while the device keeps playing the sound."""

    _suffix = "screen"
    _attr_translation_key = "screen"

    def _update_from_state(self) -> None:
        screen = self._state.get("screen")
        self._attr_is_on = screen if isinstance(screen, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send(self._config["commands"]["screen"]["key"], True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send(self._config["commands"]["screen"]["key"], False)
