"""Progress bar, media browser and play media."""

import json

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    DOMAIN as MP_DOMAIN,
    MediaPlayerEntityFeature as F,
)
from homeassistant.components.media_player.browse_media import BrowseMedia
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_component

from custom_components.mqtt_universal_media_player.const import DOMAIN

DISCOVERY = "homeassistant/media_player/vu/config"
STATE = "openwebif/Vu/HA State"
COMMAND = "openwebif/Vu/Set"
ENTITY = "media_player.vu"

VU = {
    "platform": DOMAIN,
    "unique_id": "vu",
    "state_topic": STATE,
    "command_topic": COMMAND,
    "device": {"identifiers": ["vu"], "name": "Vu"},
    "commands": {"power": {"key": "Power"}, "source": {"key": "Channel"}, "play_media": {"key": "PlayMedia"}},
    "sources": [{"id": "1:0:1:A", "name": "TVP 1 HD"}],
    "browse": [
        {"name": "Favourites", "type": "channel", "items": [{"id": "1:0:1:A", "name": "TVP 1 HD"}, {"id": "1:0:19:B", "name": "Polsat HD"}]},
        {"name": "Movies", "type": "channel", "items": [{"id": "1:0:1:C", "name": "Kino"}]},
    ],
}


async def _setup(hass: HomeAssistant, payload: dict) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, DISCOVERY, json.dumps(payload))
    await hass.async_block_till_done()


def _entity(hass: HomeAssistant):
    component: entity_component.EntityComponent = hass.data[MP_DOMAIN]
    return component.get_entity(ENTITY)


def _sent(mqtt_mock) -> list:
    return [(c.args[0], json.loads(c.args[1])) for c in mqtt_mock.async_publish.call_args_list]


async def test_progress_bar(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, VU)
    async_fire_mqtt_message(hass, STATE, json.dumps({"power": True, "media_position": 600, "media_duration": 1800}))
    await hass.async_block_till_done()
    attrs = hass.states.get(ENTITY).attributes
    assert attrs[ATTR_MEDIA_POSITION] == 600
    assert attrs[ATTR_MEDIA_DURATION] == 1800
    first = attrs[ATTR_MEDIA_POSITION_UPDATED_AT]

    # Same position keeps its update time, Home Assistant moves the bar itself
    async_fire_mqtt_message(hass, STATE, json.dumps({"volume": 20}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes[ATTR_MEDIA_POSITION_UPDATED_AT] == first

    # Epoch update time from the device
    async_fire_mqtt_message(hass, STATE, json.dumps({"media_position": 0, "media_duration": 60, "media_position_updated_at": 1790000000}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes[ATTR_MEDIA_POSITION_UPDATED_AT].timestamp() == 1790000000

    # No duration, no bar
    async_fire_mqtt_message(hass, STATE, json.dumps({"media_duration": None}))
    await hass.async_block_till_done()
    assert ATTR_MEDIA_POSITION not in hass.states.get(ENTITY).attributes


async def test_browse_folders_and_play(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, VU)
    features = hass.states.get(ENTITY).attributes[ATTR_SUPPORTED_FEATURES]
    assert features & F.BROWSE_MEDIA and features & F.PLAY_MEDIA

    entity = _entity(hass)
    root: BrowseMedia = await entity.async_browse_media()
    titles = [child.title for child in root.children]
    assert titles[:2] == ["Favourites", "Movies"]

    folder = await entity.async_browse_media(root.children[0].media_content_type, root.children[0].media_content_id)
    assert [(c.title, c.media_content_id, c.media_content_type, c.can_play) for c in folder.children] == [
        ("TVP 1 HD", "1:0:1:A", "channel", True),
        ("Polsat HD", "1:0:19:B", "channel", True),
    ]

    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(
        MP_DOMAIN, "play_media",
        {ATTR_ENTITY_ID: ENTITY, ATTR_MEDIA_CONTENT_ID: "1:0:19:B", ATTR_MEDIA_CONTENT_TYPE: "channel"},
        blocking=True,
    )
    await hass.services.async_call(
        MP_DOMAIN, "play_media",
        {ATTR_ENTITY_ID: ENTITY, ATTR_MEDIA_CONTENT_ID: "http://example.com/stream.m3u8", ATTR_MEDIA_CONTENT_TYPE: "url"},
        blocking=True,
    )
    assert _sent(mqtt_mock) == [
        (COMMAND, {"PlayMedia": {"id": "1:0:19:B", "type": "channel"}}),
        (COMMAND, {"PlayMedia": {"id": "http://example.com/stream.m3u8", "type": "url"}}),
    ]


async def test_sources_folder_without_browse(hass: HomeAssistant, mqtt_mock) -> None:
    plain = {**VU, "browse": [], "commands": {"power": {"key": "Power"}, "source": {"key": "Channel"}}}
    await _setup(hass, plain)
    entity = _entity(hass)
    root = await entity.async_browse_media()
    assert [child.title for child in root.children] == ["Sources"]
    folder = await entity.async_browse_media(root.children[0].media_content_type, root.children[0].media_content_id)
    assert folder.children[0].media_content_type == "source"

    # Playing a source selects it
    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(
        MP_DOMAIN, "play_media",
        {ATTR_ENTITY_ID: ENTITY, ATTR_MEDIA_CONTENT_ID: "1:0:1:A", ATTR_MEDIA_CONTENT_TYPE: "source"},
        blocking=True,
    )
    assert _sent(mqtt_mock) == [(COMMAND, {"Channel": "1:0:1:A"})]


async def test_browse_images_from_the_device(hass: HomeAssistant, mqtt_mock) -> None:
    import asyncio

    await _setup(hass, {**VU, "browse_image_topic": "openwebif/Vu/HA Browse Image"})
    entity = _entity(hass)
    root = await entity.async_browse_media()
    folder = await entity.async_browse_media(root.children[0].media_content_type, root.children[0].media_content_id)
    thumb = folder.children[0].thumbnail
    assert thumb.startswith(f"/api/media_player_proxy/{ENTITY}/browse_media/channel/")
    # Logos are fitted into the tile like app icons
    assert folder.children[0].media_class == "app"
    key = thumb.split("/channel/")[1].split("?")[0]

    # The request goes to the device, the answer comes on the browse image topic
    mqtt_mock.async_publish.reset_mock()
    task = asyncio.ensure_future(entity.async_get_browse_image("channel", key))
    for _ in range(5):
        await asyncio.sleep(0)
    assert _sent(mqtt_mock) == [(COMMAND, {"BrowseImage": {"type": "channel", "id": "1:0:1:A", "key": key}})]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    async_fire_mqtt_message(hass, f"openwebif/Vu/HA Browse Image/{key}", png)
    assert await task == (png, "image/png")

    # Cached, no second request
    mqtt_mock.async_publish.reset_mock()
    assert await entity.async_get_browse_image("channel", key) == (png, "image/png")
    assert _sent(mqtt_mock) == []

    # Empty answer, no icon
    key2 = folder.children[1].thumbnail.split("/channel/")[1].split("?")[0]
    task = asyncio.ensure_future(entity.async_get_browse_image("channel", key2))
    for _ in range(5):
        await asyncio.sleep(0)
    async_fire_mqtt_message(hass, f"openwebif/Vu/HA Browse Image/{key2}", b"")
    assert await task == (None, None)


async def test_current_item_marked(hass: HomeAssistant, mqtt_mock) -> None:
    await _setup(hass, VU)
    async_fire_mqtt_message(hass, STATE, json.dumps({"power": True, "source": "1:0:19:B"}))
    await hass.async_block_till_done()
    entity = _entity(hass)
    root = await entity.async_browse_media()
    assert [c.title for c in root.children[:2]] == ["● Favourites", "Movies"]
    folder = await entity.async_browse_media(root.children[0].media_content_type, root.children[0].media_content_id)
    assert [(c.title, c.can_play) for c in folder.children] == [("TVP 1 HD", True), ("● Polsat HD", False)]

    # Nothing is marked while the device is off
    async_fire_mqtt_message(hass, STATE, json.dumps({"power": False}))
    await hass.async_block_till_done()
    root = await entity.async_browse_media()
    assert root.children[0].title == "Favourites"
