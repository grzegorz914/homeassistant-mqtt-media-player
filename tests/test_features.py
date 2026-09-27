"""Search, shuffle and repeat, app id, announce and grouping of zones."""

import json

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from homeassistant.components.media_player import (
    ATTR_GROUP_MEMBERS,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SHUFFLE,
    DOMAIN as MP_DOMAIN,
    MediaPlayerEntityFeature as F,
    SearchMediaQuery,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_component

from custom_components.mqtt_universal_media_player.const import DOMAIN


def _zone(zone: int, name: str) -> dict:
    return {
        "platform": DOMAIN,
        "unique_id": f"denon_zone{zone}",
        "device_class": "receiver",
        "state_topic": f"denon/{name}/HA State",
        "command_topic": f"denon/{name}/Set",
        "device": {"identifiers": [f"denon_zone{zone}"], "name": name},
        "commands": {
            "power": {"key": "Power"},
            "source": {"key": "RcControl"},
            "shuffle": {"key": "Shuffle"},
            "repeat": {"key": "Repeat"},
            **({"join": {"key": "Join"}} if zone else {}),
        },
        "sources": [{"id": "SINET", "name": "Network"}, {"id": "SICD", "name": "CD Player"}, {"id": "SITUNER", "name": "Tuner"}],
        "group": {"id": "denon_123", "leader": zone == 0},
    }


MAIN = _zone(0, "Salon")
ZONE2 = _zone(2, "Kuchnia")
ZONE3 = _zone(3, "Taras")


async def _setup(hass: HomeAssistant, *players: dict) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for player in players:
        await _fire(hass, f"homeassistant/media_player/{player['unique_id']}/config", player)


async def _fire(hass: HomeAssistant, topic: str, payload) -> None:
    async_fire_mqtt_message(hass, topic, json.dumps(payload))
    await hass.async_block_till_done()


async def _state(hass: HomeAssistant, player: dict, state: dict) -> None:
    await _fire(hass, player["state_topic"], state)


def _sent(mqtt_mock) -> list:
    return [(c.args[0], json.loads(c.args[1])) for c in mqtt_mock.async_publish.call_args_list]


def _features(hass: HomeAssistant, entity_id: str) -> F:
    return F(hass.states.get(entity_id).attributes[ATTR_SUPPORTED_FEATURES])


async def _call(hass: HomeAssistant, service: str, data: dict) -> None:
    await hass.services.async_call(MP_DOMAIN, service, data, blocking=True)


async def test_search(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, MAIN)
    assert F.SEARCH_MEDIA in _features(hass, "media_player.salon")
    entity = entity_component.EntityComponent.get_entity(hass.data[MP_DOMAIN], "media_player.salon")

    result = await entity.async_search_media(SearchMediaQuery(search_query="play"))
    assert [(r.title, r.media_content_id, r.media_content_type, r.can_play) for r in result.result] == [
        ("CD Player", "SICD", "source", True)
    ]
    # Case insensitive, the current source is marked like in the browser
    await _state(hass, MAIN, {"power": True, "source": "SINET"})
    result = await entity.async_search_media(SearchMediaQuery(search_query="NET"))
    assert [(r.title, r.can_play) for r in result.result] == [("● Network", False)]
    assert (await entity.async_search_media(SearchMediaQuery(search_query="xyz"))).result == []


async def test_shuffle_and_repeat(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, MAIN)
    await _state(hass, MAIN, {"power": True, "source": "SINET", "shuffle": True, "repeat": "ALL"})
    state = hass.states.get("media_player.salon")
    assert state.attributes[ATTR_MEDIA_SHUFFLE] is True
    assert state.attributes[ATTR_MEDIA_REPEAT] == "all"
    assert {F.SHUFFLE_SET, F.REPEAT_SET} <= set(_features(hass, "media_player.salon"))

    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "shuffle_set", {ATTR_ENTITY_ID: "media_player.salon", ATTR_MEDIA_SHUFFLE: False})
    await _call(hass, "repeat_set", {ATTR_ENTITY_ID: "media_player.salon", ATTR_MEDIA_REPEAT: "one"})
    assert _sent(mqtt_mock) == [("denon/Salon/Set", {"Shuffle": False}), ("denon/Salon/Set", {"Repeat": "one"})]

    # Null, the current source has no shuffle or repeat
    await _state(hass, MAIN, {"source": "SICD", "shuffle": None, "repeat": None})
    assert F.SHUFFLE_SET not in _features(hass, "media_player.salon")
    assert F.REPEAT_SET not in _features(hass, "media_player.salon")
    assert ATTR_MEDIA_SHUFFLE not in hass.states.get("media_player.salon").attributes


async def test_app_id(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, MAIN)
    await _state(hass, MAIN, {"power": True, "app_id": "netflix"})
    assert hass.states.get("media_player.salon").attributes["app_id"] == "netflix"


async def test_announce(hass: HomeAssistant, mqtt_mock) -> None:
    player = {**MAIN, "commands": {**MAIN["commands"], "play_media": {"key": "PlayMedia"}}}
    await _setup(hass, player)
    assert F.MEDIA_ANNOUNCE not in _features(hass, "media_player.salon")
    data = {ATTR_ENTITY_ID: "media_player.salon", "media_content_id": "http://x/a.mp3", "media_content_type": "music", "announce": True}

    # Not declared, played as normal media
    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "play_media", data)
    assert _sent(mqtt_mock) == [("denon/Salon/Set", {"PlayMedia": {"id": "http://x/a.mp3", "type": "music"}})]

    player["commands"]["play_media"] = {"key": "PlayMedia", "announce": True}
    await _fire(hass, "homeassistant/media_player/denon_zone0/config", player)
    assert F.MEDIA_ANNOUNCE in _features(hass, "media_player.salon")
    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "play_media", data)
    assert _sent(mqtt_mock) == [("denon/Salon/Set", {"PlayMedia": {"id": "http://x/a.mp3", "type": "music", "announce": True}})]


async def test_group_of_zones(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, MAIN, ZONE2, ZONE3)
    for player in (MAIN, ZONE2, ZONE3):
        await _state(hass, player, {"power": True, "source": "SICD", "joined": False})
        assert F.GROUPING in _features(hass, f"media_player.{player['device']['name'].lower()}")
    assert hass.states.get("media_player.salon").attributes[ATTR_GROUP_MEMBERS] == ["media_player.salon"]

    # Join from the leader, both zones follow the main zone
    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "join", {ATTR_ENTITY_ID: "media_player.salon", ATTR_GROUP_MEMBERS: ["media_player.kuchnia", "media_player.taras"]})
    assert _sent(mqtt_mock) == [("denon/Kuchnia/Set", {"Join": True}), ("denon/Taras/Set", {"Join": True})]

    await _state(hass, ZONE2, {"source": "SOURCE", "joined": True})
    group = ["media_player.salon", "media_player.kuchnia"]
    assert hass.states.get("media_player.salon").attributes[ATTR_GROUP_MEMBERS] == group
    assert hass.states.get("media_player.kuchnia").attributes[ATTR_GROUP_MEMBERS] == group
    assert hass.states.get("media_player.taras").attributes[ATTR_GROUP_MEMBERS] == ["media_player.taras"]

    # Join from a member with the leader
    await _state(hass, ZONE3, {"joined": True})
    group = ["media_player.salon", "media_player.kuchnia", "media_player.taras"]
    assert hass.states.get("media_player.taras").attributes[ATTR_GROUP_MEMBERS] == group

    # A member leaves, the zone returns to its previous input on the device
    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "unjoin", {ATTR_ENTITY_ID: "media_player.taras"})
    assert _sent(mqtt_mock) == [("denon/Taras/Set", {"Join": False})]
    await _state(hass, ZONE3, {"joined": False, "source": "SICD"})
    assert hass.states.get("media_player.salon").attributes[ATTR_GROUP_MEMBERS] == ["media_player.salon", "media_player.kuchnia"]

    # A zone turned off is not in the group
    await _state(hass, ZONE2, {"power": False})
    assert hass.states.get("media_player.salon").attributes[ATTR_GROUP_MEMBERS] == ["media_player.salon"]
    await _state(hass, ZONE2, {"power": True})

    # The leader ends the group
    mqtt_mock.async_publish.reset_mock()
    await _call(hass, "unjoin", {ATTR_ENTITY_ID: "media_player.salon"})
    assert _sent(mqtt_mock) == [("denon/Kuchnia/Set", {"Join": False})]

    # Members only group with their leader
    with pytest.raises(ServiceValidationError):
        await _call(hass, "join", {ATTR_ENTITY_ID: "media_player.kuchnia", ATTR_GROUP_MEMBERS: ["media_player.taras"]})


async def test_group_needs_the_same_group(hass: HomeAssistant, mqtt_mock) -> None:
    other = {**ZONE2, "unique_id": "other", "device": {"identifiers": ["other"], "name": "Inny"}, "state_topic": "o/State", "command_topic": "o/Set", "group": {"id": "other"}}
    plain = {**MAIN, "unique_id": "plain", "device": {"identifiers": ["plain"], "name": "Plain"}, "state_topic": "p/State", "command_topic": "p/Set"}
    plain.pop("group")
    await _setup(hass, MAIN, other, plain)
    assert F.GROUPING not in _features(hass, "media_player.plain")
    assert ATTR_GROUP_MEMBERS not in hass.states.get("media_player.plain").attributes
    with pytest.raises(ServiceValidationError):
        await _call(hass, "join", {ATTR_ENTITY_ID: "media_player.salon", ATTR_GROUP_MEMBERS: ["media_player.inny"]})
