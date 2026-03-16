# Weather

Two providers — NWS (primary, US-only) and Open-Meteo (fallback, global). Both free, no API key.

## Quick Usage

```bash
# --- NWS (US only, more accurate) ---
# Step 1: Get grid from lat/lon
curl -s "https://api.weather.gov/points/32.78,-96.81" -H "User-Agent: Bartimaeus"
# → returns forecast URL like https://api.weather.gov/gridpoints/FWD/89,104/forecast

# Step 2: Get forecast
curl -s "https://api.weather.gov/gridpoints/FWD/89,104/forecast" -H "User-Agent: Bartimaeus"

# --- Open-Meteo (global fallback) ---
# Geocode city → lat/lon
curl -s "https://geocoding-api.open-meteo.com/v1/search?name=Dallas&count=1"

# Forecast
curl -s "https://api.open-meteo.com/v1/forecast?latitude=32.78&longitude=-96.81&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=auto&forecast_days=7"
```

## Python Helper

```python
import requests

HEADERS = {"User-Agent": "Bartimaeus"}

# ── Geocoding (Open-Meteo, works globally) ──

def geocode(city: str) -> dict:
    """Returns {name, latitude, longitude, country_code, timezone, ...} or raises."""
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1}).json()
    if not r.get("results"):
        raise ValueError(f"City not found: {city}")
    return r["results"][0]

# ── NWS (primary, US only) ──

def nws_weather(lat: float, lon: float) -> dict:
    """Get NWS forecast for US coordinates. Returns {current_period, periods}."""
    points = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=HEADERS).json()
    forecast_url = points["properties"]["forecast"]
    forecast = requests.get(forecast_url, headers=HEADERS).json()
    periods = forecast["properties"]["periods"]
    return {"current_period": periods[0], "periods": periods}

def format_nws(city: str) -> str:
    """Human-readable NWS forecast."""
    loc = geocode(city)
    data = nws_weather(round(loc["latitude"], 2), round(loc["longitude"], 2))
    lines = [f"📍 {loc['name']} (NWS)", ""]
    for p in data["periods"][:7]:
        wind = f"{p['windSpeed']} {p['windDirection']}"
        lines.append(f"{p['name']}: {p['temperature']}°{p['temperatureUnit']} — {p['shortForecast']} ({wind})")
    return "\n".join(lines)

# ── Open-Meteo (fallback, global) ──

WMO_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Severe thunderstorm"
}

def openmeteo_weather(city: str, days: int = 7) -> dict:
    """Get Open-Meteo forecast for any city worldwide."""
    loc = geocode(city)
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
        "forecast_days": days,
    }).json()
    return {"location": loc, "forecast": r}

def format_openmeteo(city: str) -> str:
    """Human-readable Open-Meteo forecast."""
    d = openmeteo_weather(city)
    cur = d["forecast"]["current"]
    daily = d["forecast"]["daily"]
    lines = [
        f"📍 {d['location']['name']} — {WMO_CODES.get(cur['weather_code'], '?')}",
        f"🌡️ {cur['temperature_2m']}°F (feels like {cur['apparent_temperature']}°F)",
        f"💨 {cur['wind_speed_10m']} mph | 💧 {cur['relative_humidity_2m']}% humidity",
        "",
        "7-Day Forecast:",
    ]
    for i, date in enumerate(daily["time"]):
        hi = daily["temperature_2m_max"][i]
        lo = daily["temperature_2m_min"][i]
        code = WMO_CODES.get(daily["weather_code"][i], "?")
        rain = daily["precipitation_probability_max"][i]
        lines.append(f"  {date}: {lo:.0f}–{hi:.0f}°F  {code}  ({rain}% precip)")
    return "\n".join(lines)

# ── Smart dispatcher ──

def weather(city: str) -> str:
    """Get weather — NWS for US cities, Open-Meteo for international."""
    loc = geocode(city)
    if loc.get("country_code") == "US":
        try:
            return format_nws(city)
        except Exception:
            pass  # fall through to Open-Meteo
    return format_openmeteo(city)
```

## NWS API Reference

- **Points**: `GET https://api.weather.gov/points/{lat},{lon}` → returns grid info + forecast URLs
- **Forecast**: `GET https://api.weather.gov/gridpoints/{office}/{x},{y}/forecast` → 7-day periods with text
- **Hourly**: `GET https://api.weather.gov/gridpoints/{office}/{x},{y}/forecast/hourly`
- **Alerts**: `GET https://api.weather.gov/alerts/active?point={lat},{lon}`
- **Header required**: `User-Agent: Bartimaeus`
- US-only, free, no key, no rate limit published (be reasonable)

## Open-Meteo API Reference

### Geocoding
- **URL**: `https://geocoding-api.open-meteo.com/v1/search`
- **Params**: `name` (required), `count`, `language`, `countryCode`

### Forecast
- **URL**: `https://api.open-meteo.com/v1/forecast`
- **Required**: `latitude`, `longitude`
- **Optional**: `current`, `hourly`, `daily`, `forecast_days` (0-16), `past_days` (0-92), `timezone`
- **Units**: `temperature_unit` (celsius/fahrenheit), `wind_speed_unit` (mph/kmh), `precipitation_unit` (inch/mm)
- **Current vars**: `temperature_2m`, `apparent_temperature`, `weather_code`, `wind_speed_10m`, `relative_humidity_2m`, `precipitation`, `cloud_cover`, `pressure_msl`
- **Daily vars**: `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`, `precipitation_probability_max`, `weather_code`, `sunrise`, `sunset`, `uv_index_max`
- **Hourly vars**: `temperature_2m`, `precipitation`, `precipitation_probability`, `weather_code`, `wind_speed_10m`, `cloud_cover`, `visibility`
- Free for non-commercial use, <10,000 calls/day

## WMO Weather Codes
0=Clear, 1=Mainly clear, 2=Partly cloudy, 3=Overcast, 45/48=Fog, 51/53/55=Drizzle, 61/63/65=Rain, 71/73/75=Snow, 80/81/82=Showers, 95/96/99=Thunderstorm
