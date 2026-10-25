"""The Taiwan EEW integration."""
import asyncio
import hashlib
import hmac
import logging
import time
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import Platform

from .const import API_INITIALIZATION_URL, DOMAIN, DEFAULT_TW_URL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

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

def generate_tw_headers() -> dict:
    """Generate HMAC-SHA256 signature headers for twearthquake API."""
    ts = str(int(time.time()))
    key = b"Copyrights-2024-2025,-Chang-Yu-Hsi.-All-rights-reserved."
    sign = hmac.new(key, ts.encode('utf-8'), hashlib.sha256).hexdigest()
    return {
        "TWEarthquake-Timestamp": ts,
        "TWEarthquake-Token-Sign": sign,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HomeAssistant"
    }

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Taiwan EEW component (legacy/YAML)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Taiwan EEW from a config entry."""
    location = entry.data.get("location", "Taipei")
    poll_interval = float(entry.data.get("poll_interval", 1.5))
    url = DEFAULT_TW_URL

    _LOGGER.info(
        "Setting up Taiwan EEW entry for location: %s (poll interval: %s s)",
        location, poll_interval
    )

    hass.data.setdefault(DOMAIN, {})
    
    # Start the async polling task for this location
    polling_task = hass.async_create_background_task(
        poll_twearthquake(hass, url, location, poll_interval),
        name=f"taiwan_eew_polling_{location}"
    )
    hass.data[DOMAIN][entry.entry_id] = polling_task

    # Forward the setup to platforms (sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Cancel the polling background task for this location
        polling_task = hass.data[DOMAIN].pop(entry.entry_id, None)
        if polling_task:
            polling_task.cancel()
            _LOGGER.info("Cancelled polling task for config entry %s", entry.entry_id)

    return unload_ok

async def poll_twearthquake(hass: HomeAssistant, base_url: str, location: str, poll_interval: float) -> None:
    """Poll twearthquake API endpoint for real-time EEW status."""
    _LOGGER.info("Starting twearthquake API polling loop for location: %s", location)
    url = f"{base_url.rstrip('/')}/{location}"
    signal_name = f"{DOMAIN}_update_{location}"
    
    # Enable TCP connection pooling and DNS caching while keeping TLS verification enabled.
    connector = aiohttp.TCPConnector(
        keepalive_timeout=30.0,
        ttl_dns_cache=300,
        limit=10
    )
    # Increased timeouts to ensure requests complete during server traffic spikes during earthquakes
    timeout = aiohttp.ClientTimeout(
        total=10.0,
        connect=5.0,
        sock_read=8.0
    )
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # The official website publishes its current API URL in this initialization
        # response. Keep the known current endpoint as a fallback if discovery fails.
        try:
            async with session.get(API_INITIALIZATION_URL, timeout=timeout) as response:
                response.raise_for_status()
                initialization = await response.json()
            discovered_url = (
                initialization.get("url")
                if isinstance(initialization, dict)
                else None
            )
            if isinstance(discovered_url, str) and discovered_url.startswith("https://"):
                url = f"{discovered_url.rstrip('/')}/{location}"
            else:
                _LOGGER.warning(
                    "TWEarthquake API discovery returned no valid URL; using fallback endpoint"
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.warning(
                "Could not discover TWEarthquake API endpoint, using fallback endpoint: %s",
                err,
            )

        _LOGGER.info("Using TWEarthquake API endpoint: %s", url)

        while True:
            try:
                headers = generate_tw_headers()
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.warning("TWEarthquake API returned status code %d for %s", response.status, location)
                        await asyncio.sleep(poll_interval)
                        continue
                        
                    data = await response.json()
                    _LOGGER.debug("Received TWEarthquake response for %s: %s", location, data)
                    
                    has_eq = data.get("HasEarthquake", False)
                    has_tsunami = data.get("HasTsunami", False)
                    tsunami_report = ""
                    if has_tsunami:
                        tsunami_report = data.get("tsunamiData", {}).get("ReportContent", "")
                    
                    rep = data.get("ReportData") or {}
                    
                    if has_eq:
                        eq = data.get("Earthquake") or {}
                        raw_level = eq.get("level")
                        normalized_data = {
                            "magnitude": raw_level,
                            "arrival_time_seconds": eq.get("second"),
                            "epicenter_location": eq.get("address") or rep.get("na"),
                            "latitude": eq.get("latitude") or rep.get("lat"),
                            "longitude": eq.get("longitude") or rep.get("lon"),
                            "event_id": eq.get("time") or rep.get("ti"),
                            "report_num": 1,
                            "scale": eq.get("scale") or rep.get("sc"),
                            "depth": eq.get("depth") or rep.get("de"),
                            "max_level": eq.get("maxlevel") or raw_level,
                            "is_drill": eq.get("isDrill", False),
                            "time": eq.get("time") or rep.get("ti"),
                            "has_tsunami": has_tsunami,
                            "tsunami_report": tsunami_report,
                            "intensity_value": parse_intensity_to_float(raw_level),
                        }
                        _LOGGER.info("Earthquake detected for %s! Dispatching: %s", location, normalized_data)
                        async_dispatcher_send(hass, signal_name, normalized_data)
                        
                        # Fire HASS Event containing the city name for automations to filter by location
                        event_data = dict(normalized_data)
                        event_data["location"] = location
                        hass.bus.async_fire(f"{DOMAIN}_event", event_data)
                    else:
                        # Extract the last recorded event details from ReportData
                        normalized_data = {
                            "clear": True,
                            "magnitude": "0",
                            "arrival_time_seconds": 0,
                            "epicenter_location": rep.get("na", "None"),
                            "latitude": rep.get("lat"),
                            "longitude": rep.get("lon"),
                            "event_id": rep.get("ti", "None"),
                            "report_num": 0,
                            "scale": rep.get("sc"),
                            "depth": rep.get("de"),
                            "max_level": "None",
                            "is_drill": False,
                            "time": rep.get("ti"),
                            "has_tsunami": has_tsunami,
                            "tsunami_report": tsunami_report,
                            "intensity_value": 0.0,
                        }
                        _LOGGER.debug("No active earthquake. Dispatching last report data: %s", normalized_data)
                        async_dispatcher_send(hass, signal_name, normalized_data)
                        
            except asyncio.CancelledError:
                break
            except (asyncio.TimeoutError, TimeoutError):
                _LOGGER.warning("Timeout connecting to TWEarthquake API for %s (server busy)", location)
                await asyncio.sleep(0.5)
                continue
            except aiohttp.ClientError as err:
                _LOGGER.warning("Network error polling TWEarthquake API for %s: %s", location, err)
                await asyncio.sleep(1.0)
                continue
            except Exception as err:
                _LOGGER.exception("Unexpected error polling TWEarthquake API for %s: %s", location, err)
                
            await asyncio.sleep(poll_interval)
