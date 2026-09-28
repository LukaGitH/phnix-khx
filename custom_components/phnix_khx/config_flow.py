"""Config flow for Phnix KHX heat pumps."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
)
from .modbus import ModbusClient, ModbusError


def _schema(defaults: dict | None = None) -> vol.Schema:
    """Build the connection form schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): cv.string,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): cv.string,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): cv.port,
            vol.Required(
                CONF_SLAVE,
                default=defaults.get(CONF_SLAVE, DEFAULT_SLAVE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=247,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(cv.positive_int, vol.Range(min=1, max=3600)),
        }
    )


async def _test_connection(hass: HomeAssistant, data: dict) -> bool:
    """Check connectivity with a read-only request before creating the entry."""
    client = ModbusClient(data[CONF_HOST], data[CONF_PORT], data[CONF_SLAVE])
    try:
        await client.read_register(1012, repeats=1)
    except ModbusError:
        return False
    return True


class PhnixKHXConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup from the Home Assistant UI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> dict:
        """Ask for the name and Modbus TCP connection details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            if not float(user_input[CONF_SLAVE]).is_integer():
                errors[CONF_SLAVE] = "invalid_slave"
            else:
                user_input[CONF_SLAVE] = int(user_input[CONF_SLAVE])
            if not errors and await _test_connection(self.hass, user_input):
                unique_id = (
                    f"{user_input[CONF_HOST].lower()}:"
                    f"{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.pop(CONF_NAME),
                    data=user_input,
                )
            if not errors:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_import(self, import_config: dict) -> dict:
        """Create an entry from an existing YAML configuration."""
        host = import_config[CONF_HOST].strip()
        port = import_config.get(CONF_PORT, DEFAULT_PORT)
        slave = import_config.get(CONF_SLAVE, DEFAULT_SLAVE)
        await self.async_set_unique_id(f"{host.lower()}:{port}:{slave}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_config.get(CONF_NAME, DEFAULT_NAME),
            data={
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_SLAVE: slave,
                CONF_SCAN_INTERVAL: import_config.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow for an existing entry."""
        return PhnixKHXOptionsFlow()


class PhnixKHXOptionsFlow(OptionsFlowWithReload):
    """Allow changing the polling interval from the integration page."""

    async def async_step_init(self, user_input: dict | None = None) -> dict:
        """Set the polling interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        cv.positive_int, vol.Range(min=1, max=3600)
                    )
                }
            ),
        )
