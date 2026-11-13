<p align="center">
  <img src="https://raw.githubusercontent.com/grzegorz914/homeassistant-mqtt-media-player/main/custom_components/mqtt_universal_media_player/brand/logo@2x.png" alt="MQTT Media Player" width="480">
</p>

# MQTT Universal Media Player

A Home Assistant custom integration that creates **one full `media_player` entity** from a **single retained MQTT discovery message**.

The built-in MQTT integration does not support `media_player` discovery. This integration fills that gap.

## What it offers

**The entity.** One `media_player` with its device in the device registry (name, manufacturer, model, software version). The device class is `tv`, `receiver`, `speaker` or `projector`. The entity is unavailable until the device reports online (`availability_topic`), unless a `mac` address is given, in which case `turn_on` wakes the device with Wake-on-LAN instead. Off, the entity is left with only power, since a powered-off device has nothing to change the volume or source of, or media to control, whether or not it would still answer. The retained discovery message can be published again at any time to update it, or emptied to remove the entity and its device.

**Controls.** Each is offered only when the discovery message maps its command, so a device shows just what it can do:

* power on / off, also for devices that flip the state on every command (`toggle`), with Wake-on-LAN for turning one on whenever its MAC address is given (`mac`), since many devices have no command of their own that reaches them while off
* volume set, volume up / down (a device that can only step the volume gets up / down without the slider) and mute
* source selection and sound mode selection, with the names shown in Home Assistant mapped to the ids the device uses, and a different command key per item, e.g. apps launched with their own key
* play, pause, stop, next and previous
* shuffle and repeat
* `media_player.play_media` and announcements (TTS) for devices that play them over the current media and return to it, with Home Assistant media sources sent as a url
* grouping, e.g. the zones of a receiver join the main zone

**What the device reports.** The state message carries power, play state, volume, mute, source, sound mode, the media information (title, artist, album, series, channel, content type, artwork, app name and id), a progress bar (position and duration) and the state of the screen. It can also take controls away while they make no sense:

* `volume_control` `step` or `none` hides the volume slider or all volume controls
* `shuffle` or `repeat` `null` hides that control, e.g. on an input with none
* `pausable` `false` hides play and pause, `stoppable` `false` hides stop, e.g. while live TV plays
* `sound_mode_list` `channels` lists the channels of the media browser in the sound mode selector instead of the sound modes

**Artwork.** An image url in the state, or the raw image bytes of the current source (an app icon, a channel picon) on `image_topic`.

**Media browser and search.** Folders from the discovery message, such as inputs, apps and channels or bouquets, with thumbnails shown whole in square tiles. The current source or channel is marked and has no play button. The browser and the search also cover Home Assistant media sources when the device plays urls. Icons the device must fetch itself can be sent through `browse_image_topic`.

**Extra entities on the same device.** An optional screen switch and a notify entity, like the built-in LG webOS TV integration.

**Choice of what is shown.** In the integration options, per device, the sources, apps and channels shown in the source list, the media browser and the search, like the built-in LG webOS TV integration. The device does not need to support it.

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

The **discovery prefix** is `homeassistant` by default. The integration subscribes to:

```text
<discovery_prefix>/media_player/<object_id>/config
```

Only messages containing `"platform": "mqtt_universal_media_player"` are handled. Configs published for other media player integrations on the same topic are ignored.

**Sources, apps and channels of a device** (Configure in the integration options), like the sources option of the built-in LG webOS TV integration: choose a device, then the sources, apps and channels shown in the source list, the media browser and the search. Nothing or everything chosen shows all, also the ones the device adds later. The choice is stored in Home Assistant, the device does not need to support it.

## Supported plugins

* [homebridge-denon-tv](https://github.com/grzegorz914/homebridge-denon-tv), class `receiver`
* [homebridge-openwebif-tv](https://github.com/grzegorz914/homebridge-openwebif-tv), class `receiver`
* [homebridge-xbox-tv](https://github.com/grzegorz914/homebridge-xbox-tv), class `receiver`
* [homebridge-lgwebos-tv](https://github.com/grzegorz914/homebridge-lgwebos-tv), class `tv`
* [Glasshouse](https://github.com/rorygallagher2024/glasshouse), the app on LG webOS TVs, class `tv`, with the Internet TV channels in the media browser and the programme on now

Enable **MQTT → HA Discovery** in the plugin settings.

## Tested with

Run against these TVs, with Home Assistant 2026.11:

| Model | webOS | Firmware |
| --- | --- | --- |
| OLED48C31LA | 11.2.0 | 44.00.92 |
| OLED48CX8LC | 5.6.2 | 04.74.00 |
| 32LM6300PLA | 4.10.2 | 05.40.97 |
| 49SK8500PLA | 4.4.3 | 05.50.70 |

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
| `availability_topic` | no | When set, the entity is unavailable until `payload_available` is received, unless `mac` is also set. |
| `mac` | no | The device's MAC address. `turn_on` always sends a Wake-on-LAN magic packet to it rather than the usual command, since a normal command needs a device already listening, which many have no way to do once powered off. Also keeps the entity available while `availability_topic` reports it unreachable. |
| `image_topic` | no | Topic with the raw image bytes (PNG, JPEG, GIF, WebP or SVG) of the current source, e.g. an app icon or a channel picon. Publish it retained when the source changes, an empty payload clears it. The image is shown in the media card. |
| `payload_available` | no | Default `online`. Also takes a list, for a device whose connection can read more than one way. |
| `payload_not_available` | no | Default `offline`. Also takes a list, e.g. a clean sleep and an unexpected disconnect reading differently. |
| `device` | no | `identifiers`, `name`, `manufacturer`, `model`, `sw_version`, `hw_version`, `serial_number`, `configuration_url`. |
| `commands` | no | Action to command key mapping, see below. Actions without a mapping are not offered. |
| `assumed_state` | no | `true` shows play, pause and stop as separate buttons in the media card (and power on / off), for devices whose play state is not always reported. Without it the frontend shows stop only for devices that cannot pause. The frontend then also shows separate power on and power off buttons. For stop with a single power button use the `media_stop` control of the Tile card playback feature instead. |
| `sources` | no | List of `{ "id", "name", "key"? }`. `id` is sent in the command and reported in the state, `name` is shown in Home Assistant. `key` overrides the command key for this item only (e.g. apps launched with `App`, inputs with `Input`). |
| `sound_modes` | no | Same format as `sources`. |
| `group` | no | `{ "id", "leader"? }`. Players with the same `id` can be grouped (`media_player.join`), e.g. the zones of one receiver. The leader (`"leader": true`, e.g. the main zone) plays, the members join it with the `join` command. |

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
| `play_media` | `{ "key", "announce"? }` | `{key: {"id": media id, "type": media type}}`, from the `media_player.play_media` action and the media browser. Home Assistant media sources are sent as a url with their mime type. Without it browser items select the source with the same id. `"announce": true` when the device plays announcements over the current media and returns to it, announcements (e.g. TTS) are then sent with `"announce": true`. |
| `shuffle` | `{ "key" }` | `{key: true}` / `{key: false}` |
| `repeat` | `{ "key" }` | `{key: "off"}`, `{key: "all"}` or `{key: "one"}` |
| `join` | `{ "key" }` | Group member only. `{key: true}` joins the leader of its group, `{key: false}` leaves it (e.g. the zone returns to its previous source). |
| `notify` | `{ "key" }` | Creates a notify entity on the device (`notify.send_message`). `{key: "message"}`, a title is sent in front of the message as `title: message`. |

`"toggle": true` is for devices that flip the state on every command regardless of the value. The command is then only sent when the requested state differs from the current one.

When only `volume_set` is mapped, volume up / down steps by `step`.

The screen switch and the notify entity are unavailable while the device is off (`power: false` or `state: off`) or offline, like in the built-in LG webOS TV integration.

### Media browser

`browse` in the discovery message adds folders to the media browser. Without it the browser shows the sources.

```json
"browse": [
  { "name": "Favourites", "type": "channel", "items": [ { "id": "1:0:1:3DCD:640:13E:820000:0:0:0:", "name": "TVP 1 HD" } ] },
  { "name": "Apps", "type": "app", "items": [ { "id": "netflix", "name": "Netflix" } ] }
]
```

| Key | Description |
| --- | --- |
| `name` | Folder name. |
| `type` | Sent as the media type with `play_media` (`channel`, `app`, `video`, `music`...). `source` (default) selects the source with the item id. |
| `items` | `id`, `name` and an optional `image` url shown as the thumbnail. |

The item whose `id` is the current `source` of the state message is marked with `●`, has no play button, and its folder is marked too. While `sound_mode_list` is `channels` the current channel of the `channel` folders is the `sound_mode`. Folders whose items have an `image` show it whole in square tiles.

Devices whose icons Home Assistant cannot load itself (self signed certificate, password, icons bundled with the device software) set `browse_image_topic` in the discovery message. The integration then sends `{"BrowseImage": {"type": ..., "id": ..., "key": ...}}` on the command topic when an icon is shown and the device answers with the image bytes (not retained) on `<browse_image_topic>/<key>`, an empty payload when the item has no icon. Answers are cached.

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
| `volume_control` | `full` (default), `step` or `none`. `step` hides the volume slider and keeps up / down (needs `volume_step`) and mute, e.g. a TV on an optical or HDMI ARC amplifier. `none` hides all volume controls, e.g. line out. |
| `media_position`, `media_duration` | Seconds, shown as a progress bar. Publish them when the media changes, Home Assistant moves the bar itself. |
| `media_position_updated_at` | Optional, epoch seconds or ISO time of `media_position`. When omitted the time the position changed is used. |
| `source`, `sound_mode` | The item `id`. Unknown ids are shown as is. |
| `shuffle` | Boolean. `null` hides the shuffle control, e.g. on a source without shuffle. |
| `repeat` | `off`, `all` or `one`. `null` hides the repeat control. |
| `pausable` | Boolean. `false` hides play and pause, e.g. on live TV that cannot be paused. |
| `stoppable` | Boolean. `false` hides stop, e.g. on live TV that has no stop. |
| `sound_mode_list` | `channels` lists the channels of the media browser (folders of type `channel`) in the sound mode selector instead of the sound modes. `sound_mode` is then the id of the current channel and `sound_mode_current` the id of the sound mode in use. Needs `play_media`. |
| `sound_mode_current` | The id of the sound mode in use. Only read while `sound_mode_list` is `channels`, for the second line of the media card. |
| `joined` | Boolean, a group member follows its leader. |
| `media_title`, `media_artist`, `media_album_name`, `media_series_title`, `media_channel`, `media_content_type`, `media_image_url`, `app_name`, `app_id` | Shown in the media card. |

The second line of the media card (`app_name`) shows the current source and sound mode, e.g. `TV Audio · Movie`, so they are visible without opening the selectors. While the channels are listed as sound modes it shows the source and `sound_mode_current` instead. When the device has neither, the `app_name` from the state is shown.

## Volume buttons next to the slider

The more-info dialog shows either the volume slider or the volume up / down buttons. For both, add a Tile card with the `Media player volume slider` and `Media player volume buttons` features (devices with a volume level, with `volume_control` `step` the dialog already shows the buttons):

```yaml
type: tile
entity: media_player.living_room_tv
features:
  - type: media-player-volume-slider
  - type: media-player-volume-buttons
```

A stop button without `assumed_state`:

```yaml
features:
  - type: media-player-playback
    controls: [power, media_previous_track, media_play_pause, media_stop, media_next_track]
```

## Development

```bash
uv venv --python 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

MIT
