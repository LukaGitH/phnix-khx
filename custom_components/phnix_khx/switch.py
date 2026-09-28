"""Switch platform for Phnix KHX - on/off settings."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PhnixKHXDevice
from .const import DOMAIN, SWITCHES
from .modbus import ModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities for a configured heat pump."""
    device: PhnixKHXDevice = entry.runtime_data
    async_add_entities([PhnixKHXSwitch(device, spec) for spec in SWITCHES])


class PhnixKHXSwitch(CoordinatorEntity, SwitchEntity):
    """A holding register that takes one of two values.

    Note `silent_mode` uses 2/0 rather than 1/0 - that is the unit's actual
    encoding, verified live (see out/README.md).
    """

    _attr_has_entity_name = True

    def __init__(self, device: PhnixKHXDevice, spec: dict) -> None:
        super().__init__(device.coordinator)
        self._device = device
        self._spec = spec
        self._address = spec["address"]
        self._on = spec["on"]
        self._off = spec["off"]
        self._attr_unique_id = f"{device.host}_{spec['key']}"
        self._attr_name = spec["name"]
        self._attr_icon = "mdi:power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.host, device.port, device.slave)},
            "name": device.name,
            "manufacturer": "Phnix",
            "model": "KHX R290 (WarmLink 644)",
        }

    @property
    def is_on(self) -> bool | None:
        raw = self._device.raw(self._address)
        return None if raw is None else raw == self._on

    async def _write(self, value: int) -> None:
        try:
            await self._device.client.write_register(self._address, value)
        except ModbusError as err:
            _LOGGER.error("write %s=%s failed: %s", self._spec["key"], value, err)
            return
        self._device.coordinator.data[self._address] = value
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._write(self._on)

    async def async_turn_off(self, **kwargs) -> None:
        await self._write(self._off)
