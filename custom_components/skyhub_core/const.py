"""Constants for the SkyHub Core integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "skyhub_core"

CONF_HOST = "host"
CONF_TOKEN = "token"
CONF_VERIFY_SSL = "verify_ssl"

# The SSE stream carries changes as they happen. Polling stays as the
# fallback that closes the gap when the stream drops, an event is dropped
# under load, or the controller reconnects — never as the primary path.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# How long to wait before reconnecting a dropped event stream. SkyHub sends
# a keepalive every 20 s, so a silent minute means the stream is gone.
STREAM_RETRY_SECONDS = 10
STREAM_IDLE_TIMEOUT = 60

PATH_ROOF = "/api/ha/roof"
PATH_COMMAND = "/api/ha/roof/command"
PATH_EVENTS = "/api/ha/events"

MANUFACTURER = "SkyHub"
MODEL = "Observatory roof"
