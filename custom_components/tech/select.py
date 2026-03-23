"""Platform for select entities backed by Tech menu choice parameters."""

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
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
    MENU_ITEM_TYPE_CHOICE,
    UDID,
)
from .coordinator import TechCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tech select entities from menu choice parameters."""
    controller = config_entry.data[CONTROLLER]
    coordinator: TechCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    controller_udid = controller[UDID]

    menus = await coordinator.api.get_module_menus(controller_udid)

    entities: list[MenuSelectEntity] = []
    for key, item in menus.items():
        if item.get("type") not in MENU_ITEM_TYPE_CHOICE:
            continue
        if not item.get("access", False):
            continue
        options = item.get("params", {}).get("options", [])
        if not options:
            continue
        entities.append(MenuSelectEntity(item, key, coordinator, config_entry))

    async_add_entities(entities, True)


class MenuSelectEntity(CoordinatorEntity, SelectEntity):
    """A choice menu parameter exposed as a Home Assistant select entity."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        item: dict[str, Any],
        menu_key: str,
        coordinator: TechCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialise a menu select entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._udid = config_entry.data[CONTROLLER][UDID]
        self._menu_key = menu_key
        self._item_id = item["id"]
        self._menu_type = item["menuType"]

        self._attr_unique_id = f"{self._udid}_menu_{menu_key}"

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

        self._value_to_label: dict[int, str] = {}
        self._label_to_value: dict[str, int] = {}
        self._update_from_item(item)

    def _build_option_maps(self, options: list[dict[str, Any]]) -> None:
        """Build label/value mappings from the API options list."""
        self._value_to_label = {}
        self._label_to_value = {}
        ha_options: list[str] = []

        for opt in options:
            if isinstance(opt, dict):
                val = opt.get("value", 0)
                txt_id = opt.get("txtId", 0)
            else:
                continue
            label = assets.get_text(txt_id) if txt_id else str(val)
            # Ensure unique labels
            if label in self._label_to_value:
                label = f"{label} ({val})"
            self._value_to_label[val] = label
            self._label_to_value[label] = val
            ha_options.append(label)

        self._attr_options = ha_options

    def _update_from_item(self, item: dict[str, Any]) -> None:
        """Refresh entity properties from a menu item payload."""
        params = item.get("params", {})
        options = params.get("options", [])
        self._build_option_maps(options)

        current_value = params.get("value", 0)
        current_label = self._value_to_label.get(current_value)
        if current_label and current_label in self._attr_options:
            self._attr_current_option = current_label
        elif self._attr_options:
            self._attr_current_option = self._attr_options[0]
        else:
            self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = self._label_to_value.get(option)
        if value is None:
            _LOGGER.warning("Unknown option %s for menu item %s", option, self._item_id)
            return

        await self.coordinator.api.set_menu_value(
            self._udid, self._menu_type, self._item_id, {"value": value}
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
