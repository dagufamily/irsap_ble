"""Climate entity for an IRSAP radiator."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP, DOMAIN, MAX_TEMP, MIN_TEMP
from .coordinator import IrsapCoordinator
from .protocol import CMD_MANUAL, CMD_OFF, CMD_PROGRAM, build_command
from .radiator import IrsapError

REFRESH_DELAY = 3  # seconds to let the radiator close the connection before reading it back


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the climate entity of a config entry."""
    async_add_entities([IrsapClimate(entry.runtime_data, entry)])


class IrsapClimate(CoordinatorEntity[IrsapCoordinator], ClimateEntity):
    """An IRSAP electric radiator."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: IrsapCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        address = coordinator.radiator.address
        self._attr_unique_id = address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=entry.title,
            manufacturer="IRSAP",
            model="Electric radiator (BLE)",
        )

    @property
    def available(self) -> bool:
        # Unavailable until the first successful read (the first read runs in the background)
        return super().available and self.coordinator.data is not None

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self.coordinator.data is None:
            return None
        return HVACMode.HEAT if self.coordinator.data.is_on else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        return None if self.coordinator.data is None else self.coordinator.data.current_temp

    @property
    def target_temperature(self) -> float | None:
        return None if self.coordinator.data is None else self.coordinator.data.target_temp

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        state = self.coordinator.data
        if state is None:
            return None
        attrs: dict[str, Any] = {
            "control_mode": state.mode,
            "polls_ok": self.coordinator.polls_ok,
            "polls_failed": self.coordinator.polls_failed,
        }
        if self.coordinator.last_success is not None:
            attrs["last_success"] = self.coordinator.last_success.isoformat()
        if state.expiry is not None:
            # program: next program change; manual with a timer: end of the timer
            attrs["until"] = state.expiry.isoformat()
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._async_command(CMD_OFF)
        elif hvac_mode == HVACMode.HEAT:
            comfort = self._entry.options.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
            await self._async_command(CMD_PROGRAM, comfort=comfort)
        else:
            raise HomeAssistantError(f"Unsupported HVAC mode {hvac_mode}")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if kwargs.get("hvac_mode") == HVACMode.OFF:
            await self._async_command(CMD_OFF)
            return
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self._async_command(CMD_MANUAL, temp=float(temperature))

    async def _async_command(self, command: int, **params: float) -> None:
        announce, blob = build_command(command, **params)
        try:
            await self.coordinator.radiator.async_send(announce, blob)
        except IrsapError as err:
            raise HomeAssistantError(str(err)) from err
        await asyncio.sleep(REFRESH_DELAY)
        await self.coordinator.async_refresh()
