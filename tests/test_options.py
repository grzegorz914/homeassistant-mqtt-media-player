"""Options: discovery prefix and the sources, apps and channels shown per device."""

import json

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE_LIST,
    DOMAIN as MP_DOMAIN,
    SearchMediaQuery,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_component

from custom_components.mqtt_universal_media_player.const import DOMAIN

DISCOVERY = "homeassistant/media_player/lg/config"
LG = {
    "platform": DOMAIN,
    "unique_id": "lg",
    "state_topic": "lg/State",
    "command_topic": "lg/Set",
    "device": {"identifiers": ["lg"], "name": "Salon"},
    "commands": {"power": {"key": "Power"}, "source": {"key": "Input"}},
    "sources": [{"id": "hdmi1", "name": "PS5"}, {"id": "netflix", "name": "Netflix"}],
    "browse": [
        {"name": "Inputs", "type": "app", "items": [{"id": "hdmi1", "name": "PS5"}, {"id": "hdmi2", "name": "HDMI 2"}]},
        {"name": "Apps", "type": "app", "items": [{"id": "netflix", "name": "Netflix"}, {"id": "youtube", "name": "YouTube"}]},
    ],
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, DISCOVERY, json.dumps(LG))
    await hass.async_block_till_done()
    return entry


async def _choose(hass: HomeAssistant, entry: MockConfigEntry, items: list[str]) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "device"})
    assert result["step_id"] == "device"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"device": "lg"})
    assert result["step_id"] == "items"
    assert result["description_placeholders"] == {"device": "Salon"}
    labels = {o["value"]: o["label"] for o in result["data_schema"].schema["items"].config["options"]}
    assert labels == {"hdmi1": "Inputs · PS5", "hdmi2": "Inputs · HDMI 2", "netflix": "Apps · Netflix", "youtube": "Apps · YouTube"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"items": items})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    # The entry reloads, the retained discovery comes back
    async_fire_mqtt_message(hass, DISCOVERY, json.dumps(LG))
    await hass.async_block_till_done()


def _entity(hass: HomeAssistant):
    return entity_component.EntityComponent.get_entity(hass.data[MP_DOMAIN], "media_player.salon")


async def test_selected_items(hass: HomeAssistant, mqtt_mock) -> None:
    entry = await _setup(hass)
    assert hass.states.get("media_player.salon").attributes[ATTR_INPUT_SOURCE_LIST] == ["PS5", "Netflix"]

    await _choose(hass, entry, ["hdmi1", "youtube"])
    assert entry.options == {"selected": {"lg": ["hdmi1", "youtube"]}}
    assert hass.states.get("media_player.salon").attributes[ATTR_INPUT_SOURCE_LIST] == ["PS5"]

    entity = _entity(hass)
    root = await entity.async_browse_media()
    assert [c.title for c in root.children if c.media_content_type == "folder"] == ["Inputs", "Apps"]
    apps = await entity.async_browse_media("folder", "1")
    assert [c.title for c in apps.children] == ["YouTube"]
    found = await entity.async_search_media(SearchMediaQuery(search_query="e"))
    assert [r.title for r in found.result] == ["YouTube"]

    # Everything chosen shows all again
    await _choose(hass, entry, ["hdmi1", "hdmi2", "netflix", "youtube"])
    assert entry.options == {"selected": {}}
    assert hass.states.get("media_player.salon").attributes[ATTR_INPUT_SOURCE_LIST] == ["PS5", "Netflix"]


async def test_folder_without_selected_items_hidden(hass: HomeAssistant, mqtt_mock) -> None:
    entry = await _setup(hass)
    await _choose(hass, entry, ["netflix"])
    root = await _entity(hass).async_browse_media()
    folders = [c for c in root.children if c.media_content_type == "folder"]
    assert [(c.title, c.media_content_id) for c in folders] == [("Apps", "1")]


async def test_prefix_keeps_selected(hass: HomeAssistant, mqtt_mock) -> None:
    entry = await _setup(hass)
    await _choose(hass, entry, ["netflix"])
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "prefix"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"discovery_prefix": "ha"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"selected": {"lg": ["netflix"]}, "discovery_prefix": "ha"}


async def test_no_devices(hass: HomeAssistant, mqtt_mock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"discovery_prefix": "homeassistant"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "device"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices"
