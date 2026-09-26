"""Screen switch and notify entities created on the device of the media player."""

import json

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.mqtt_universal_media_player.const import DOMAIN

DISCOVERY = "homeassistant/media_player/lg_aabbcc/config"
STATE = "lg/Biuro TV/HA State"
COMMAND = "lg/Biuro TV/Set"

LG = {
    "platform": DOMAIN,
    "unique_id": "lg_aabbcc",
    "device_class": "tv",
    "state_topic": STATE,
    "command_topic": COMMAND,
    "availability_topic": "lg/Biuro TV/Availability",
    "device": {"identifiers": ["lg_aabbcc"], "name": "Biuro TV", "manufacturer": "LG Electronics"},
    "commands": {"power": {"key": "Power"}, "screen": {"key": "Screen"}, "notify": {"key": "Notify"}},
    "sources": [{"id": "netflix", "name": "Netflix"}],
}


async def _setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _fire(hass: HomeAssistant, topic: str, payload) -> None:
    async_fire_mqtt_message(hass, topic, payload if isinstance(payload, str) else json.dumps(payload))
    await hass.async_block_till_done()


def _sent(mqtt_mock) -> list:
    return [(c.args[0], json.loads(c.args[1])) for c in mqtt_mock.async_publish.call_args_list]


def _ids(hass: HomeAssistant) -> dict:
    ent_reg = er.async_get(hass)
    return {e.unique_id: e for e in ent_reg.entities.values() if e.platform == DOMAIN}


async def test_extras_on_the_media_player_device(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass)
    await _fire(hass, DISCOVERY, LG)

    entities = _ids(hass)
    assert set(entities) == {"lg_aabbcc", "lg_aabbcc_screen", "lg_aabbcc_notify"}
    assert len({e.device_id for e in entities.values()}) == 1
    assert entities["lg_aabbcc_screen"].entity_id == "switch.biuro_tv_screen"
    assert entities["lg_aabbcc_notify"].entity_id == "notify.biuro_tv"
    device = dr.async_get(hass).async_get(entities["lg_aabbcc"].device_id)
    assert device.name == "Biuro TV"


async def test_screen_switch(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass)
    await _fire(hass, DISCOVERY, LG)
    await _fire(hass, "lg/Biuro TV/Availability", "online")

    await _fire(hass, STATE, {"power": True, "state": "on", "screen": True})
    assert hass.states.get("switch.biuro_tv_screen").state == STATE_ON
    await _fire(hass, STATE, {"screen": False})
    assert hass.states.get("switch.biuro_tv_screen").state == STATE_OFF

    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(SWITCH_DOMAIN, "turn_on", {ATTR_ENTITY_ID: "switch.biuro_tv_screen"}, blocking=True)
    await hass.services.async_call(SWITCH_DOMAIN, "turn_off", {ATTR_ENTITY_ID: "switch.biuro_tv_screen"}, blocking=True)
    assert _sent(mqtt_mock) == [(COMMAND, {"Screen": True}), (COMMAND, {"Screen": False})]

    # Unavailable while the TV is off or offline, like the built-in integration
    await _fire(hass, STATE, {"power": False, "state": "off"})
    assert hass.states.get("switch.biuro_tv_screen").state == STATE_UNAVAILABLE
    await _fire(hass, STATE, {"power": True, "state": "on"})
    assert hass.states.get("switch.biuro_tv_screen").state == STATE_OFF
    await _fire(hass, "lg/Biuro TV/Availability", "offline")
    assert hass.states.get("switch.biuro_tv_screen").state == STATE_UNAVAILABLE


async def test_notify(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass)
    await _fire(hass, DISCOVERY, LG)
    await _fire(hass, "lg/Biuro TV/Availability", "online")
    await _fire(hass, STATE, {"power": True, "state": "on"})

    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(NOTIFY_DOMAIN, "send_message", {ATTR_ENTITY_ID: "notify.biuro_tv", "message": "Pranie gotowe"}, blocking=True)
    await hass.services.async_call(NOTIFY_DOMAIN, "send_message", {ATTR_ENTITY_ID: "notify.biuro_tv", "message": "Otwarte", "title": "Drzwi"}, blocking=True)
    assert _sent(mqtt_mock) == [(COMMAND, {"Notify": "Pranie gotowe"}), (COMMAND, {"Notify": "Drzwi: Otwarte"})]


async def test_extras_follow_the_config(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass)
    await _fire(hass, DISCOVERY, LG)
    device_id = _ids(hass)["lg_aabbcc"].device_id

    # Screen command dropped (e.g. older webOS), only the switch goes away
    without_screen = {**LG, "commands": {k: v for k, v in LG["commands"].items() if k != "screen"}}
    await _fire(hass, DISCOVERY, without_screen)
    assert set(_ids(hass)) == {"lg_aabbcc", "lg_aabbcc_notify"}
    assert hass.states.get("switch.biuro_tv_screen") is None

    # Added back
    await _fire(hass, DISCOVERY, LG)
    assert "lg_aabbcc_screen" in _ids(hass)

    # Empty config removes all entities and the device
    await _fire(hass, DISCOVERY, "")
    assert _ids(hass) == {}
    assert dr.async_get(hass).async_get(device_id) is None


async def test_no_extras_without_commands(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass)
    plain = {**LG, "commands": {"power": {"key": "Power"}}}
    await _fire(hass, DISCOVERY, plain)
    assert set(_ids(hass)) == {"lg_aabbcc"}
