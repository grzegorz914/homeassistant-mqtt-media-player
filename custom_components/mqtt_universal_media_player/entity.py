"""Shared parts of the entities created from one discovery message."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVERY

_LOGGER = logging.getLogger(__name__)


def device_info(config: dict[str, Any]) -> DeviceInfo:
    """Device of a discovered media player, shared by all its entities."""
    device = config["device"]
    identifiers = device.get("identifiers") or [config["unique_id"]]
    return DeviceInfo(
        identifiers={(DOMAIN, ident) for ident in identifiers},
        name=device.get("name") or config.get("name") or config["unique_id"],
        manufacturer=device.get("manufacturer"),
        model=device.get("model"),
        sw_version=device.get("sw_version"),
        hw_version=device.get("hw_version"),
        serial_number=device.get("serial_number"),
        configuration_url=device.get("configuration_url"),
    )


@callback
def async_setup_discovered(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[dict[str, Any]], Entity | None],
) -> None:
    """Create, update and remove the entities of one platform from discovery.

    factory returns the entity for a config, or None when the config has nothing
    for this platform (e.g. no screen command), which also removes an existing one.
    """
    entities: dict[str, Entity] = {}

    @callback
    def _async_discovered(object_id: str, config: dict[str, Any] | None) -> None:
        entity = entities.get(object_id)
        new = factory(config) if config is not None else None

        if new is None:
            if entity is not None:
                entities.pop(object_id)
                hass.async_create_task(async_remove_discovered(entity))
            return
        if entity is not None:
            entity.async_update_discovery(config)
            return
        entities[object_id] = new
        async_add_entities([new])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{SIGNAL_DISCOVERY}_{entry.entry_id}", _async_discovered)
    )


async def async_remove_discovered(entity: Entity) -> None:
    """Remove an entity (and its device when empty) after its config is gone."""
    if entity.hass is None:
        return
    ent_reg = er.async_get(entity.hass)
    dev_reg = dr.async_get(entity.hass)
    entry = ent_reg.async_get(entity.entity_id)
    if entry is None:
        await entity.async_remove(force_remove=True)
        return
    device_id = entry.device_id
    ent_reg.async_remove(entity.entity_id)
    if device_id and not er.async_entries_for_device(
        ent_reg, device_id, include_disabled_entities=True
    ):
        dev_reg.async_remove_device(device_id)


class DiscoveredEntity(Entity):
    """Extra entity of a discovered device, follows its state and availability.

    The extra entities are unavailable while the device is powered off, like
    the screen switch and notify of the built-in LG webOS TV integration.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _suffix = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config: dict[str, Any] = {}
        self._unsubscribe: list = []
        self._available_flag = True
        self._state: dict[str, Any] = {}
        self._apply_config(config)
        self._attr_unique_id = f"{config['unique_id']}_{self._suffix}"

    def _apply_config(self, config: dict[str, Any]) -> None:
        self._config = config
        self._attr_device_info = device_info(config)

    @callback
    def async_update_discovery(self, config: dict[str, Any]) -> None:
        """A new config was published for this device."""
        topics_changed = any(
            config.get(key) != self._config.get(key)
            for key in ("state_topic", "availability_topic")
        )
        self._apply_config(config)
        if self.hass is None:
            return
        if topics_changed:
            self.hass.async_create_task(self._async_subscribe_topics())
        self._update_from_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await self._async_subscribe_topics()

    async def async_will_remove_from_hass(self) -> None:
        self._unsubscribe_topics()

    def _unsubscribe_topics(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()

    async def _async_subscribe_topics(self) -> None:
        self._unsubscribe_topics()
        self._available_flag = "availability_topic" not in self._config
        self._unsubscribe.append(
            await mqtt.async_subscribe(
                self.hass, self._config["state_topic"], self._async_state_received, qos=1
            )
        )
        if topic := self._config.get("availability_topic"):
            self._unsubscribe.append(
                await mqtt.async_subscribe(
                    self.hass, topic, self._async_availability_received, qos=1
                )
            )

    @callback
    def _async_state_received(self, msg: mqtt.ReceiveMessage) -> None:
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        self._state.update(data)
        self._update_from_state()
        self.async_write_ha_state()

    @callback
    def _async_availability_received(self, msg: mqtt.ReceiveMessage) -> None:
        if msg.payload == self._config["payload_available"]:
            self._available_flag = True
        elif msg.payload == self._config["payload_not_available"]:
            self._available_flag = False
        else:
            return
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        powered = self._state.get("power") is not False and str(self._state.get("state", "")).lower() != "off"
        return self._available_flag and powered

    def _update_from_state(self) -> None:
        """Read the entity state from the device state."""

    async def _async_send(self, key: str, value: Any) -> None:
        await mqtt.async_publish(
            self.hass, self._config["command_topic"], json.dumps({key: value}), qos=1
        )
