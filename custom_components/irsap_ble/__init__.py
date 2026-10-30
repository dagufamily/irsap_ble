"""IRSAP BLE radiator integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import IrsapCoordinator
from .radiator import IrsapRadiator

PLATFORMS = [Platform.CLIMATE]

type IrsapConfigEntry = ConfigEntry[IrsapCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: IrsapConfigEntry) -> bool:
    """Set up one radiator from a config entry."""
    radiator = IrsapRadiator(hass, entry.data[CONF_ADDRESS], entry.title)
    coordinator = IrsapCoordinator(hass, entry, radiator)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    # The first read can take a while (the radiator is slow to connect), so it must not block the setup:
    # the config flow waits for the setup, and would time out ("Unknown error"). The entity stays
    # unavailable until the first read succeeds.
    entry.async_create_background_task(hass, coordinator.async_refresh(), f"{DOMAIN} first refresh")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrsapConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: IrsapConfigEntry) -> None:
    """Reload when the options change (poll interval, Comfort preset)."""
    await hass.config_entries.async_reload(entry.entry_id)
