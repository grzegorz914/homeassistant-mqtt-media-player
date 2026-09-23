"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mqtt_universal_media_player.const import DOMAIN


async def test_user_flow(hass: HomeAssistant, mqtt_mock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"discovery_prefix": "bad/#"}
    )
    assert result["errors"] == {"discovery_prefix": "invalid_prefix"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"discovery_prefix": " /homeassistant/ "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"discovery_prefix": "homeassistant"}

    # Single instance only.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
