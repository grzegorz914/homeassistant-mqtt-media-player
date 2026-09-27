"""Config flow for MQTT Universal Media Player."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_DISCOVERY_PREFIX, CONF_SELECTED, DEFAULT_DISCOVERY_PREFIX, DOMAIN


def _prefix_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_DISCOVERY_PREFIX, default=default): str})


def _clean_prefix(value: str) -> str:
    return value.strip().strip("/")


class MqttUniversalMediaPlayerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            prefix = _clean_prefix(user_input[CONF_DISCOVERY_PREFIX])
            if not prefix or any(c in prefix for c in "+#"):
                errors[CONF_DISCOVERY_PREFIX] = "invalid_prefix"
            else:
                return self.async_create_entry(
                    title="MQTT Universal Media Player",
                    data={CONF_DISCOVERY_PREFIX: prefix},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_prefix_schema(DEFAULT_DISCOVERY_PREFIX),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MqttUniversalMediaPlayerOptionsFlow()


class MqttUniversalMediaPlayerOptionsFlow(OptionsFlow):
    """Discovery prefix, and the sources, apps and channels shown per device."""

    def __init__(self) -> None:
        self._device: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["device", "prefix"])

    async def async_step_prefix(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options.get(
            CONF_DISCOVERY_PREFIX,
            self.config_entry.data.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX),
        )
        if user_input is not None:
            prefix = _clean_prefix(user_input[CONF_DISCOVERY_PREFIX])
            if not prefix or any(c in prefix for c in "+#"):
                errors[CONF_DISCOVERY_PREFIX] = "invalid_prefix"
            else:
                return self.async_create_entry(
                    data={**self.config_entry.options, CONF_DISCOVERY_PREFIX: prefix}
                )
        return self.async_show_form(
            step_id="prefix", data_schema=_prefix_schema(current), errors=errors
        )

    def _configs(self) -> dict[str, dict[str, Any]]:
        """Discovered devices with sources, apps or channels, by unique id."""
        configs = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
        return {config["unique_id"]: config for config in configs.values() if _items(config)}

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        configs = self._configs()
        if not configs:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            self._device = user_input["device"]
            return await self.async_step_items()

        options = [
            SelectOptionDict(value=unique_id, label=_device_name(config))
            for unique_id, config in sorted(configs.items(), key=lambda c: _device_name(c[1]).casefold())
        ]
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_items(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        config = self._configs().get(self._device or "")
        if config is None:
            return self.async_abort(reason="no_devices")
        items = _items(config)
        selected: dict[str, list[str]] = dict(self.config_entry.options.get(CONF_SELECTED, {}))

        if user_input is not None:
            chosen = [item for item in user_input.get("items", []) if item in items]
            # Nothing or everything chosen shows all, also items added to the device later
            if not chosen or len(chosen) == len(items):
                selected.pop(config["unique_id"], None)
            else:
                selected[config["unique_id"]] = chosen
            return self.async_create_entry(
                data={**self.config_entry.options, CONF_SELECTED: selected}
            )

        current = [item for item in selected.get(config["unique_id"], []) if item in items] or list(items)
        return self.async_show_form(
            step_id="items",
            data_schema=vol.Schema(
                {
                    vol.Optional("items", description={"suggested_value": current}): SelectSelector(
                        SelectSelectorConfig(
                            options=[SelectOptionDict(value=value, label=label) for value, label in items.items()],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"device": _device_name(config)},
        )


def _device_name(config: dict[str, Any]) -> str:
    return config["device"].get("name") or config.get("name") or config["unique_id"]


def _items(config: dict[str, Any]) -> dict[str, str]:
    """Id to label of the sources, apps and channels of a device, in the media browser order."""
    items: dict[str, str] = {}
    for folder in config.get("browse") or []:
        for item in folder["items"]:
            items.setdefault(str(item["id"]), f"{folder['name']} · {item['name']}")
    for item in config["sources"]:
        items.setdefault(str(item["id"]), item["name"] if not config.get("browse") else f"Sources · {item['name']}")
    return items
