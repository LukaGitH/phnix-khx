"""Phnix KHX heat pump integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    NUMBERS,
    SELECTS,
    SENSORS,
    SWITCHES,
)
from .modbus import ModbusClient, ModbusError

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH, Platform.SELECT]

_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SLAVE, default=DEFAULT_SLAVE): cv.positive_int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [_DEVICE_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)


class PhnixKHXDevice:
    """Runtime objects shared by the entities for one heat pump."""

    def __init__(self, name: str, host: str, port: int, slave: int,
                 client: ModbusClient,
                 coordinator: DataUpdateCoordinator[dict[int, int]]) -> None:
        self.name = name
        self.host = host
        self.port = port
        self.slave = slave
        self.client = client
        self.coordinator = coordinator

    def raw(self, address: int) -> int | None:
        """Return a raw register value."""
        return self.coordinator.data.get(address)

    def value(self, address: int, scale: float = 1.0,
              signed: bool = False) -> float | None:
        """Return a scaled register value."""
        from .modbus import signed16

        raw = self.coordinator.data.get(address)
        if raw is None:
            return None
        return (signed16(raw) if signed else raw) * scale


def all_addresses() -> list[int]:
    """Return all registers used by this integration."""
    return sorted({item["address"] for item in SENSORS + NUMBERS + SWITCHES + SELECTS})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import any legacy YAML entries into the UI-managed config-entry system."""
    for device_config in config.get(DOMAIN, []):
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=device_config,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured heat pump."""
    entry_values = {**entry.data, **entry.options}
    values = {
        CONF_NAME: entry.title or DEFAULT_NAME,
        CONF_HOST: entry_values[CONF_HOST],
        CONF_PORT: entry_values.get(CONF_PORT, DEFAULT_PORT),
        CONF_SLAVE: entry_values.get(CONF_SLAVE, DEFAULT_SLAVE),
        CONF_SCAN_INTERVAL: entry_values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    }
    client = ModbusClient(
        host=values[CONF_HOST],
        port=values[CONF_PORT],
        unit=values[CONF_SLAVE],
    )

    async def _update() -> dict[int, int]:
        try:
            return await client.read_registers(all_addresses())
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err

    coordinator: DataUpdateCoordinator[dict[int, int]] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"phnix_khx_{values[CONF_NAME]}",
        update_method=_update,
        update_interval=timedelta(seconds=values[CONF_SCAN_INTERVAL]),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ModbusError, UpdateFailed) as err:
        raise ConfigEntryNotReady(f"Unable to read registers from {values[CONF_HOST]}") from err

    device = PhnixKHXDevice(
        name=values[CONF_NAME],
        host=values[CONF_HOST],
        port=values[CONF_PORT],
        slave=values[CONF_SLAVE],
        client=client,
        coordinator=coordinator,
    )
    entry.runtime_data = device
    _LOGGER.info(
        "Phnix KHX %s (%s) ready: %d/%d registers readable",
        device.name, device.host, len(coordinator.data), len(all_addresses()),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and its platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
