"""Tests for the pure API-to-Home-Assistant mapping.

Runs with plain pytest — no Home Assistant, no network. Everything here is
about the decisions that matter operationally: is the roof shut, did an
unattended closure fail, and can an old controller be told apart from one
that closes by itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded straight from the file rather than as part of the package: the
# package __init__ pulls in Home Assistant, and the point of model.py is
# that it stands on its own.
_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "skyhub_core"
    / "model.py"
)
_spec = importlib.util.spec_from_file_location("skyhub_model", _MODEL_PATH)
model = importlib.util.module_from_spec(_spec)
sys.modules["skyhub_model"] = model  # dataclasses resolves types through it
_spec.loader.exec_module(model)

RoofState = model.RoofState
is_new_episode = model.is_new_episode
parse_roof = model.parse_roof
position_command = model.position_command


def payload(**overrides):
    base = {
        "available": True,
        "state": "closed",
        "percent": 0,
        "percentStale": False,
        "rain": False,
        "fault": "",
        "driver": "serial",
        "hardStop": False,
        "rainAuto": True,
        "closeAllowed": True,
        "closeReason": "none",
        "closePhase": "idle",
        "closeBlock": "none",
        "closeId": 0,
    }
    base.update(overrides)
    return base


def test_parses_a_full_reading():
    roof = parse_roof(payload(state="closing", percent=43, closePhase="closing", closeId=2))
    assert roof.available
    assert roof.is_closing
    assert roof.position == 43
    assert roof.close_id == 2
    assert roof.supports_rain_closure


def test_unavailable_roof_has_unknown_closed_state():
    # SkyHub answers this way when the serial link to the controller is down.
    roof = parse_roof({"available": False, "state": "unavailable", "percent": None, "rain": None})
    assert not roof.available
    assert roof.is_closed is None, "a silent controller must not read as open or shut"
    assert roof.position is None
    assert roof.rain is None


def test_unknown_state_is_not_reported_as_open():
    assert parse_roof(payload(state="unknown")).is_closed is None


def test_stale_calibration_keeps_the_position():
    # Dropping it would make the cover lose its place entirely.
    roof = parse_roof(payload(state="stopped", percent=61, percentStale=True))
    assert roof.position == 61
    assert roof.position_stale


@pytest.mark.parametrize("value", [None, -1, 101, "50", 12.5, True])
def test_implausible_position_becomes_none(value):
    assert parse_roof(payload(percent=value)).position is None


def test_old_firmware_cannot_close_by_itself():
    # Firmware 0.1.0 omits every close_* key. The absence must read as
    # "this controller only reports rain", never as a working automation.
    roof = parse_roof(
        {"available": True, "state": "open", "percent": 100, "rain": True, "fault": ""}
    )
    assert roof.rain is True
    assert not roof.supports_rain_closure
    assert not roof.rain_closure_failed
    assert roof.close_phase == ""


def test_failed_rain_closure_is_flagged():
    # The controller does not retry, so this is the state that needs a person.
    roof = parse_roof(payload(state="open", percent=100, rain=True,
                              closePhase="error", closeBlock="stop_timeout"))
    assert roof.rain_closure_failed
    assert roof.close_block == "stop_timeout"


@pytest.mark.parametrize(
    "phase,failed,active",
    [
        ("idle", False, False),
        ("pending", False, True),
        ("stopping", False, True),
        ("blocked", False, True),
        ("closing", False, True),
        ("closed", False, False),
        ("interrupted", False, False),
        ("expired", False, False),
        ("error", True, False),
    ],
)
def test_phase_classification(phase, failed, active):
    roof = parse_roof(payload(closePhase=phase))
    assert roof.rain_closure_failed is failed
    assert roof.rain_closure_active is active


def test_expired_is_not_a_failure():
    # An attempt that went stale in dry weather was correctly abandoned.
    assert not parse_roof(payload(closePhase="expired")).rain_closure_failed


def test_garbage_payload_does_not_raise():
    for junk in (None, [], "nope", 42):
        roof = parse_roof(junk)
        assert not roof.available
        assert roof.is_closed is None


def test_position_command_range():
    assert position_command(0) == "PERCENT 0"
    assert position_command(100) == "PERCENT 100"
    for bad in (-1, 101):
        with pytest.raises(ValueError):
            position_command(bad)


def test_new_episode_detection():
    idle = parse_roof(payload(closeId=0))
    first = parse_roof(payload(closeId=1))
    second = parse_roof(payload(closeId=2))
    assert not is_new_episode(None, idle), "no episode has happened yet"
    assert is_new_episode(None, first)
    assert is_new_episode(first, second)
    assert not is_new_episode(second, second)
    # close_id restarts at zero after a controller reset, so a lower number
    # is a new episode too — never proof that nothing happened.
    assert is_new_episode(second, first)


def test_roof_state_defaults_are_safe():
    roof = RoofState()
    assert not roof.available
    assert roof.is_closed is None
    assert not roof.supports_rain_closure
    assert not roof.rain_closure_failed


def test_old_firmware_does_not_claim_closing_is_disallowed():
    # Firmware 0.1.0 omits close_allowed. Defaulting it to false would read
    # as "this roof may not close", the opposite of the truth: that build
    # has no clearance gate that could fail. reports_closure lets the
    # integration leave the entity out instead of stating something false.
    roof = parse_roof(
        {"available": True, "state": "closed", "percent": 0, "rain": False}
    )
    assert not roof.reports_closure
    assert not roof.close_allowed  # the raw value stays false...
    # ...but nothing may present it, because the controller never said it.


def test_new_firmware_reports_closure_block():
    roof = parse_roof(payload(closeAllowed=True, closePhase="idle"))
    assert roof.reports_closure
    assert roof.close_allowed


def test_closure_report_survives_rain_auto_disabled():
    # A build with RAIN_AUTO_CLOSE=false still sends the close_* block, so
    # the diagnostics stay while the rain automation entities disappear.
    roof = parse_roof(payload(rainAuto=False, closeAllowed=True, closePhase="idle"))
    assert roof.reports_closure
    assert not roof.supports_rain_closure


def diag_payload(**overrides):
    base = payload()
    base.update({
        "mode": "AUTO", "motion": "STOPPED", "zone": "CLOSED", "homed": True,
        "currentMa": 20, "speedRpm": 0,
        "tempMcu": 34.6, "tempMosfet": 38.7, "tempBrake": 38.0,
        "modbusConnected": True, "commFail": False, "errFlags": "",
        "limitOpen": False, "limitClose": True, "fwVersion": "0.2.0-rain.1",
    })
    base.update(overrides)
    return base


def test_diagnostics_are_parsed():
    roof = parse_roof(diag_payload())
    assert roof.reports_diagnostics
    assert roof.mode == "AUTO"
    assert roof.current_ma == 20
    assert roof.temp_mosfet == 38.7
    assert roof.modbus_connected and not roof.comm_fail
    assert roof.limit_close and not roof.limit_open
    assert roof.fw_version == "0.2.0-rain.1"


def test_older_backend_reports_no_diagnostics():
    # A SkyHub build from before these fields existed must not produce
    # zeroed sensors that look like real measurements.
    roof = parse_roof(payload())
    assert not roof.reports_diagnostics
    assert roof.current_ma is None
    assert roof.temp_mcu is None
    assert roof.mode == ""


@pytest.mark.parametrize("value", [None, "20", True, [], {}])
def test_missing_measurement_stays_none(value):
    # Zero amps and "no reading" are the same number and opposite facts.
    roof = parse_roof(diag_payload(currentMa=value, tempMcu=value))
    assert roof.current_ma is None
    assert roof.temp_mcu is None


def test_integer_temperature_is_accepted():
    # JSON drops a trailing .0, so 38.0 can arrive as an int.
    assert parse_roof(diag_payload(tempBrake=38)).temp_brake == 38.0
