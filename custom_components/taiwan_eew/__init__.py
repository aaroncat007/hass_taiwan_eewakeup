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

from .const import DOMAIN, DEFAULT_TW_URL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

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
    # Return True, configuration is now handled via UI (Config Flow)
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
    
    # Bypass SSL verification to avoid SSLCertVerificationError
    connector = aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=3.0)
    
    async with aiohttp.ClientSession(connector=connector) as session:
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
                    if has_eq:
                        eq = data.get("Earthquake") or {}
                        normalized_data = {
                            "magnitude": eq.get("level"),
                            "arrival_time_seconds": eq.get("second"),
                            "epicenter_location": eq.get("address"),
                            "latitude": eq.get("latitude"),
                            "longitude": eq.get("longitude"),
                            "event_id": eq.get("time"),
                            "report_num": 1,
                        }
                        _LOGGER.info("Earthquake detected for %s! Dispatching: %s", location, normalized_data)
                        async_dispatcher_send(hass, signal_name, normalized_data)
                        
                        # Fire HASS Event containing the city name for automations to filter by location
                        event_data = dict(normalized_data)
                        event_data["location"] = location
                        hass.bus.async_fire(f"{DOMAIN}_event", event_data)
                    else:
                        # Send clear message to reset state
                        normalized_data = {"clear": True}
                        async_dispatcher_send(hass, signal_name, normalized_data)
                        
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.exception("Error polling TWEarthquake API for %s: %s", location, err)
                
            await asyncio.sleep(poll_interval)
