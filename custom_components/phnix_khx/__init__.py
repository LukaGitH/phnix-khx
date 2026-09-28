"""Phnix KHX heat pump - local Modbus integration.

Configure in configuration.yaml:

    phnix_khx:
      - name: Phnix KHX
        host: 192.168.0.194
        port: 502
        slave: 1
        scan_interval: 10

Reads and writes the KHX holding registers directly. Runs alongside (not instead
of) an existing `modbus:` block - useful for comparing both, or for migrating off
raw modbus entities onto a real device with number/switch/select platforms.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
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

CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"

PLATFORMS = ["sensor", "number", "switch", "select"]

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SLAVE, default=DEFAULT_SLAVE): cv.positive_int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [DEVICE_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)


class PhnixKHXDevice:
    """Runtime objects for one configured heat pump."""

    def __init__(self, name: str, host: str, port: int, slave: int,
                 client: ModbusClient,
                 coordinator: "DataUpdateCoordinator[dict[int, int]]") -> None:
        self.name = name
        self.host = host
        self.port = port
        self.slave = slave
        self.client = client
        self.coordinator = coordinator

    # ---- convenience accessors used by every platform ---------------------
    def raw(self, address: int) -> int | None:
        return self.coordinator.data.get(address)

    def value(self, address: int, scale: float = 1.0,
              signed: bool = False) -> float | None:
        from .modbus import signed16
        raw = self.coordinator.data.get(address)
        if raw is None:
            return None
        return (signed16(raw) if signed else raw) * scale


def all_addresses() -> list[int]:
    """Every register any entity needs - polled in one pass."""
    return sorted({i["address"] for i in SENSORS + NUMBERS + SWITCHES + SELECTS})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up one or more Phnix KHX heat pumps from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})

    for conf in config[DOMAIN]:
        name = conf[CONF_NAME]
        client = ModbusClient(
            host=conf[CONF_HOST],
            port=conf[CONF_PORT],
            unit=conf[CONF_SLAVE],
        )
        addresses = all_addresses()

        async def _update(client=client, addresses=addresses) -> dict[int, int]:
            try:
                return await client.read_registers(addresses)
            except ModbusError as err:
                raise UpdateFailed(str(err)) from err

        coordinator: DataUpdateCoordinator[dict[int, int]] = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"phnix_khx_{name}",
            update_method=_update,
            update_interval=timedelta(seconds=conf[CONF_SCAN_INTERVAL]),
        )
        await coordinator.async_refresh()

        hass.data[DOMAIN][name] = PhnixKHXDevice(
            name=name,
            host=conf[CONF_HOST],
            port=conf[CONF_PORT],
            slave=conf[CONF_SLAVE],
            client=client,
            coordinator=coordinator,
        )
        _LOGGER.info(
            "Phnix KHX %s (%s) ready: %d/%d registers readable",
            name, conf[CONF_HOST], len(coordinator.data), len(addresses),
        )

        for platform in PLATFORMS:
            hass.async_create_task(
                async_load_platform(hass, platform, DOMAIN, {"name": name}, config)
            )
    return True
