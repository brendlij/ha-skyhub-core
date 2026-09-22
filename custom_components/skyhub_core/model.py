"""Pure translation between the SkyHub roof API and Home Assistant.

Nothing here imports Home Assistant or aiohttp, so the mapping that decides
whether a roof counts as closed — or whether an unattended rain closure
failed — can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# close_phase values reported by controller firmware >= 0.2.0-rain.1.
PHASE_IDLE = "idle"
PHASE_PENDING = "pending"
PHASE_STOPPING = "stopping"
PHASE_BLOCKED = "blocked"
PHASE_CLOSING = "closing"
PHASE_CLOSED = "closed"
PHASE_INTERRUPTED = "interrupted"
PHASE_EXPIRED = "expired"
PHASE_ERROR = "error"

# A rain closure that ended in error left the roof wherever it was, and the
# controller will not retry until it has been dry for the re-arm interval and
# rains again. That is the one state a person has to act on.
PHASES_FAILED = frozenset({PHASE_ERROR})

# Movement was cut short. Not an unattended failure, but not a finished
# closure either — worth surfacing, not worth alarming about.
PHASES_INCOMPLETE = frozenset({PHASE_INTERRUPTED, PHASE_BLOCKED})


@dataclass(frozen=True)
class RoofState:
    """One reading of /api/ha/roof."""

    available: bool = False
    state: str = "unavailable"
    position: int | None = None
    position_stale: bool = False
    rain: bool | None = None
    fault: str = ""
    driver: str = ""
    hard_stop: bool = False
    rain_auto: bool = False
    close_allowed: bool = False
    close_reason: str = ""
    close_phase: str = ""
    close_block: str = ""
    close_id: int = 0
    # Whether the controller reported the close_* block at all. Absent on
    # firmware before 0.2.0-rain.1, where close_allowed defaulting to false
    # would otherwise read as "this roof may not close" — the opposite of
    # the truth, since that firmware has no clearance gate to fail.
    reports_closure: bool = False

    # Operating mode and drive health. Added to SkyHub later than the rest,
    # so an older backend leaves them empty rather than reporting a zero
    # that would look like a real reading.
    mode: str = ""
    motion: str = ""
    zone: str = ""
    homed: bool = False
    current_ma: int | None = None
    speed_rpm: int | None = None
    temp_mcu: float | None = None
    temp_mosfet: float | None = None
    temp_brake: float | None = None
    modbus_connected: bool = False
    comm_fail: bool = False
    err_flags: str = ""
    limit_open: bool = False
    limit_close: bool = False
    fw_version: str = ""
    reports_diagnostics: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_closed(self) -> bool | None:
        """None means unknown, which Home Assistant renders as such."""
        if not self.available or self.state in ("unknown", "unavailable"):
            return None
        return self.state == "closed"

    @property
    def is_opening(self) -> bool:
        return self.state == "opening"

    @property
    def is_closing(self) -> bool:
        return self.state == "closing"

    @property
    def rain_closure_failed(self) -> bool:
        """True when an autonomous rain closure gave up.

        The controller does not retry on its own, so this stays true until a
        new episode starts. It is the condition that warrants a notification
        rather than a dashboard tile: the roof may be open in the rain.
        """
        return self.close_phase in PHASES_FAILED

    @property
    def rain_closure_active(self) -> bool:
        return self.close_phase in (
            PHASE_PENDING,
            PHASE_STOPPING,
            PHASE_CLOSING,
            PHASE_BLOCKED,
        )

    @property
    def supports_rain_closure(self) -> bool:
        """False on firmware that only reports rain without acting on it.

        Older firmware omits the close_* keys entirely, so this reads as
        'this controller cannot close by itself' — the safe assumption.
        """
        return self.rain_auto


def _as_int(value: Any) -> int:
    """Ints only — bool is a subclass of int and must not slip through."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _opt_int(value: Any) -> int | None:
    """None for anything that is not a real integer reading.

    A missing reading has to stay missing: zero amps and "no measurement"
    look identical as a number and mean opposite things when you are
    watching for a drive that is straining.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_roof(payload: Any) -> RoofState:
    """Build a RoofState from the API payload, tolerating a partial one.

    An unreachable controller answers with available=false and null fields
    rather than an error, so a missing key is normal and never raises.
    """
    if not isinstance(payload, dict):
        return RoofState(raw={})

    # bool is a subclass of int, so a stray true would otherwise arrive as
    # position 1 — a roof reported as very nearly shut.
    position = payload.get("percent")
    if isinstance(position, bool) or not isinstance(position, int):
        position = None
    elif not 0 <= position <= 100:
        position = None

    rain = payload.get("rain")
    if not isinstance(rain, bool):
        rain = None

    return RoofState(
        available=payload.get("available") is True,
        state=str(payload.get("state") or "unknown"),
        position=position,
        position_stale=payload.get("percentStale") is True,
        rain=rain,
        fault=str(payload.get("fault") or ""),
        driver=str(payload.get("driver") or ""),
        hard_stop=payload.get("hardStop") is True,
        rain_auto=payload.get("rainAuto") is True,
        close_allowed=payload.get("closeAllowed") is True,
        close_reason=str(payload.get("closeReason") or ""),
        close_phase=str(payload.get("closePhase") or ""),
        close_block=str(payload.get("closeBlock") or ""),
        close_id=_as_int(payload.get("closeId")),
        reports_closure="closePhase" in payload or "closeAllowed" in payload,
        mode=str(payload.get("mode") or ""),
        motion=str(payload.get("motion") or ""),
        zone=str(payload.get("zone") or ""),
        homed=payload.get("homed") is True,
        current_ma=_opt_int(payload.get("currentMa")),
        speed_rpm=_opt_int(payload.get("speedRpm")),
        temp_mcu=_opt_float(payload.get("tempMcu")),
        temp_mosfet=_opt_float(payload.get("tempMosfet")),
        temp_brake=_opt_float(payload.get("tempBrake")),
        modbus_connected=payload.get("modbusConnected") is True,
        comm_fail=payload.get("commFail") is True,
        err_flags=str(payload.get("errFlags") or ""),
        limit_open=payload.get("limitOpen") is True,
        limit_close=payload.get("limitClose") is True,
        fw_version=str(payload.get("fwVersion") or ""),
        reports_diagnostics="mode" in payload or "currentMa" in payload,
        raw=payload,
    )


def position_command(position: int) -> str:
    """Home Assistant and SkyHub agree: 0 is closed, 100 is fully open."""
    if not 0 <= position <= 100:
        raise ValueError(f"position {position} out of range")
    return f"PERCENT {position}"


def is_new_episode(previous: RoofState | None, current: RoofState) -> bool:
    """Whether current begins a rain episode that previous did not show.

    close_id counts episodes since the controller booted. It is neither
    globally unique nor persisted, so a reset restarts it at zero and a
    rising number alone proves nothing — a drop means the controller
    rebooted, which starts a new episode just as much as an increase does.
    """
    if current.close_id == 0:
        return False
    if previous is None:
        return True
    return current.close_id != previous.close_id
