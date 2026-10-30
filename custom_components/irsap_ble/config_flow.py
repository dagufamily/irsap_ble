"""Config flow: scan for IRSAP radiators, pick the ones to add, give each a name."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COMFORT_TEMP,
    CONF_DEVICES,
    CONF_LOCAL_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NAME_PREFIX,
)

SOURCE_BATCH = "batch"  # internal source used to create the entries of the other selected radiators


def _default_name(local_name: str) -> str:
    """'IRSAP_RS_HHATQYN' -> 'IRSAP HHATQYN'."""
    return f"IRSAP {local_name.removeprefix(NAME_PREFIX)}"


class IrsapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, str] = {}      # address -> advertised name
        self._queue: list[str] = []           # addresses still to be named
        self._names: dict[str, str] = {}      # address -> chosen name
        self._address: str | None = None      # single device (Bluetooth discovery)
        self._local_name: str = ""

    # ---- automatic discovery (Home Assistant "Discovered" card) ----
    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._local_name = discovery_info.name
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name a single discovered radiator."""
        assert self._address is not None
        if user_input is not None:
            # A double click on Submit must not create the same radiator twice
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_ADDRESS: self._address, CONF_LOCAL_NAME: self._local_name},
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=_default_name(self._local_name)): str}),
            description_placeholders={"device": f"{self._local_name} ({self._address})"},
        )

    # ---- manual setup: scan and pick several radiators ----
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        configured = self._async_current_ids()
        self._found = {
            info.address: info.name
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.name and info.name.startswith(NAME_PREFIX) and info.address not in configured
        }
        if not self._found:
            return self.async_abort(reason="no_devices_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = [a for a in user_input[CONF_DEVICES] if a in self._found]
            if selected:
                self._queue = selected
                return await self.async_step_name()
            errors["base"] = "none_selected"

        options = [
            selector.SelectOptionDict(value=address, label=f"{name} ({address})")
            for address, name in sorted(self._found.items(), key=lambda item: item[1])
        ]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICES, default=[o["value"] for o in options]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_name(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask a name for each selected radiator, one after the other."""
        address = self._queue[0]
        local_name = self._found[address]
        if user_input is not None:
            self._names[address] = user_input[CONF_NAME]
            self._queue.pop(0)
            if self._queue:
                return await self.async_step_name()
            return await self._async_create_all()
        return self.async_show_form(
            step_id="name",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=_default_name(local_name)): str}),
            description_placeholders={"device": f"{local_name} ({address})"},
        )

    async def _async_create_all(self) -> ConfigFlowResult:
        """Create the entry of the first radiator here and start one flow for each of the others."""
        items = list(self._names.items())
        for address, name in items[1:]:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_BATCH},
                    data={CONF_ADDRESS: address, CONF_NAME: name, CONF_LOCAL_NAME: self._found[address]},
                )
            )
        address, name = items[0]
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=name, data={CONF_ADDRESS: address, CONF_LOCAL_NAME: self._found[address]}
        )

    async def async_step_batch(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create an entry without asking anything (started by the multi-select flow)."""
        await self.async_set_unique_id(data[CONF_ADDRESS])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=data[CONF_NAME],
            data={CONF_ADDRESS: data[CONF_ADDRESS], CONF_LOCAL_NAME: data[CONF_LOCAL_NAME]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrsapOptionsFlow()


class IrsapOptionsFlow(OptionsFlow):
    """Options: Comfort preset used by 'heat', polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COMFORT_TEMP, default=options.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=15, max=30, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=60, max=3600, step=30, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )
