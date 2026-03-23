"""Platform for number entities backed by Tech menu parameters."""

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import assets
from .const import (
    CONTROLLER,
    DOMAIN,
    INCLUDE_HUB_IN_NAME,
    MANUFACTURER,
    MENU_ITEM_TYPE_UNIVERSAL_VALUE,
    MENU_ITEM_TYPE_VALUE,
    UDID,
    VALUE_FORMAT_TENTH,
)
from .coordinator import TechCoordinator

_LOGGER = logging.getLogger(__name__)

_EDITABLE_TYPES = MENU_ITEM_TYPE_VALUE | {MENU_ITEM_TYPE_UNIVERSAL_VALUE}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tech number entities from menu parameters."""
    controller = config_entry.data[CONTROLLER]
    coordinator: TechCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    controller_udid = controller[UDID]

    menus = await coordinator.api.get_module_menus(controller_udid)

    entities: list[MenuNumberEntity] = []
    for key, item in menus.items():
        item_type = item.get("type")
        if item_type not in _EDITABLE_TYPES:
            continue
        if not item.get("access", False):
            continue
        entities.append(MenuNumberEntity(item, key, coordinator, config_entry))

    async_add_entities(entities, True)


class MenuNumberEntity(CoordinatorEntity, NumberEntity):
    """A numeric menu parameter exposed as a Home Assistant number entity."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        item: dict[str, Any],
        menu_key: str,
        coordinator: TechCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialise a menu number entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._udid = config_entry.data[CONTROLLER][UDID]
        self._menu_key = menu_key
        self._item_id = item["id"]
        self._menu_type = item["menuType"]

        params = item.get("params", {})
        self._format = params.get("format", 1)

        self._attr_unique_id = f"{self._udid}_menu_{menu_key}"
        self._attr_mode = NumberMode.BOX

        if config_entry.data[INCLUDE_HUB_IN_NAME]:
            prefix = config_entry.title + " "
        else:
            prefix = ""
        txt_id = item.get("txtId", 0)
        label = assets.get_text(txt_id) if txt_id else f"Menu {self._item_id}"
        self._attr_name = prefix + label

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._udid)},
            "name": config_entry.title,
            "manufacturer": MANUFACTURER,
        }

        self._update_from_item(item)

    def _update_from_item(self, item: dict[str, Any]) -> None:
        """Refresh entity properties from a menu item payload."""
        params = item.get("params", {})
        self._format = params.get("format", 1)
        raw_value = params.get("value", 0)
        raw_min = params.get("min", 0)
        raw_max = params.get("max", 100)
        step = params.get("jump", 1)

        if self._format == VALUE_FORMAT_TENTH:
            self._attr_native_value = raw_value / 10.0
            self._attr_native_min_value = raw_min / 10.0
            self._attr_native_max_value = raw_max / 10.0
            self._attr_native_step = step / 10.0
        else:
            self._attr_native_value = float(raw_value)
            self._attr_native_min_value = float(raw_min)
            self._attr_native_max_value = float(raw_max)
            self._attr_native_step = float(step)

    async def async_set_native_value(self, value: float) -> None:
        """Set the menu parameter to the requested value."""
        if self._format == VALUE_FORMAT_TENTH:
            api_value = int(value * 10)
        else:
            api_value = int(value)

        await self.coordinator.api.set_menu_value(
            self._udid, self._menu_type, self._item_id, {"value": api_value}
        )
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        menus = self.coordinator.data.get("menus", {})
        item = menus.get(self._menu_key)
        if item:
            self._update_from_item(item)
        self.async_write_ha_state()
