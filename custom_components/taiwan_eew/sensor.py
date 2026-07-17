"""Sensor platform for Taiwan EEW integration."""
import logging
import math
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_RESET_TIMEOUT = 120  # Seconds to wait before resetting values to 0

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two GPS coordinates using Haversine formula."""
    R = 6371.0  # Radius of Earth in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def parse_intensity_to_float(intensity_val) -> float:
    """Convert Taiwan intensity representation (e.g. 5, '5弱', '5-', '5強', '5+') to float."""
    if intensity_val is None:
        return 0.0
    
    if isinstance(intensity_val, (int, float)):
        return float(intensity_val)
        
    s = str(intensity_val).strip()
    if not s:
        return 0.0
        
    try:
        return float(s)
    except ValueError:
        pass
        
    # Map Taiwan's 2020 CWA intensity levels (5-/5+ and 6-/6+)
    # 5- / 5弱 -> 5.0
    # 5+ / 5強 -> 5.5
    # 6- / 6弱 -> 6.0
    # 6+ / 6強 -> 6.5
    # 7 -> 7.0
    if "5-" in s or "5弱" in s or "5minus" in s.lower():
        return 5.0
    elif "5+" in s or "5強" in s or "5plus" in s.lower():
        return 5.5
    elif "6-" in s or "6弱" in s or "6minus" in s.lower():
        return 6.0
    elif "6+" in s or "6強" in s or "6plus" in s.lower():
        return 6.5
    
    # Fallback: extract the first digit if available
    for char in s:
        if char.isdigit():
            return float(char)
            
    return 0.0

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Taiwan EEW sensor from a config entry."""
    _LOGGER.info("Setting up Taiwan EEW sensor from config entry")
    location = entry.data.get("location", "Taipei")
    sensor = TaiwanEEWSensor(entry.entry_id, location)
    async_add_entities([sensor], True)

class TaiwanEEWSensor(SensorEntity):
    """Representation of a Taiwan EEW Sensor."""

    _attr_should_poll = False
    _attr_icon = "mdi:earthquake"

    def __init__(self, entry_id: str, location: str) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._location = location
        self._attr_name = f"Taiwan EEW Sensor ({location})"
        self._attr_unique_id = f"taiwan_eew_{location.lower()}"
        
        # Internal states
        self._state = "0.0"
        self._arrival_time_seconds = 0
        self._epicenter_location = "None"
        self._distance_km = None
        self._event_id = "None"
        self._report_num = 0
        self._intensity_value = 0.0
        self._reset_listener = None

    @property
    def native_value(self) -> str:
        """Return the predicted magnitude/intensity (raw string representation)."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            "arrival_time_seconds": self._arrival_time_seconds,
            "epicenter_location": self._epicenter_location,
            "distance_km": self._distance_km,
            "event_id": self._event_id,
            "report_num": self._report_num,
            "intensity_value": self._intensity_value,
            "monitored_location": self._location,
        }

    async def async_added_to_hass(self) -> None:
        """Register dispatcher callbacks."""
        signal_name = f"{DOMAIN}_update_{self._location}"
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_name,
                self._handle_update
            )
        )

    @callback
    def _handle_update(self, data: dict) -> None:
        """Handle incoming updates from the dispatcher."""
        _LOGGER.info("Taiwan EEW sensor (%s) received data update: %s", self._location, data)

        # Cancel any active reset timer
        if self._reset_listener:
            self._reset_listener()
            self._reset_listener = None

        # Check if this is an explicit clear/reset signal
        is_clear = data.get("clear") or data.get("alert") in ("clear", "end", "cancel")

        if is_clear:
            _LOGGER.info("Explicit clear/end signal received for %s. Resetting state.", self._location)
            self._reset_state()
            self.async_write_ha_state()
            return

        # Parse magnitude/intensity from multiple possible payload structures
        magnitude = data.get("magnitude") or data.get("mag") or data.get("scale")

        # Parse arrival time in seconds
        arrival = data.get("arrival_time_seconds") or data.get("arrival") or data.get("seconds") or data.get("time_to_wave")

        # Parse epicenter location
        epicenter = data.get("epicenter_location") or data.get("epicenter") or data.get("location")

        # Parse coordinate and calculate distance to Home Assistant home GPS location
        lat = data.get("latitude") or data.get("lat")
        lon = data.get("longitude") or data.get("lon") or data.get("lng")
        
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude

        if lat is not None and lon is not None and home_lat is not None and home_lon is not None:
            try:
                self._distance_km = calculate_distance(
                    float(home_lat), float(home_lon),
                    float(lat), float(lon)
                )
            except (ValueError, TypeError):
                self._distance_km = None
        else:
            self._distance_km = None

        # Parse event metadata
        self._event_id = str(data.get("event_id") or data.get("id") or "None")
        try:
            self._report_num = int(data.get("report_num") or data.get("seq") or data.get("report", 0))
        except (ValueError, TypeError):
            self._report_num = 0

        # Update state with raw string representation
        self._state = str(magnitude) if magnitude is not None else "0.0"
        
        # Calculate float representation for automations
        self._intensity_value = parse_intensity_to_float(magnitude)

        if arrival is not None:
            try:
                self._arrival_time_seconds = int(arrival)
            except (ValueError, TypeError):
                self._arrival_time_seconds = 0
        else:
            self._arrival_time_seconds = 0

        self._epicenter_location = str(epicenter) if epicenter is not None else "None"

        # Start a new reset timer to reset state to 0 after inactivity
        self._reset_listener = async_call_later(
            self.hass,
            DEFAULT_RESET_TIMEOUT,
            self._reset_state_callback
        )

        self.async_write_ha_state()

    @callback
    def _reset_state(self) -> None:
        """Reset internal state to default values."""
        self._state = "0.0"
        self._arrival_time_seconds = 0
        self._epicenter_location = "None"
        self._distance_km = None
        self._event_id = "None"
        self._report_num = 0
        self._intensity_value = 0.0
        if self._reset_listener:
            self._reset_listener()
            self._reset_listener = None

    @callback
    def _reset_state_callback(self, _now) -> None:
        """Callback to reset sensor values and write state to HASS."""
        _LOGGER.info("Inactivity timeout reached for %s. Resetting sensor to 0.", self._location)
        self._reset_state()
        self.async_write_ha_state()
