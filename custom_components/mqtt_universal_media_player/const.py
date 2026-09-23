"""Constants for the MQTT Universal Media Player integration."""

DOMAIN = "mqtt_universal_media_player"

CONF_DISCOVERY_PREFIX = "discovery_prefix"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"

# Discovery payloads are only accepted when they carry this platform marker,
# so configs published for other media_player integrations are ignored.
PLATFORM_MARKER = DOMAIN

SIGNAL_DISCOVERY = f"{DOMAIN}_discovery"
