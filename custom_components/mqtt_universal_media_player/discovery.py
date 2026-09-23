"""Discovery payload schema.

A device publishes one retained JSON message to
``<discovery_prefix>/media_player/<object_id>/config``. Commands are sent back
to the device as ``{"<key>": <value>}`` on ``command_topic``, so the device
only has to declare which of its existing command keys map to which action.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from .const import PLATFORM_MARKER

DEVICE_CLASSES = ("tv", "speaker", "receiver", "projector")

_SCALAR = vol.Any(str, int, float, bool)

# Generic command: sends {key: <value supplied by the action>}.
# "toggle": the device flips the state on every command (value ignored), so
# the command is only sent when the requested state differs from the current one.
COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("key"): str,
        vol.Optional("toggle", default=False): bool,
    }
)

# Fixed command: always sends {key: value}, e.g. a remote key code.
FIXED_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("key"): str,
        vol.Required("value"): _SCALAR,
    }
)

VOLUME_SET_SCHEMA = vol.Schema(
    {
        vol.Required("key"): str,
        vol.Optional("min", default=0): vol.Coerce(float),
        vol.Optional("max", default=100): vol.Coerce(float),
        vol.Optional("step", default=1): vol.Coerce(float),
    }
)

VOLUME_STEP_SCHEMA = vol.Schema(
    {
        vol.Required("key"): str,
        vol.Required("up"): _SCALAR,
        vol.Required("down"): _SCALAR,
    }
)

# A selectable item (source or sound mode). "id" is what the device expects in
# the command and reports in its state, "name" is what Home Assistant shows.
# "key" overrides the command key for this item only (e.g. apps vs inputs).
ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _SCALAR,
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Optional("key"): str,
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("identifiers"): vol.All(
            vol.Any(str, [str]), lambda v: [v] if isinstance(v, str) else v
        ),
        vol.Optional("name"): str,
        vol.Optional("manufacturer"): str,
        vol.Optional("model"): str,
        vol.Optional("sw_version"): str,
        vol.Optional("hw_version"): str,
        vol.Optional("serial_number"): str,
        vol.Optional("configuration_url"): str,
    },
    extra=vol.REMOVE_EXTRA,
)

COMMANDS_SCHEMA = vol.Schema(
    {
        vol.Optional("power"): COMMAND_SCHEMA,
        vol.Optional("volume_set"): VOLUME_SET_SCHEMA,
        vol.Optional("volume_step"): VOLUME_STEP_SCHEMA,
        vol.Optional("mute"): COMMAND_SCHEMA,
        vol.Optional("source"): COMMAND_SCHEMA,
        vol.Optional("sound_mode"): COMMAND_SCHEMA,
        vol.Optional("play"): FIXED_COMMAND_SCHEMA,
        vol.Optional("pause"): FIXED_COMMAND_SCHEMA,
        vol.Optional("play_pause"): FIXED_COMMAND_SCHEMA,
        vol.Optional("stop"): FIXED_COMMAND_SCHEMA,
        vol.Optional("next"): FIXED_COMMAND_SCHEMA,
        vol.Optional("previous"): FIXED_COMMAND_SCHEMA,
    },
    extra=vol.REMOVE_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): PLATFORM_MARKER,
        vol.Required("unique_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("name"): vol.Any(str, None),
        vol.Optional("device_class"): vol.In(DEVICE_CLASSES),
        vol.Required("state_topic"): vol.All(str, vol.Length(min=1)),
        vol.Required("command_topic"): vol.All(str, vol.Length(min=1)),
        vol.Optional("availability_topic"): str,
        vol.Optional("payload_available", default="online"): str,
        vol.Optional("payload_not_available", default="offline"): str,
        vol.Optional("device", default=dict): DEVICE_SCHEMA,
        vol.Optional("commands", default=dict): COMMANDS_SCHEMA,
        vol.Optional("sources", default=list): [ITEM_SCHEMA],
        vol.Optional("sound_modes", default=list): [ITEM_SCHEMA],
    },
    extra=vol.REMOVE_EXTRA,
)


def is_ours(payload: Any) -> bool:
    """True when the payload is addressed to this integration."""
    return isinstance(payload, dict) and payload.get("platform") == PLATFORM_MARKER


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a discovery payload, raises vol.Invalid."""
    config = CONFIG_SCHEMA(payload)
    for field in ("sources", "sound_modes"):
        names = [item["name"] for item in config[field]]
        if len(names) != len(set(names)):
            raise vol.Invalid(f"duplicate names in {field}")
    return config
