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

def translate_intensity_to_zh(intensity_val) -> str:
    """Translate API level representation to Traditional Chinese."""
    if intensity_val is None:
        return "0級"
    s = str(intensity_val).strip()
    if not s or s == "0" or s == "0.0":
        return "0級"
    
    mapping = {
        "1": "1級", "2": "2級", "3": "3級", "4": "4級",
        "5-": "5弱", "5+": "5強", "6-": "6弱", "6+": "6強", "7": "7級",
        "5弱": "5弱", "5強": "5強", "6弱": "6弱", "6強": "6強",
        "1級": "1級", "2級": "2級", "3級": "3級", "4級": "4級", "7級": "7級"
    }
    return mapping.get(s, s)

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
        
    if "5-" in s or "5弱" in s or "5minus" in s.lower():
        return 5.0
    elif "5+" in s or "5強" in s or "5plus" in s.lower():
        return 5.5
    elif "6-" in s or "6弱" in s or "6minus" in s.lower():
        return 6.0
    elif "6+" in s or "6強" in s or "6plus" in s.lower():
        return 6.5
    
    for char in s:
        if char.isdigit():
            return float(char)
            
    return 0.0

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two GPS coordinates using Haversine formula."""
    R = 6371.0  # Radius of Earth in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    # Normalize dlon difference to [-pi, pi] to find the shortest distance on the sphere
    dlon = (dlon + math.pi) % (2 * math.pi) - math.pi
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Taiwan EEW sensors from a config entry."""
    _LOGGER.info("Setting up Taiwan EEW sensors from config entry")
    location = entry.data.get("location", "Taipei")
    
    async_add_entities([
        TaiwanEEWWarningSensor(entry.entry_id, location),
        TaiwanEEWLastReportSensor(entry.entry_id, location)
    ], True)

class TaiwanEEWWarningSensor(SensorEntity):
    """Real-time Taiwan EEW Local Warning Sensor."""

    _attr_should_poll = False
    _attr_icon = "mdi:alert-decagram"

    def __init__(self, entry_id: str, location: str) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._location = location
        self._attr_name = f"Taiwan EEW Warning ({location})"
        self._attr_unique_id = f"taiwan_eew_warning_{location.lower()}"
        
        # Internal states
        self._state = "0級"
        self._arrival_time_seconds = 0
        self._epicenter_location = "None"
        self._distance_km = None
        self._event_id = "None"
        self._report_num = 0
        self._intensity_value = 0.0
        self._is_drill = False
        
        self._reset_listener = None

    @property
    def device_info(self) -> dict:
        """Return device information about this sensor."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"Taiwan EEW ({self._location})",
            "manufacturer": "Taiwan EEW",
            "model": "台灣地震速報監測器",
            "sw_version": "1.0.0",
            "configuration_url": "https://twearthquake.github.io/",
        }

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
            
            # Chinese Attributes for beautiful UI display
            "預估震度": self._state,
            "震度數值": self._intensity_value,
            "預估波抵達秒數": self._arrival_time_seconds,
            "震央地點": self._epicenter_location,
            "震央距離_公里": self._distance_km,
            "是否為演習": "是" if self._is_drill else "否",
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
        _LOGGER.info("Taiwan EEW warning sensor (%s) received data update", self._location)

        # Cancel any active reset timer
        if self._reset_listener:
            self._reset_listener()
            self._reset_listener = None

        is_clear = data.get("clear") or data.get("alert") in ("clear", "end", "cancel")

        if is_clear:
            self._state = "0級"
            self._intensity_value = 0.0
            self._arrival_time_seconds = 0
            self._epicenter_location = "None"
            self._distance_km = None
            self._event_id = "None"
            self._report_num = 0
            self._is_drill = False
        else:
            magnitude = data.get("magnitude") or data.get("mag") or data.get("scale")
            arrival = data.get("arrival_time_seconds") or data.get("arrival") or data.get("seconds") or data.get("time_to_wave")
            epicenter = data.get("epicenter_location") or data.get("epicenter") or data.get("location")
            self._is_drill = bool(data.get("is_drill", False))

            # Parse coordinates and calculate distance to Home Assistant home GPS location
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

            self._event_id = str(data.get("event_id") or data.get("id") or "None")
            try:
                self._report_num = int(data.get("report_num") or data.get("seq") or data.get("report", 0))
            except (ValueError, TypeError):
                self._report_num = 0

            self._epicenter_location = str(epicenter) if epicenter is not None else "None"
            self._state = translate_intensity_to_zh(magnitude)
            self._intensity_value = parse_intensity_to_float(magnitude)
            
            if arrival is not None:
                try:
                    self._arrival_time_seconds = int(arrival)
                except (ValueError, TypeError):
                    self._arrival_time_seconds = 0
            else:
                self._arrival_time_seconds = 0

            # Start a reset timer so that if no update is received for DEFAULT_RESET_TIMEOUT seconds,
            # we automatically fall back to the clear state (0級 / 0s)
            self._reset_listener = async_call_later(
                self.hass,
                DEFAULT_RESET_TIMEOUT,
                self._reset_state_callback
            )

        self.async_write_ha_state()

    @callback
    def _reset_state_callback(self, _now) -> None:
        """Callback to reset sensor values and write state to HASS."""
        _LOGGER.info("Inactivity timeout reached for %s. Resetting warning state.", self._location)
        self._state = "0級"
        self._intensity_value = 0.0
        self._arrival_time_seconds = 0
        self._epicenter_location = "None"
        self._distance_km = None
        self._event_id = "None"
        self._report_num = 0
        self._is_drill = False
        self.async_write_ha_state()


class TaiwanEEWLastReportSensor(SensorEntity):
    """Taiwan EEW Diagnostic Last Official Report Sensor."""

    _attr_should_poll = False
    _attr_icon = "mdi:clipboard-text-clock"

    def __init__(self, entry_id: str, location: str) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._location = location
        self._attr_name = f"Taiwan EEW Last Report ({location})"
        self._attr_unique_id = f"taiwan_eew_last_report_{location.lower()}"
        
        # Internal states
        self._state = "None"
        self._scale = None
        self._depth = None
        self._max_level = "None"
        self._event_time = "None"
        self._has_tsunami = False
        self._tsunami_report = "None"
        self._epicenter_lat = None
        self._epicenter_lon = None

    @property
    def device_info(self) -> dict:
        """Return device information about this sensor."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"Taiwan EEW ({self._location})",
            "manufacturer": "Taiwan EEW",
            "model": "台灣地震速報監測器",
            "sw_version": "1.0.0",
            "configuration_url": "https://twearthquake.github.io/",
        }

    @property
    def native_value(self) -> str:
        """Return the epicenter location of the last earthquake."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            # Chinese Attributes for beautiful UI display
            "震央地點": self._state,
            "芮氏規模": self._scale,
            "震源深度_公里": self._depth,
            "最大震度": self._max_level,
            "地震發生時間": self._event_time,
            "震央緯度": self._epicenter_lat,
            "震央經度": self._epicenter_lon,
            "海嘯警報": "是" if self._has_tsunami else "否",
            "海嘯報告內容": self._tsunami_report,
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
        _LOGGER.info("Taiwan EEW last report sensor (%s) received data update", self._location)

        epicenter = data.get("epicenter_location") or data.get("epicenter") or data.get("location")
        if epicenter is None or epicenter == "None":
            return  # Ignore blank updates

        self._state = str(epicenter)
        self._scale = data.get("scale")
        self._depth = data.get("depth")
        self._max_level = translate_intensity_to_zh(data.get("max_level"))
        self._event_time = data.get("time") or data.get("event_id")
        self._has_tsunami = bool(data.get("has_tsunami", False))
        self._tsunami_report = data.get("tsunami_report") or "None"
        self._epicenter_lat = data.get("latitude") or data.get("lat")
        self._epicenter_lon = data.get("longitude") or data.get("lon") or data.get("lng")
        
        self.async_write_ha_state()
