import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_LOCATION, CONF_POLL_INTERVAL

# Location list mapping English keys to Traditional Chinese labels
LOCATIONS = {
    "Taipei": "台北市 (Taipei)",
    "NewTaipei": "新北市 (NewTaipei)",
    "Taoyuan": "桃園市 (Taoyuan)",
    "Hsinchu": "新竹縣市 (Hsinchu)",
    "Miaoli": "苗栗縣 (Miaoli)",
    "Taichung": "台中市 (Taichung)",
    "Nantou": "南投縣 (Nantou)",
    "Changhua": "彰化縣 (Changhua)",
    "Yunlin": "雲林縣 (Yunlin)",
    "Chiayi": "嘉義縣市 (Chiayi)",
    "Tainan": "台南市 (Tainan)",
    "Kaohsiung": "高雄市 (Kaohsiung)",
    "Pingtung": "屏東縣 (Pingtung)",
    "Keelung": "基隆市 (Keelung)",
    "Yilan": "宜蘭縣 (Yilan)",
    "Hualien": "花蓮縣 (Hualien)",
    "Taitung": "台東縣 (Taitung)",
    "Lianjiang": "連江縣 (Lianjiang)",
    "Kinmen": "金門縣 (Kinmen)",
    "Penghu": "澎湖縣 (Penghu)"
}

class TaiwanEEWConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Taiwan EEW."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            location = user_input[CONF_LOCATION]
            # Set unique ID based on location to prevent duplicate entries for the same city
            await self.async_set_unique_id(f"{DOMAIN}_{location}")
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=LOCATIONS.get(location, location),
                data=user_input
            )

        # Build schema with dropdown select and float validation
        data_schema = vol.Schema({
            vol.Required(CONF_LOCATION, default="Taipei"): vol.In(LOCATIONS),
            vol.Required(CONF_POLL_INTERVAL, default=1.5): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=10.0)
            )
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
