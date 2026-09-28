"""Select platform for Phnix KHX - enumerated settings."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PhnixKHXDevice
from .const import DOMAIN, SELECTS
from .modbus import ModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities for a configured heat pump."""
    device: PhnixKHXDevice = entry.runtime_data
    async_add_entities([PhnixKHXSelect(device, spec) for spec in SELECTS])


class PhnixKHXSelect(CoordinatorEntity, SelectEntity):
    """A holding register whose raw values map to named options.

    A real select platform is the main reason to prefer this integration over
    raw modbus YAML - HA's modbus integration has no native select, so the YAML
    route needs template entities calling modbus.write_register (see
    knownModbus.txt / out/ha_templates_644.yaml).
    """

    _attr_has_entity_name = True

    def __init__(self, device: PhnixKHXDevice, spec: dict) -> None:
        super().__init__(device.coordinator)
        self._device = device
        self._spec = spec
        self._address = spec["address"]
        self._options = list(spec["options"])
        self._values = list(spec["values"])
        self._attr_unique_id = f"{device.host}_{spec['key']}"
        self._attr_name = spec["name"]
        self._attr_options = self._options
        self._attr_icon = "mdi:form-list-box"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.host, device.port, device.slave)},
            "name": device.name,
            "manufacturer": "Phnix",
            "model": "KHX R290 (WarmLink 644)",
        }

    @property
    def current_option(self) -> str | None:
        raw = self._device.raw(self._address)
        if raw is None:
            return None
        try:
            return self._options[self._values.index(raw)]
        except ValueError:
            return None

    async def async_select_option(self, option: str) -> None:
        try:
            raw = self._values[self._options.index(option)]
        except ValueError:
            _LOGGER.error("%s: unknown option %r", self._spec["key"], option)
            return
        try:
            await self._device.client.write_register(self._address, raw)
        except ModbusError as err:
            _LOGGER.error("write %s=%s failed: %s", self._spec["key"], option, err)
            return
        self._device.coordinator.data[self._address] = raw
        self.async_write_ha_state()
