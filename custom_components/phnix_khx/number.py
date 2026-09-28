"""Number platform for Phnix KHX - writable numeric settings."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PhnixKHXDevice
from .const import DOMAIN, NUMBERS
from .modbus import ModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities for a configured heat pump."""
    device: PhnixKHXDevice = entry.runtime_data
    async_add_entities([PhnixKHXNumber(device, spec) for spec in NUMBERS])


class PhnixKHXNumber(CoordinatorEntity, NumberEntity):
    """One writable holding register, scaled to engineering units."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, device: PhnixKHXDevice, spec: dict) -> None:
        super().__init__(device.coordinator)
        self._device = device
        self._spec = spec
        self._address = spec["address"]
        self._scale = spec["scale"]
        self._attr_unique_id = f"{device.host}_{spec['key']}"
        self._attr_name = spec["name"]
        self._attr_native_unit_of_measurement = spec["unit"]
        self._attr_native_min_value = spec["min"]
        self._attr_native_max_value = spec["max"]
        self._attr_native_step = spec["step"]
        self._attr_icon = "mdi:thermometer-cog"
        if spec["unit"] == "°C":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.host, device.port, device.slave)},
            "name": device.name,
            "manufacturer": "Phnix",
            "model": "KHX R290 (WarmLink 644)",
        }

    @property
    def native_value(self) -> float | None:
        # settings registers are two's-complement (a limit may be negative)
        return self._device.value(self._address, self._scale, signed=True)

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value / self._scale)) & 0xFFFF
        try:
            await self._device.client.write_register(self._address, raw)
        except ModbusError as err:
            _LOGGER.error("write %s=%s failed: %s", self._spec["key"], value, err)
            return
        self._device.coordinator.data[self._address] = raw
        self.async_write_ha_state()
