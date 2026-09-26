<p align="center">
  <img src="https://raw.githubusercontent.com/grzegorz914/homeassistant-mqtt-media-player/main/custom_components/mqtt_universal_media_player/brand/logo@2x.png" alt="MQTT Media Player" width="480">
</p>

# MQTT Universal Media Player

A Home Assistant custom integration that creates **one full `media_player` entity** from a **single retained MQTT discovery message**.

The built-in MQTT integration does not support `media_player` discovery. This integration fills that gap. It supports:

* device class `tv`, `receiver`, `speaker` or `projector`
* power on / off
* volume set, volume up / down
* mute
* source selection
* sound mode selection
* play / pause / stop / next / previous
* media information (title, artist, channel, app, artwork)
* source icon or channel picon from a raw image topic
* optional screen switch and notify entity on the same device, like the built-in LG webOS TV integration

Devices do not need any new command handling. The discovery message maps each action to a command key the device already understands on its existing command topic.

## Installation

### HACS

1. HACS → three dots → **Custom repositories** → add `https://github.com/grzegorz914/homeassistant-mqtt-media-player`, category **Integration**.
2. Install **MQTT Universal Media Player** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **MQTT Universal Media Player**.

### Manual

Copy `custom_components/mqtt_universal_media_player` into your `config/custom_components` folder and restart Home Assistant.

The [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) must be set up first.

## Configuration

The only option is the **discovery prefix**, `homeassistant` by default. The integration subscribes to:

```text
<discovery_prefix>/media_player/<object_id>/config
```

Only messages containing `"platform": "mqtt_universal_media_player"` are handled. Configs published for other media player integrations on the same topic are ignored.

## Supported plugins

* [homebridge-denon-tv](https://github.com/grzegorz914/homebridge-denon-tv), class `receiver`
* [homebridge-openwebif-tv](https://github.com/grzegorz914/homebridge-openwebif-tv), class `receiver`
* [homebridge-xbox-tv](https://github.com/grzegorz914/homebridge-xbox-tv), class `receiver`
* [homebridge-lgwebos-tv](https://github.com/grzegorz914/homebridge-lgwebos-tv), class `tv`

Enable **MQTT → HA Discovery** in the plugin settings.

## Discovery message

Publish it **retained**. Publishing it again updates the entity (e.g. a new source list). Publishing an empty retained message removes the entity and its device.

```json
{
  "platform": "mqtt_universal_media_player",
  "unique_id": "denon_0005cd123456_main",
  "device_class": "receiver",
  "state_topic": "denon/Living Room/HA State",
  "command_topic": "denon/Living Room/Set",
  "availability_topic": "denon/Living Room/Availability",
  "device": {
    "identifiers": ["denon_0005cd123456_main"],
    "name": "Living Room",
    "manufacturer": "Denon",
    "model": "AVR-X2800H",
    "sw_version": "1.2.3"
  },
  "commands": {
    "power": { "key": "Power" },
    "volume_set": { "key": "Volume", "min": 0, "max": 98, "step": 1 },
    "mute": { "key": "Mute" },
    "source": { "key": "Input" },
    "sound_mode": { "key": "Surround" }
  },
  "sources": [
    { "id": "CD", "name": "CD" },
    { "id": "TV", "name": "TV Audio" }
  ],
  "sound_modes": [
    { "id": "STEREO", "name": "Stereo" },
    { "id": "MOVIE", "name": "Movie" }
  ]
}
```

| Key | Required | Description |
| --- | --- | --- |
| `platform` | yes | Must be `mqtt_universal_media_player`. |
| `unique_id` | yes | Unique entity id. |
| `state_topic` | yes | Topic with the JSON state, see below. |
| `command_topic` | yes | Commands are published here as `{"<key>": <value>}`. |
| `name` | no | Entity name. When omitted the entity uses the device name. |
| `device_class` | no | `tv`, `receiver`, `speaker` or `projector`. |
| `availability_topic` | no | When set, the entity is unavailable until `payload_available` is received. |
| `image_topic` | no | Topic with the raw image bytes (PNG, JPEG, GIF, WebP or SVG) of the current source, e.g. an app icon or a channel picon. Publish it retained when the source changes, an empty payload clears it. The image is shown in the media card. |
| `payload_available` | no | Default `online`. |
| `payload_not_available` | no | Default `offline`. |
| `device` | no | `identifiers`, `name`, `manufacturer`, `model`, `sw_version`, `hw_version`, `serial_number`, `configuration_url`. |
| `commands` | no | Action to command key mapping, see below. Actions without a mapping are not offered. |
| `sources` | no | List of `{ "id", "name", "key"? }`. `id` is sent in the command and reported in the state, `name` is shown in Home Assistant. `key` overrides the command key for this item only (e.g. apps launched with `App`, inputs with `Input`). |
| `sound_modes` | no | Same format as `sources`. |

### Commands

| Action | Format | Sent payload |
| --- | --- | --- |
| `power` | `{ "key", "toggle"? }` | `{key: true}` on, `{key: false}` off |
| `volume_set` | `{ "key", "min"?, "max"?, "step"? }` | `{key: value}` scaled from 0–1 to `min`–`max` (default 0–100), rounded to `step` |
| `volume_step` | `{ "key", "up", "down" }` | `{key: up}` / `{key: down}`, for devices that can only step the volume |
| `mute` | `{ "key", "toggle"? }` | `{key: true}` mute, `{key: false}` unmute |
| `source` | `{ "key" }` | `{key: source id}` |
| `sound_mode` | `{ "key" }` | `{key: sound mode id}` |
| `play`, `pause`, `play_pause`, `stop`, `next`, `previous` | `{ "key", "value" }` | `{key: value}`, e.g. a remote key code |
| `screen` | `{ "key" }` | Creates a `Screen` switch on the device. `{key: true}` screen on, `{key: false}` screen off while the sound keeps playing. The state is the `screen` key of the state message. |
| `notify` | `{ "key" }` | Creates a notify entity on the device (`notify.send_message`). `{key: "message"}`, a title is sent in front of the message as `title: message`. |

`"toggle": true` is for devices that flip the state on every command regardless of the value. The command is then only sent when the requested state differs from the current one.

When only `volume_set` is mapped, volume up / down steps by `step`.

The screen switch and the notify entity are unavailable while the device is off (`power: false` or `state: off`) or offline, like in the built-in LG webOS TV integration.

## State message

JSON published on `state_topic`. Every key is optional and partial updates are merged, so a device may publish only what changed.

```json
{
  "power": true,
  "state": "playing",
  "volume": 45,
  "muted": false,
  "source": "TV",
  "sound_mode": "MOVIE",
  "media_title": "News",
  "media_channel": "BBC One",
  "app_name": "Netflix",
  "media_image_url": "http://192.168.1.10/picon/bbc_one.png"
}
```

| Key | Description |
| --- | --- |
| `power` | `false` shows the entity as `off`. |
| `state` | `on`, `idle`, `playing`, `paused`, `buffering` or `off`. When omitted a powered device is `on`. |
| `volume` | In the device scale, converted with `volume_set.min` / `max` (default 0–100). |
| `muted` | Boolean. |
| `screen` | Boolean, state of the screen switch. |
| `source`, `sound_mode` | The item `id`. Unknown ids are shown as is. |
| `media_title`, `media_artist`, `media_album_name`, `media_series_title`, `media_channel`, `media_content_type`, `media_image_url`, `app_name` | Shown in the media card. |

The second line of the media card (`app_name`) shows the current source and sound mode, e.g. `TV Audio · Movie`, so they are visible without opening the selectors. When the device has neither, the `app_name` from the state is shown.

## Development

```bash
uv venv --python 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

MIT
