# SkyHub Core — Home Assistant integration

Brings the observatory roof into Home Assistant: open, close, stop, drive to a
position, and see what the roof controller is doing — including a rain closure
it carried out on its own.

Companion integration for [skyhub-core](https://github.com/brendlij/skyhub-core),
which is a private repository. Install this through HACS as a custom repository.

## What it creates

One device with:

| Entity | Type | Notes |
| --- | --- | --- |
| Roof | `cover` | open / close / stop / set position, `shutter` class |
| Rain | `binary_sensor` | `moisture`, straight from the controller's sensor |
| Controller fault | `binary_sensor` | `problem`, latched — nothing moves until it is cleared |
| Hardware hard stop | `binary_sensor` | `problem`, latched by the controller itself |
| Rain closure failed | `binary_sensor` | `problem` — **see below** |
| Rain closure running | `binary_sensor` | an autonomous closure is under way |
| Closing allowed | `binary_sensor` | scope clearance, diagnostic |
| Position uncalibrated | `binary_sensor` | position is shown but not trustworthy |
| Rain closure phase / blocked by / last reason | `sensor` | diagnostic |
| Roof driver | `sensor` | diagnostic |

The rain closure entities only appear when the controller reports that it can
close by itself. Firmware 0.1.0 reports rain without acting on it, and the
integration will not pretend otherwise.

## The one alarm worth wiring up

`binary_sensor.rain_closure_failed` turns on when the controller started an
autonomous rain closure and gave up — for example because the drive never
confirmed a standstill within the timeout.

**The controller does not retry.** A new attempt is armed only after a
sustained dry interval followed by fresh rain. Until then the roof stays where
it is, possibly open in the rain, waiting for a person.

Treat this as a notification, not a dashboard tile:

```yaml
automation:
  - alias: Observatory roof failed to close
    triggers:
      - trigger: state
        entity_id: binary_sensor.skyhub_rain_closure_failed
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: Roof did not close
          message: >-
            Rain closure failed
            ({{ state_attr('binary_sensor.skyhub_rain_closure_failed',
            'close_block') }}). The roof may be open in the rain.
          data:
            priority: high
```

## Rain while the scope is not clear

Only relevant once the controller's scope clearance pin is wired — it is
disabled by default, and a roof that clears the telescope at any orientation
does not need it.

With it enabled, a rain closure that finds the scope in the way parks itself and
waits rather than driving into it. `sensor.*_rain_closure_blocked_by` reads
`scope_not_safe`. Normally NINA resolves this on its own: SkyHub publishes rain
through its Alpaca SafetyMonitor, NINA aborts the sequence and parks the mount,
and the controller — still holding the pending attempt — closes by itself.

When nothing parks the scope, the roof stays open in the rain by design. Alert
on the combination rather than waiting for the closure to fail:

```yaml
automation:
  - alias: Rain while the scope is not clear
    triggers:
      - trigger: state
        entity_id: sensor.skyhub_rain_closure_blocked_by
        to: scope_not_safe
        for: "00:00:30"
    conditions:
      - condition: state
        entity_id: binary_sensor.skyhub_rain
        state: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: Roof cannot close
          message: >-
            It is raining and the telescope is not clear of the roof. Park the
            mount, or close the roof by hand.
          data:
            priority: high
```

Cutting power to the mount does not help: an unpowered mount stops where it
stands, still in the way and no longer able to park.

## After a firmware update

Flashing the controller resets it, which reboots the motor driver and marks
the position as uncalibrated. Expect all of this, none of it is a fault:

- a brief unavailable window while the controller reboots
- `binary_sensor.*_hard_stop` on for a few seconds — the watchdog relay drops
  on boot and is only released once Modbus is proven healthy
- `binary_sensor.*_position_uncalibrated` on, and the cover's position slider
  greyed out. Open, close and stop still work: they drive onto physical end
  stops. A percentage move aims at a counter the controller no longer
  vouches for, so it is withheld until a homing run re-measures the range
- possibly a latched fault to clear, if the drive was unreachable during the
  reset window

Reload the integration afterwards. Entities are created at setup, so ones
that only exist on the newer firmware — the rain closure sensors — will not
appear until the config entry is reloaded.

## Setup

1. In SkyHub, generate a Home Assistant token (it is shown once).
2. In Home Assistant: **Settings → Devices & services → Add integration → SkyHub Core**.
3. Enter the address (`skyhub-core:11111` or `http://192.168.178.108:11111`) and the token.

Rotating the token in SkyHub revokes the old one; Home Assistant then asks you
to re-authenticate.

## How it stays current

Updates arrive over SkyHub's server-sent event stream, so a movement shows up
within one round trip rather than on the next poll. Polling every 30 s remains
as the fallback for a dropped stream, a dropped event, or a controller
reconnect — the stream is a speed-up, never the only path.

The roof state always comes from a fresh read of `/api/ha/roof`. The stream is
used as a signal that something changed, never as the data itself.

## What it deliberately cannot do

The token allows `OPEN`, `CLOSE`, `STOP` and `PERCENT 0-100`. Homing, firmware
updates, motor enable and fault reset stay with an operator signed in to SkyHub.
That limit is enforced on the SkyHub side as well.

## Development

```bash
python -m pytest tests/ -q
```

`custom_components/skyhub_core/model.py` holds the API-to-Home-Assistant
mapping and imports neither Home Assistant nor aiohttp, so the decisions that
matter — is the roof shut, did an unattended closure fail — are testable on
their own.
