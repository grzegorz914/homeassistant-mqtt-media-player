"""Media player entities created from MQTT discovery messages."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import async_setup_discovered, device_info

_LOGGER = logging.getLogger(__name__)

# Device reported "state" values mapped to Home Assistant states. Anything else
# while powered on is shown as "on".
_STATES = {
    "on": MediaPlayerState.ON,
    "idle": MediaPlayerState.IDLE,
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "off": MediaPlayerState.OFF,
}

# Optional informational fields accepted in the state payload.
_MEDIA_FIELDS = (
    "media_title",
    "media_artist",
    "media_album_name",
    "media_series_title",
    "media_channel",
    "media_content_type",
    "media_image_url",
    "app_name",
)


def _image_content_type(data: bytes) -> str:
    """Detect the image type from its first bytes."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.lstrip()[:5] in (b"<?xml", b"<svg ") or data.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    return "image/png"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create an entity per discovered device, discovery is subscribed in __init__."""
    async_setup_discovered(
        hass, entry, async_add_entities, lambda config: MqttUniversalMediaPlayer(config, entry.entry_id)
    )


class MqttUniversalMediaPlayer(MediaPlayerEntity):
    """A media player fully described by a discovery message."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, config: dict[str, Any], entry_id: str) -> None:
        self._entry_id = entry_id
        self._config: dict[str, Any] = {}
        self._unsubscribe: list = []
        self._available_flag = True
        self._state: dict[str, Any] = {}
        self._image: bytes | None = None
        self._apply_config(config)
        self._attr_unique_id = config["unique_id"]

    # ----- configuration -------------------------------------------------

    def _apply_config(self, config: dict[str, Any]) -> None:
        self._config = config
        commands = config["commands"]

        self._attr_device_info = device_info(config)
        # A name in the payload overrides the device name as entity name.
        self._attr_name = config.get("name") if config.get("name") else None
        self._attr_device_class = (
            MediaPlayerDeviceClass(config["device_class"])
            if "device_class" in config
            else None
        )

        self._sources = {item["name"]: item for item in config["sources"]}
        self._source_ids = {str(item["id"]): item["name"] for item in config["sources"]}
        self._sound_modes = {item["name"]: item for item in config["sound_modes"]}
        self._sound_mode_ids = {
            str(item["id"]): item["name"] for item in config["sound_modes"]
        }
        self._attr_source_list = list(self._sources) or None
        self._attr_sound_mode_list = list(self._sound_modes) or None

        features = MediaPlayerEntityFeature(0)
        if "power" in commands:
            features |= MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if "volume_set" in commands:
            features |= MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_STEP
            vol_cfg = commands["volume_set"]
            span = vol_cfg["max"] - vol_cfg["min"]
            self._attr_volume_step = vol_cfg["step"] / span if span > 0 else 0.01
        if "volume_step" in commands:
            features |= MediaPlayerEntityFeature.VOLUME_STEP
        if "mute" in commands:
            features |= MediaPlayerEntityFeature.VOLUME_MUTE
        if "source" in commands or any("key" in s for s in config["sources"]):
            if self._sources:
                features |= MediaPlayerEntityFeature.SELECT_SOURCE
        if "sound_mode" in commands or any("key" in s for s in config["sound_modes"]):
            if self._sound_modes:
                features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
        if "play" in commands or "play_pause" in commands:
            features |= MediaPlayerEntityFeature.PLAY
        if "pause" in commands or "play_pause" in commands:
            features |= MediaPlayerEntityFeature.PAUSE
        if "stop" in commands:
            features |= MediaPlayerEntityFeature.STOP
        if "next" in commands:
            features |= MediaPlayerEntityFeature.NEXT_TRACK
        if "previous" in commands:
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        self._attr_supported_features = features

    @callback
    def async_update_discovery(self, config: dict[str, Any]) -> None:
        """A new config was published for this device."""
        topics_changed = any(
            config.get(key) != self._config.get(key)
            for key in ("state_topic", "availability_topic", "image_topic")
        )
        self._apply_config(config)
        if topics_changed and self.hass is not None:
            self.hass.async_create_task(self._async_subscribe_topics())
        if self.hass is not None:
            self._update_from_state()
            self.async_write_ha_state()

    # ----- MQTT subscriptions ---------------------------------------------

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
        if topic := self._config.get("image_topic"):
            self._unsubscribe.append(
                await mqtt.async_subscribe(
                    self.hass, topic, self._async_image_received, qos=1, encoding=None
                )
            )

    @callback
    def _async_state_received(self, msg: mqtt.ReceiveMessage) -> None:
        try:
            data = json.loads(msg.payload)
        except ValueError:
            _LOGGER.debug("Ignoring non JSON state on %s", msg.topic)
            return
        if not isinstance(data, dict):
            return
        # Partial updates are merged, so a device may publish only what changed.
        self._state.update(data)
        self._update_from_state()
        self.async_write_ha_state()

    @callback
    def _async_image_received(self, msg: mqtt.ReceiveMessage) -> None:
        # Raw image bytes of the current source, an empty payload clears it
        payload = msg.payload
        if isinstance(payload, str):
            payload = payload.encode()
        self._image = payload or None
        self.async_write_ha_state()

    @property
    def media_image_hash(self) -> str | None:
        if self._image is not None:
            return hashlib.sha256(self._image).hexdigest()[:16]
        return super().media_image_hash

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        if self._image is not None:
            return self._image, _image_content_type(self._image)
        return await super().async_get_media_image()

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
        return self._available_flag

    def _update_from_state(self) -> None:
        s = self._state
        power = s.get("power")
        reported = str(s.get("state", "")).lower()
        if power is False or reported == "off":
            self._attr_state = MediaPlayerState.OFF
        elif power is None and not reported:
            self._attr_state = None
        else:
            self._attr_state = _STATES.get(reported, MediaPlayerState.ON)

        vol_cfg = self._config["commands"].get("volume_set")
        volume = s.get("volume")
        if isinstance(volume, (int, float)) and not isinstance(volume, bool):
            vmin = vol_cfg["min"] if vol_cfg else 0
            vmax = vol_cfg["max"] if vol_cfg else 100
            span = vmax - vmin
            self._attr_volume_level = (
                min(1.0, max(0.0, (volume - vmin) / span)) if span > 0 else None
            )
        else:
            self._attr_volume_level = None

        muted = s.get("muted")
        self._attr_is_volume_muted = muted if isinstance(muted, bool) else None

        source = s.get("source")
        self._attr_source = (
            self._source_ids.get(str(source), str(source)) if source is not None else None
        )
        sound_mode = s.get("sound_mode")
        self._attr_sound_mode = (
            self._sound_mode_ids.get(str(sound_mode), str(sound_mode))
            if sound_mode is not None
            else None
        )

        for field in _MEDIA_FIELDS:
            value = s.get(field)
            setattr(self, f"_attr_{field}", value if value not in ("", None) else None)

        # The media card shows app_name as the second line, use it to show the
        # current source and sound mode without opening the selectors.
        current = " · ".join(v for v in (self._attr_source, self._attr_sound_mode) if v)
        if current:
            self._attr_app_name = current

    # ----- commands -------------------------------------------------------

    async def _async_send(self, key: str, value: Any) -> None:
        await mqtt.async_publish(
            self.hass, self._config["command_topic"], json.dumps({key: value}), qos=1
        )

    def _command(self, name: str) -> dict[str, Any]:
        cmd = self._config["commands"].get(name)
        if cmd is None:
            raise ServiceValidationError(f"{self.entity_id} does not support {name}")
        return cmd

    async def async_turn_on(self) -> None:
        cmd = self._command("power")
        if cmd["toggle"] and self.state not in (None, MediaPlayerState.OFF):
            return
        await self._async_send(cmd["key"], True)

    async def async_turn_off(self) -> None:
        cmd = self._command("power")
        if cmd["toggle"] and self.state == MediaPlayerState.OFF:
            return
        await self._async_send(cmd["key"], False)

    async def async_set_volume_level(self, volume: float) -> None:
        cmd = self._command("volume_set")
        raw = cmd["min"] + volume * (cmd["max"] - cmd["min"])
        steps = round((raw - cmd["min"]) / cmd["step"]) if cmd["step"] > 0 else raw
        value = cmd["min"] + steps * cmd["step"] if cmd["step"] > 0 else raw
        value = min(cmd["max"], max(cmd["min"], value))
        await self._async_send(cmd["key"], int(value) if float(value).is_integer() else value)

    async def async_volume_up(self) -> None:
        if cmd := self._config["commands"].get("volume_step"):
            await self._async_send(cmd["key"], cmd["up"])
            return
        await super().async_volume_up()

    async def async_volume_down(self) -> None:
        if cmd := self._config["commands"].get("volume_step"):
            await self._async_send(cmd["key"], cmd["down"])
            return
        await super().async_volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        cmd = self._command("mute")
        if cmd["toggle"] and self.is_volume_muted is not None and self.is_volume_muted == mute:
            return
        await self._async_send(cmd["key"], mute)

    async def async_select_source(self, source: str) -> None:
        await self._async_select(source, self._sources, "source")

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        await self._async_select(sound_mode, self._sound_modes, "sound_mode")

    async def _async_select(
        self, name: str, items: dict[str, dict[str, Any]], command: str
    ) -> None:
        if (item := items.get(name)) is None:
            raise ServiceValidationError(f"Unknown {command.replace('_', ' ')}: {name}")
        key = item.get("key") or self._command(command)["key"]
        await self._async_send(key, item["id"])

    async def _async_fixed(self, *names: str) -> None:
        for name in names:
            if cmd := self._config["commands"].get(name):
                await self._async_send(cmd["key"], cmd["value"])
                return
        raise ServiceValidationError(f"{self.entity_id} does not support {names[0]}")

    async def async_media_play(self) -> None:
        await self._async_fixed("play", "play_pause")

    async def async_media_pause(self) -> None:
        await self._async_fixed("pause", "play_pause")

    async def async_media_stop(self) -> None:
        await self._async_fixed("stop")

    async def async_media_next_track(self) -> None:
        await self._async_fixed("next")

    async def async_media_previous_track(self) -> None:
        await self._async_fixed("previous")
