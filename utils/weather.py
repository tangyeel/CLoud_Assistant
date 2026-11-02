"""
utils/weather.py — Free Real-time Weather Integration using Open-Meteo API.
Requires zero API keys. Fetches live conditions, temperature, and daily forecasts.
"""
import httpx
from config import USER_CITY
from utils.logger import logger

# Cache coordinates for city lookups
_GEO_CACHE: dict[str, tuple[float, float, str]] = {}

WMO_WEATHER_CODES = {
    0: "Clear sky ☀️",
    1: "Mainly clear 🌤️",
    2: "Partly cloudy ⛅",
    3: "Overcast ☁️",
    45: "Foggy 🌫️",
    48: "Depositing rime fog 🌫️",
    51: "Light drizzle 🌦️",
    53: "Moderate drizzle 🌧️",
    55: "Dense drizzle 🌧️",
    61: "Slight rain 🌦️",
    63: "Moderate rain 🌧️",
    65: "Heavy rain ⛈️",
    71: "Slight snow 🌨️",
    73: "Moderate snow 🌨️",
    75: "Heavy snow ❄️",
    80: "Slight rain showers 🌦️",
    81: "Moderate rain showers 🌧️",
    82: "Violent rain showers ⛈️",
    95: "Thunderstorm ⚡",
    96: "Thunderstorm with slight hail ⛈️",
    99: "Thunderstorm with heavy hail ⛈️",
}


def _geocode_city(city_name: str) -> tuple[float, float, str] | None:
    """Find latitude and longitude using Open-Meteo Geocoding API."""
    city_key = city_name.strip().lower()
    if city_key in _GEO_CACHE:
        return _GEO_CACHE[city_key]

    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    lat = results[0]["latitude"]
                    lon = results[0]["longitude"]
                    official_name = results[0]["name"]
                    _GEO_CACHE[city_key] = (lat, lon, official_name)
                    return (lat, lon, official_name)
    except Exception as e:
        logger.warning(f"Geocoding failed for '{city_name}': {e}")

    # Fallback coordinates: New Delhi
    return (28.6139, 77.2090, city_name)


def get_weather(city_name: str | None = None) -> dict:
    """
    Retrieve live weather and daily forecast.

    Returns dict containing:
    - city: Name of location
    - temperature: Current temp in °C
    - feels_like: Apparent temp in °C
    - condition: Description with emoji
    - humidity: Relative humidity percentage
    - temp_max: Today's maximum temp
    - temp_min: Today's minimum temp
    - rain_chance: Today's max precipitation probability (%)
    - spoken_summary: Plain English sentence for Jarvis audio briefings
    - text_card: Formatted markdown card for Telegram display
    """
    target_city = city_name or USER_CITY
    geo = _geocode_city(target_city)
    if not geo:
        return {
            "city": target_city,
            "spoken_summary": f"Weather data is currently unavailable for {target_city}.",
            "text_card": f"🌦️ Weather data unavailable for {target_city}.",
        }

    lat, lon, city_display = geo

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&timezone=auto"
        )

        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Open-Meteo returned status {resp.status_code}")

            data = resp.json()
            curr = data.get("current", {})
            daily = data.get("daily", {})

            temp = round(curr.get("temperature_2m", 0), 1)
            feels_like = round(curr.get("apparent_temperature", temp), 1)
            code = curr.get("weather_code", 0)
            condition = WMO_WEATHER_CODES.get(code, "Clear skies ☀️")
            humidity = curr.get("relative_humidity_2m", 50)
            wind = round(curr.get("wind_speed_10m", 0), 1)

            t_max = daily.get("temperature_2m_max", [temp])[0]
            t_min = daily.get("temperature_2m_min", [temp])[0]
            rain_chance = daily.get("precipitation_probability_max", [0])[0] or 0

            spoken = (
                f"In {city_display}, it is currently {temp} degrees Celsius, feels like {feels_like}, "
                f"with {condition.split(' ')[0].lower()} conditions. "
                f"Today's high will be {t_max} degrees, and low around {t_min} degrees"
            )
            if rain_chance > 30:
                spoken += f", with a {rain_chance} percent chance of rain, so keeping an umbrella handy is advised."
            else:
                spoken += "."

            card = (
                f"🌦️ **Weather in {city_display}**\n\n"
                f"• Condition: **{condition}**\n"
                f"• Temperature: **{temp}°C** (Feels like {feels_like}°C)\n"
                f"• High / Low: **{t_max}°C** / **{t_min}°C**\n"
                f"• Rain Chance: **{rain_chance}%** | Humidity: **{humidity}%**\n"
                f"• Wind: **{wind} km/h**"
            )

            return {
                "city": city_display,
                "temperature": temp,
                "feels_like": feels_like,
                "condition": condition,
                "humidity": humidity,
                "temp_max": t_max,
                "temp_min": t_min,
                "rain_chance": rain_chance,
                "spoken_summary": spoken,
                "text_card": card,
            }

    except Exception as e:
        logger.warning(f"Open-Meteo fetch error: {e}")
        return {
            "city": target_city,
            "spoken_summary": f"Weather data is currently unavailable for {target_city}.",
            "text_card": f"🌦️ Weather data unavailable for {target_city}.",
        }


def get_tomorrow_weather(city_name: str | None = None) -> dict:
    """
    Retrieve tomorrow's weather forecast for Patiala/configured city.
    """
    target_city = city_name or USER_CITY
    geo = _geocode_city(target_city)
    if not geo:
        return {
            "city": target_city,
            "spoken_summary": f"Weather forecast is currently unavailable for {target_city}.",
            "text_card": f"🌦️ Tomorrow's weather unavailable for {target_city}.",
        }

    lat, lon, city_display = geo

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
            f"&timezone=auto"
        )

        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Open-Meteo returned status {resp.status_code}")

            data = resp.json()
            daily = data.get("daily", {})

            # Index 1 is tomorrow
            idx = 1 if len(daily.get("temperature_2m_max", [])) > 1 else 0
            t_max = daily.get("temperature_2m_max", [25])[idx]
            t_min = daily.get("temperature_2m_min", [15])[idx]
            rain_chance = daily.get("precipitation_probability_max", [0])[idx] or 0
            code = daily.get("weather_code", [0])[idx]
            condition = WMO_WEATHER_CODES.get(code, "Clear skies ☀️")

            spoken = (
                f"Tomorrow in {city_display}, expect {condition.split(' ')[0].lower()} skies "
                f"with a high of {t_max} degrees and an early morning low around {t_min} degrees"
            )
            if rain_chance > 25:
                spoken += f", with a {rain_chance} percent probability of rain."
            else:
                spoken += ", with virtually no chance of rain."

            card = (
                f"🌦️ **Tomorrow's Weather in {city_display}**\n\n"
                f"• Condition: **{condition}**\n"
                f"• Expected High / Low: **{t_max}°C** / **{t_min}°C**\n"
                f"• Rain Probability: **{rain_chance}%**"
            )

            return {
                "city": city_display,
                "condition": condition,
                "temp_max": t_max,
                "temp_min": t_min,
                "rain_chance": rain_chance,
                "spoken_summary": spoken,
                "text_card": card,
            }

    except Exception as e:
        logger.warning(f"Open-Meteo tomorrow forecast error: {e}")
        return {
            "city": target_city,
            "spoken_summary": f"Tomorrow's weather forecast is currently unavailable for {target_city}.",
            "text_card": f"🌦️ Tomorrow's weather unavailable for {target_city}.",
        }
