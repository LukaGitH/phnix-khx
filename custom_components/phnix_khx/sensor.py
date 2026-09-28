"""Sensor platform for Phnix KHX - read-only telemetry, state and bitfields."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PhnixKHXDevice
from .const import DOMAIN, SENSORS

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities for a configured heat pump."""
    device: PhnixKHXDevice = entry.runtime_data
    async_add_entities([PhnixKHXSensor(device, spec) for spec in SENSORS])


class PhnixKHXSensor(CoordinatorEntity, SensorEntity):
    """One read-only holding register."""

    _attr_has_entity_name = True

    def __init__(self, device: PhnixKHXDevice, spec: dict) -> None:
        super().__init__(device.coordinator)
        self._device = device
        self._address = spec["address"]
        self._scale = spec["scale"]
        self._signed = spec["signed"]
        self._attr_unique_id = f"{device.host}_{spec['key']}"
        self._attr_name = spec["name"]
        self._attr_native_unit_of_measurement = spec["unit"]
        self._attr_suggested_display_precision = spec["precision"]
        if spec["device_class"]:
            self._attr_device_class = _DEVICE_CLASS.get(spec["device_class"])
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.host, device.port, device.slave)},
            "name": device.name,
            "manufacturer": "Phnix",
            "model": "KHX R290 (WarmLink 644)",
        }

    @property
    def native_value(self) -> float | None:
        return self._device.value(self._address, self._scale, self._signed)
