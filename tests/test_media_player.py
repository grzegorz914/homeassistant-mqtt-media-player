"""End to end tests against a real Home Assistant core with mocked MQTT."""

import json
from unittest.mock import call

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE,
    DOMAIN as MP_DOMAIN,
    MediaPlayerEntityFeature as F,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.mqtt_universal_media_player.const import DOMAIN

DISCOVERY = "homeassistant/media_player/denon_avr_main/config"
ENTITY = "media_player.denon_avr_x2800h"

DENON = {
    "platform": DOMAIN,
    "unique_id": "denon_123456_main",
    "device_class": "receiver",
    "state_topic": "denon/Denon AVR/HA State",
    "command_topic": "denon/Denon AVR/Set",
    "device": {
        "identifiers": ["denon_123456"],
        "name": "Denon AVR-X2800H",
        "manufacturer": "Denon",
        "model": "AVR-X2800H",
    },
    "commands": {
        "power": {"key": "Power"},
        "volume_set": {"key": "Volume", "min": 0, "max": 98},
        "mute": {"key": "Mute"},
        "source": {"key": "Input"},
        "sound_mode": {"key": "Surround"},
    },
    "sources": [{"id": "CD", "name": "CD"}, {"id": "TV", "name": "TV Audio"}],
    "sound_modes": [{"id": "STEREO", "name": "Stereo"}, {"id": "MOVIE", "name": "Movie"}],
}


def _device(hass: HomeAssistant):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "denon_123456"), entry.entry_id)


async def _setup(hass: HomeAssistant, mqtt_mock) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _discover(hass: HomeAssistant, payload: dict, topic: str = DISCOVERY) -> None:
    async_fire_mqtt_message(hass, topic, json.dumps(payload))
    await hass.async_block_till_done()


async def _service(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        MP_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY, **data}, blocking=True
    )


def _sent(mqtt_mock) -> list:
    return [
        (c.args[0], json.loads(c.args[1]))
        for c in mqtt_mock.async_publish.call_args_list
    ]


async def test_discovery_creates_one_full_entity(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, mqtt_mock)
    await _discover(hass, DENON)

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.attributes["device_class"] == "receiver"
    assert state.attributes["source_list"] == ["CD", "TV Audio"]
    assert state.attributes["sound_mode_list"] == ["Stereo", "Movie"]
    features = F(state.attributes[ATTR_SUPPORTED_FEATURES])
    for f in (F.TURN_ON, F.TURN_OFF, F.VOLUME_SET, F.VOLUME_STEP, F.VOLUME_MUTE,
              F.SELECT_SOURCE, F.SELECT_SOUND_MODE):
        assert f in features
    assert F.PLAY not in features

    device = _device(hass)
    assert device.manufacturer == "Denon" and device.model == "AVR-X2800H"


async def test_state_updates_and_partial_merge(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, mqtt_mock)
    await _discover(hass, DENON)

    async_fire_mqtt_message(hass, DENON["state_topic"], json.dumps(
        {"power": True, "volume": 49, "muted": False, "source": "TV", "sound_mode": "MOVIE"}))
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == pytest.approx(0.5)
    assert state.attributes[ATTR_MEDIA_VOLUME_MUTED] is False
    assert state.attributes[ATTR_INPUT_SOURCE] == "TV Audio"
    assert state.attributes[ATTR_SOUND_MODE] == "Movie"
    # Second line of the media card shows the current source and sound mode
    assert state.attributes["app_name"] == "TV Audio · Movie"

    # Partial update keeps the other values.
    async_fire_mqtt_message(hass, DENON["state_topic"], json.dumps({"muted": True}))
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.attributes[ATTR_MEDIA_VOLUME_MUTED] is True
    assert state.attributes[ATTR_INPUT_SOURCE] == "TV Audio"

    async_fire_mqtt_message(hass, DENON["state_topic"], json.dumps({"power": False}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "off"


async def test_commands_use_device_keys(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, mqtt_mock)
    await _discover(hass, DENON)
    mqtt_mock.async_publish.reset_mock()

    await _service(hass, "turn_on")
    await _service(hass, "turn_off")
    await _service(hass, "volume_set", **{ATTR_MEDIA_VOLUME_LEVEL: 0.5})
    await _service(hass, "volume_mute", **{ATTR_MEDIA_VOLUME_MUTED: True})
    await _service(hass, "select_source", **{ATTR_INPUT_SOURCE: "TV Audio"})
    await _service(hass, "select_sound_mode", **{ATTR_SOUND_MODE: "Movie"})

    topic = DENON["command_topic"]
    assert _sent(mqtt_mock) == [
        (topic, {"Power": True}),
        (topic, {"Power": False}),
        (topic, {"Volume": 49}),
        (topic, {"Mute": True}),
        (topic, {"Input": "TV"}),
        (topic, {"Surround": "MOVIE"}),
    ]

    with pytest.raises(ServiceValidationError):
        await _service(hass, "select_source", **{ATTR_INPUT_SOURCE: "Nope"})


async def test_volume_step_and_per_item_key(hass: HomeAssistant, mqtt_mock) -> None:
    """Xbox style: only volume up/down, sources launched with a different key."""
    xbox = {
        "platform": DOMAIN,
        "unique_id": "xbox_1",
        "device_class": "receiver",
        "state_topic": "microsoft/Xbox/HA State",
        "command_topic": "microsoft/Xbox/Set",
        "device": {"name": "Xbox"},
        "commands": {
            "power": {"key": "Power"},
            "volume_step": {"key": "Volume", "up": "up", "down": "down"},
            "mute": {"key": "Mute"},
            "play_pause": {"key": "RcControl", "value": "PlayPause"},
        },
        "sources": [
            {"id": "Dashboard", "name": "Dashboard", "key": "App"},
            {"id": "9NBLGGH4R315", "name": "Netflix", "key": "App"},
        ],
    }
    await _setup(hass, mqtt_mock)
    await _discover(hass, xbox, "homeassistant/media_player/xbox_1/config")
    entity = "media_player.xbox"
    features = F(hass.states.get(entity).attributes[ATTR_SUPPORTED_FEATURES])
    assert F.VOLUME_STEP in features and F.VOLUME_SET not in features
    assert F.SELECT_SOURCE in features and F.PLAY in features and F.PAUSE in features
    mqtt_mock.async_publish.reset_mock()

    for service, data in (("volume_up", {}), ("volume_down", {}), ("media_play", {}),
                          ("select_source", {ATTR_INPUT_SOURCE: "Netflix"})):
        await hass.services.async_call(MP_DOMAIN, service, {ATTR_ENTITY_ID: entity, **data},
                                       blocking=True)
    t = xbox["command_topic"]
    assert _sent(mqtt_mock) == [
        (t, {"Volume": "up"}), (t, {"Volume": "down"}),
        (t, {"RcControl": "PlayPause"}), (t, {"App": "9NBLGGH4R315"}),
    ]


async def test_toggle_mute_only_sent_when_needed(hass: HomeAssistant, mqtt_mock) -> None:
    """OpenWebIf style: Mute toggles, so muting an already muted box sends nothing."""
    cfg = {**DENON, "commands": {**DENON["commands"], "mute": {"key": "Mute", "toggle": True}}}
    await _setup(hass, mqtt_mock)
    await _discover(hass, cfg)
    async_fire_mqtt_message(hass, DENON["state_topic"], json.dumps({"power": True, "muted": True}))
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()

    await _service(hass, "volume_mute", **{ATTR_MEDIA_VOLUME_MUTED: True})
    assert _sent(mqtt_mock) == []
    await _service(hass, "volume_mute", **{ATTR_MEDIA_VOLUME_MUTED: False})
    assert _sent(mqtt_mock) == [(DENON["command_topic"], {"Mute": False})]


async def test_foreign_and_invalid_payloads_ignored(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, mqtt_mock)
    # bkbilly/mqtt_media_player style payload, no platform marker.
    await _discover(hass, {"name": "Other", "state_state_topic": "x"})
    # Ours but invalid device class.
    await _discover(hass, {**DENON, "device_class": "toaster"})
    assert hass.states.async_all(MP_DOMAIN) == []


async def test_config_update_and_removal(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, mqtt_mock)
    await _discover(hass, DENON)
    await _discover(hass, {**DENON, "sources": [{"id": "BD", "name": "Blu-ray"}]})
    assert hass.states.get(ENTITY).attributes["source_list"] == ["Blu-ray"]
    assert len(hass.states.async_all(MP_DOMAIN)) == 1

    async_fire_mqtt_message(hass, DISCOVERY, "")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None
    assert er.async_get(hass).async_get(ENTITY) is None
    assert _device(hass) is None


async def test_unload(hass: HomeAssistant, mqtt_mock) -> None:
    entry = await _setup(hass, mqtt_mock)
    await _discover(hass, DENON)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "unavailable"
