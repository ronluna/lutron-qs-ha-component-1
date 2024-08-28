"""Support for Lutron events."""

from enum import StrEnum

from pylutron import Button, Keypad, Lutron, LutronEvent

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import ATTR_ACTION, ATTR_FULL_ID, ATTR_UUID, DOMAIN, LutronData
from .entity import LutronKeypad


class LutronEventType(StrEnum):
    """Lutron event types."""

    SINGLE_PRESS = "single_press"
    PRESS = "press"
    RELEASE = "release"
    HOLD = "hold"
    DOUBLE_TAP = "double_tap"
    HOLD_RELEASE = "hold_release"


LEGACY_EVENT_TYPES: dict[LutronEventType, str] = {
    LutronEventType.SINGLE_PRESS: "single",
    LutronEventType.PRESS: "press",
    LutronEventType.RELEASE: "release",
    LutronEventType.HOLD: "hold",
    LutronEventType.DOUBLE_TAP: "double_tap",
    LutronEventType.HOLD_RELEASE: "hold_release",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Lutron event platform."""
    entry_data: LutronData = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        LutronEventEntity(area_name, device_name, keypad, button, entry_data.client)
        for area_name, device_name, keypad, button in entry_data.buttons
    )


class LutronEventEntity(LutronKeypad, EventEntity):
    """Representation of a Lutron keypad button."""

    _attr_translation_key = "button"

    def __init__(
        self,
        area_name: str,
        device_name: str,
        keypad: Keypad,
        button: Button,
        controller: Lutron,
    ) -> None:
        """Initialize the button."""
        super().__init__(area_name, device_name, button, controller, keypad)
        if (name := button.name) == "Unknown Button":
            name += f" {button.number}"
        self._attr_name = name
        self._has_release_event = (
            button.button_type is not None
            and button.button_type in ("RaiseLower", "DualAction")
        )
        self._attr_event_types = [
            LutronEventType.PRESS,
            LutronEventType.RELEASE,
            LutronEventType.HOLD,
            LutronEventType.HOLD_RELEASE,
            LutronEventType.DOUBLE_TAP,
        ]

        self._full_id = slugify(f"{area_name} {keypad.name}: {name}")
        self._id = slugify(f"{keypad.name}: {name}")

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        self._lutron_device.subscribe(self.handle_event, None)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        await super().async_will_remove_from_hass()
        # Temporary solution until https://github.com/thecynic/pylutron/pull/93 gets merged
        self._lutron_device._subscribers.remove((self.handle_event, None))  # pylint: disable=protected-access

    @callback
    def handle_event(
        self, button: Button, _context: None, event: LutronEvent, _params: dict
    ) -> None:
        """Handle received event."""
        action: LutronEventType | None = None

        ev_map = {
            Button.Event.PRESS: LutronEventType.PRESS,
            Button.Event.RELEASE: LutronEventType.RELEASE,
            Button.Event.HOLD: LutronEventType.HOLD,
            Button.Event.DOUBLE_TAP: LutronEventType.DOUBLE_TAP,
            Button.Event.HOLD_RELEASE: LutronEventType.HOLD_RELEASE,
        }

        action = ev_map.get(event)

        if action:
            data = {
                ATTR_ID: self._id,
                ATTR_ACTION: LEGACY_EVENT_TYPES[action],
                ATTR_FULL_ID: self._full_id,
                ATTR_UUID: button.uuid,
            }
            self.hass.bus.fire("lutron_event", data)
            self._trigger_event(action)
            #self.async_write_ha_state()
            self.schedule_update_ha_state()