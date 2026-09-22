"""HTTP client for the SkyHub roof API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import aiohttp

from .const import PATH_COMMAND, PATH_EVENTS, PATH_ROOF, STREAM_IDLE_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class SkyHubError(Exception):
    """Any failure talking to SkyHub."""


class SkyHubAuthError(SkyHubError):
    """The token was rejected. Re-authentication is the only fix."""


class SkyHubCommandRejected(SkyHubError):
    """SkyHub refused the command and said why.

    A rejection is an answer, not a transport failure: the roof may be in
    the wrong mode, locked out by rain, or waiting on scope clearance. The
    message comes from SkyHub and is shown to the user as-is.
    """


class SkyHubClient:
    """Talks to one SkyHub instance with one Home Assistant token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._host = host.rstrip("/")
        self._token = token
        self._verify_ssl = verify_ssl

    @property
    def host(self) -> str:
        return self._host

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def async_get_roof(self) -> dict:
        """Read the current roof state.

        An unreachable controller is reported by SkyHub as available=false
        rather than an error, so a 200 here does not mean the roof answered.
        """
        try:
            async with self._session.get(
                f"{self._host}{PATH_ROOF}",
                headers=self._headers(),
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 401:
                    raise SkyHubAuthError("SkyHub rejected the token")
                response.raise_for_status()
                payload = await response.json()
        except SkyHubError:
            raise
        except aiohttp.ClientError as err:
            raise SkyHubError(f"cannot reach SkyHub: {err}") from err
        except asyncio.TimeoutError as err:
            raise SkyHubError("SkyHub did not answer in time") from err
        if not isinstance(payload, dict):
            raise SkyHubError("unexpected roof payload")
        return payload

    async def async_command(self, command: str) -> None:
        """Send one roof command.

        SkyHub allows OPEN, CLOSE, STOP and PERCENT 0-100 over this token.
        Everything else — homing, firmware update, motor enable — stays with
        an operator signed in to SkyHub itself, so it is refused here too.
        """
        try:
            async with self._session.post(
                f"{self._host}{PATH_COMMAND}",
                headers=self._headers(),
                json={"command": command},
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise SkyHubAuthError("SkyHub rejected the token")
                if response.status >= 400:
                    detail = (await response.text()).strip()
                    raise SkyHubCommandRejected(detail or f"HTTP {response.status}")
        except SkyHubError:
            raise
        except aiohttp.ClientError as err:
            raise SkyHubError(f"cannot reach SkyHub: {err}") from err
        except asyncio.TimeoutError as err:
            raise SkyHubError("SkyHub did not answer in time") from err

    async def async_events(self) -> AsyncIterator[str]:
        """Yield the name of each event on the SkyHub stream.

        Only the event name is yielded: the payload describes what changed
        inside SkyHub, but the authoritative roof state always comes from a
        fresh read of /api/ha/roof. Acting on the stream's own data would
        mean trusting an ordering the transport does not guarantee.

        A "dropped" event means SkyHub discarded events because this client
        could not keep up. It is yielded like any other, so the caller
        re-reads rather than assuming continuity.
        """
        async with self._session.get(
            f"{self._host}{PATH_EVENTS}",
            headers={**self._headers(), "Accept": "text/event-stream"},
            ssl=self._verify_ssl,
            timeout=aiohttp.ClientTimeout(total=None, sock_read=STREAM_IDLE_TIMEOUT),
        ) as response:
            if response.status == 401:
                raise SkyHubAuthError("SkyHub rejected the token")
            response.raise_for_status()
            event = ""
            async for raw in response.content:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith(":"):
                    continue  # keepalive
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif not line:
                    if event:
                        yield event
                    event = ""
