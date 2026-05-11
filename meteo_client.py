"""Open-Meteo Wetterdaten-Client.

Open-Meteo ist kostenlos und benötigt keinen API-Key. Für Deutschland nutzt
es bevorzugt das DWD-ICON-Modell, das deutlich präzisere Werte liefert als
der OWM-5d/3h-Free-Tier.

Wetter-Codes folgen WMO-Standard und werden hier auf die vorhandenen
InkyPi-OWM-Icon-Codes (`01d`/`01n` etc.) gemappt — so bleibt der Renderer
unverändert.
"""
from dataclasses import dataclass
from typing import List
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AQI_URL      = "https://air-quality-api.open-meteo.com/v1/air-quality"


@dataclass
class HourlyEntry:
    dt: int
    temp: float
    icon: str
    pop: float


@dataclass
class DailyEntry:
    dt: int
    tmin: float
    tmax: float
    icon: str
    pop: float


@dataclass
class WeatherSnapshot:
    current_dt: int
    current_temp: float
    current_feels_like: float
    current_humidity: int
    current_wind: float
    current_uvi: float
    current_pressure: int
    current_visibility_m: int
    current_clouds: int
    current_icon: str
    current_desc: str
    sunrise: int
    sunset: int
    hourly: List[HourlyEntry]
    daily: List[DailyEntry]
    current_aqi: int  # 1=Sehr gut .. 5=Sehr schlecht; 0 = unbekannt
    tz_offset_s: int


# WMO Wettercode → (OWM-Icon-Stamm, deutsche Beschreibung)
_WMO: dict = {
    0:  ("01", "Klar"),
    1:  ("02", "Überwiegend klar"),
    2:  ("03", "Teils bewölkt"),
    3:  ("04", "Bedeckt"),
    45: ("50", "Nebel"),
    48: ("50", "Reifnebel"),
    51: ("09", "Leichter Nieselregen"),
    53: ("09", "Nieselregen"),
    55: ("09", "Dichter Nieselregen"),
    56: ("09", "Gefrierender Nieselregen"),
    57: ("09", "Gefrierender Nieselregen"),
    61: ("10", "Leichter Regen"),
    63: ("10", "Regen"),
    65: ("10", "Starker Regen"),
    66: ("10", "Gefrierender Regen"),
    67: ("10", "Gefrierender Regen"),
    71: ("13", "Leichter Schneefall"),
    73: ("13", "Schneefall"),
    75: ("13", "Starker Schneefall"),
    77: ("13", "Schneegriesel"),
    80: ("09", "Leichte Regenschauer"),
    81: ("09", "Regenschauer"),
    82: ("09", "Heftige Regenschauer"),
    85: ("13", "Schneeschauer"),
    86: ("13", "Schneeschauer"),
    95: ("11", "Gewitter"),
    96: ("11", "Gewitter mit Hagel"),
    99: ("11", "Schweres Gewitter mit Hagel"),
}


def _icon_code(wmo: int, is_day: int) -> str:
    stem, _ = _WMO.get(int(wmo), ("01", "Unbekannt"))
    suffix = "d" if int(is_day) == 1 else "n"
    return f"{stem}{suffix}"


def _description(wmo: int) -> str:
    _, desc = _WMO.get(int(wmo), ("01", "Unbekannt"))
    return desc


def _european_aqi_to_band(aqi_val: float) -> int:
    """European AQI 0–100+ → 1..5 (Sehr gut..Sehr schlecht)."""
    if aqi_val is None:
        return 0
    if aqi_val < 20:
        return 1
    if aqi_val < 40:
        return 2
    if aqi_val < 60:
        return 3
    if aqi_val < 80:
        return 4
    return 5


def _fetch_aqi(lat: float, lon: float) -> int:
    try:
        r = requests.get(AQI_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "european_aqi",
            "timezone": "auto",
        }, timeout=8)
        if r.status_code == 200:
            j = r.json()
            val = j.get("current", {}).get("european_aqi")
            return _european_aqi_to_band(val)
    except Exception:
        pass
    return 0


def fetch_weather(lat: float, lon: float) -> WeatherSnapshot:
    params = {
        "latitude":  lat,
        "longitude": lon,
        "timezone":  "auto",
        "current": ",".join([
            "temperature_2m", "apparent_temperature", "relative_humidity_2m",
            "weather_code", "wind_speed_10m", "surface_pressure",
            "cloud_cover", "is_day",
        ]),
        "hourly": ",".join([
            "temperature_2m", "weather_code", "precipitation_probability",
            "is_day", "visibility", "uv_index",
        ]),
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "weather_code",
            "precipitation_probability_max", "sunrise", "sunset",
        ]),
        "wind_speed_unit": "ms",
        "forecast_days": 7,
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    j = r.json()

    tz_off = int(j.get("utc_offset_seconds", 0))
    cur    = j["current"]
    hourly = j["hourly"]
    daily  = j["daily"]

    # Stunden ab "jetzt": index der ersten Hourly-Stunde, die >= current_dt liegt.
    cur_dt = int(cur["time_epoch"]) if "time_epoch" in cur else int(cur.get("time_unix", 0))
    if cur_dt == 0:
        # Open-Meteo liefert "time" als ISO-String + "time"-Index. Fallback:
        from datetime import datetime, timezone
        cur_dt = int(datetime.fromisoformat(cur["time"])
                     .replace(tzinfo=timezone(__import__("datetime").timedelta(seconds=tz_off)))
                     .timestamp())
    hourly_unix: list = hourly.get("time_unix") or [
        _iso_to_unix(t, tz_off) for t in hourly["time"]
    ]
    start = 0
    for i, ts in enumerate(hourly_unix):
        if ts >= cur_dt:
            start = i
            break

    # Aktuelle UV/Sicht/Pressure aus dem ersten relevanten Hourly-Slot beziehen,
    # weil Open-Meteo "current" diese Felder nicht alle anbietet.
    uvi  = _safe_get(hourly.get("uv_index"),    start, 0.0)
    vis  = int(_safe_get(hourly.get("visibility"), start, 0))
    pres = int(round(cur.get("surface_pressure") or 0))

    hourly_out: List[HourlyEntry] = []
    for i in range(start, min(start + 24, len(hourly_unix))):
        hourly_out.append(HourlyEntry(
            dt=hourly_unix[i],
            temp=float(hourly["temperature_2m"][i]),
            icon=_icon_code(hourly["weather_code"][i], hourly["is_day"][i]),
            pop=float(hourly.get("precipitation_probability", [0] * len(hourly_unix))[i] or 0) / 100.0,
        ))

    daily_unix = daily.get("time_unix") or [
        _iso_to_unix(t + "T12:00", tz_off) for t in daily["time"]
    ]
    sunrise_unix = _iso_to_unix(daily["sunrise"][0], tz_off)
    sunset_unix  = _iso_to_unix(daily["sunset"][0],  tz_off)

    daily_out: List[DailyEntry] = []
    for i in range(min(7, len(daily_unix))):
        daily_out.append(DailyEntry(
            dt=daily_unix[i],
            tmin=float(daily["temperature_2m_min"][i]),
            tmax=float(daily["temperature_2m_max"][i]),
            icon=_icon_code(daily["weather_code"][i], 1),
            pop=float(daily.get("precipitation_probability_max", [0] * len(daily_unix))[i] or 0) / 100.0,
        ))

    aqi = _fetch_aqi(lat, lon)

    return WeatherSnapshot(
        current_dt=cur_dt,
        current_temp=float(cur["temperature_2m"]),
        current_feels_like=float(cur.get("apparent_temperature", cur["temperature_2m"])),
        current_humidity=int(cur.get("relative_humidity_2m", 0)),
        current_wind=float(cur.get("wind_speed_10m", 0.0)),
        current_uvi=float(uvi),
        current_pressure=pres,
        current_visibility_m=vis,
        current_clouds=int(cur.get("cloud_cover", 0)),
        current_icon=_icon_code(cur["weather_code"], cur.get("is_day", 1)),
        current_desc=_description(cur["weather_code"]),
        sunrise=sunrise_unix,
        sunset=sunset_unix,
        hourly=hourly_out,
        daily=daily_out,
        current_aqi=aqi,
        tz_offset_s=tz_off,
    )


def _safe_get(seq, idx: int, default):
    if seq is None or idx >= len(seq) or seq[idx] is None:
        return default
    return seq[idx]


def _iso_to_unix(iso: str, tz_off: int) -> int:
    """Open-Meteo liefert lokale Zeit als ISO ohne Offset (z.B. '2026-05-11T14:00').
    Mit dem timezone-Offset wandeln wir das in einen Unix-Timestamp um.
    """
    from datetime import datetime, timezone, timedelta
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(seconds=tz_off)))
    return int(dt.timestamp())
