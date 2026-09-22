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

# While the roof is actually moving, position changes continuously and a
# half-minute tick would show a stale number for most of the travel. SkyHub
# reads the controller every 500 ms, so there is fresh data to fetch.
MOVING_SCAN_INTERVAL = timedelta(seconds=2)

# Home Assistant's default debouncer waits ten seconds between refreshes
# requested by code, which would throw away most of what the event stream
# delivers. Short enough to feel live, long enough that a burst of events
# during a movement does not become a request per event.
REQUEST_REFRESH_COOLDOWN = 1.0

# How long to wait before reconnecting a dropped event stream. SkyHub sends
# a keepalive every 20 s, so a silent minute means the stream is gone.
STREAM_RETRY_SECONDS = 10
STREAM_IDLE_TIMEOUT = 60

PATH_ROOF = "/api/ha/roof"
PATH_COMMAND = "/api/ha/roof/command"
PATH_EVENTS = "/api/ha/events"

MANUFACTURER = "SkyHub"
MODEL = "Observatory roof"

# Where the integration serves its own frontend assets: the 3D card, the
# viewer bundle and the two .glb models. A fixed path rather than one per
# config entry, because a dashboard resource URL has to stay stable.
STATIC_URL = "/skyhub_core_static"
