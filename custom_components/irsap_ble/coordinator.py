"""Polling coordinator for an IRSAP radiator."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .protocol import RadiatorState
from .radiator import IrsapError, IrsapRadiator

_LOGGER = logging.getLogger(__name__)

MAX_TOLERATED_FAILURES = 3  # keep the last known state for a few failed polls (e.g. phone app connected)


class IrsapCoordinator(DataUpdateCoordinator[RadiatorState]):
    """Reads the radiator state at a fixed interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, radiator: IrsapRadiator) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {radiator.address}",
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.radiator = radiator
        self._failures = 0
        self.polls_ok = 0       # statistics for the stability test, exposed as climate attributes
        self.polls_failed = 0
        self.last_success: datetime | None = None

    async def _async_update_data(self) -> RadiatorState:
        try:
            state = await self.radiator.async_read_state()
        except IrsapError as err:
            self._failures += 1
            self.polls_failed += 1
            if self.data is not None and self._failures < MAX_TOLERATED_FAILURES:
                _LOGGER.debug("Poll failed (%s), keeping the last known state", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        self._failures = 0
        self.polls_ok += 1
        self.last_success = datetime.now().astimezone()
        return state
