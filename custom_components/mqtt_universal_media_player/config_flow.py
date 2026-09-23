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

from .const import CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX, DOMAIN


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
    """Allow changing the discovery prefix later."""

    async def async_step_init(
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
                return self.async_create_entry(data={CONF_DISCOVERY_PREFIX: prefix})
        return self.async_show_form(
            step_id="init", data_schema=_prefix_schema(current), errors=errors
        )
