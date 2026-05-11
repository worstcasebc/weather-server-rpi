from unittest.mock import patch, MagicMock
import meteo_client
from meteo_client import fetch_weather, WeatherSnapshot, _icon_code, _european_aqi_to_band


def test_icon_mapping_day_night():
    assert _icon_code(0, 1) == "01d"
    assert _icon_code(0, 0) == "01n"
    assert _icon_code(61, 1) == "10d"
    assert _icon_code(95, 0) == "11n"
    assert _icon_code(45, 1) == "50d"


def test_aqi_banding():
    assert _european_aqi_to_band(10) == 1
    assert _european_aqi_to_band(30) == 2
    assert _european_aqi_to_band(50) == 3
    assert _european_aqi_to_band(70) == 4
    assert _european_aqi_to_band(95) == 5
    assert _european_aqi_to_band(None) == 0


FORECAST_FIXTURE = {
    "utc_offset_seconds": 7200,
    "current": {
        "time": "2026-05-10T22:00",
        "temperature_2m": 15.0,
        "apparent_temperature": 14.5,
        "relative_humidity_2m": 70,
        "wind_speed_10m": 1.5,
        "weather_code": 61,
        "surface_pressure": 1013.0,
        "cloud_cover": 80,
        "is_day": 0,
    },
    "hourly": {
        "time": [f"2026-05-10T{h:02d}:00" for h in range(22, 24)]
                + [f"2026-05-11T{h:02d}:00" for h in range(0, 24)],
        "temperature_2m":           [15 - i * 0.2 for i in range(26)],
        "weather_code":             [61] * 26,
        "precipitation_probability":[40] * 26,
        "is_day":                   [0, 0] + [0] * 6 + [1] * 12 + [0] * 6,
        "visibility":               [10000] * 26,
        "uv_index":                 [0.0] * 26,
    },
    "daily": {
        "time":                          [f"2026-05-{10 + d:02d}" for d in range(7)],
        "temperature_2m_max":            [20 - d for d in range(7)],
        "temperature_2m_min":            [10 - d for d in range(7)],
        "weather_code":                  [61] * 7,
        "precipitation_probability_max": [50] * 7,
        "sunrise":                       [f"2026-05-{10 + d:02d}T05:47" for d in range(7)],
        "sunset":                        [f"2026-05-{10 + d:02d}T20:59" for d in range(7)],
    },
}

AQI_FIXTURE = {"current": {"european_aqi": 30}}


def _mock_get(url, params=None, timeout=None):
    m = MagicMock(status_code=200, raise_for_status=lambda: None)
    if "air-quality" in url:
        m.json = lambda: AQI_FIXTURE
    else:
        m.json = lambda: FORECAST_FIXTURE
    return m


def test_fetch_weather_parses_fixture():
    with patch.object(meteo_client.requests, "get", side_effect=_mock_get):
        snap = fetch_weather(50.30, 8.27)
    assert isinstance(snap, WeatherSnapshot)
    assert snap.tz_offset_s == 7200
    assert snap.current_temp == 15.0
    assert snap.current_aqi == 2  # 30 → "Gut"
    assert snap.current_icon == "10n"  # weather_code 61, is_day 0
    assert snap.current_desc == "Leichter Regen"
    assert len(snap.hourly) == 24
    assert len(snap.daily) == 7
