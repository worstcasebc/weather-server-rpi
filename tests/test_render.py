from meteo_client import WeatherSnapshot, HourlyEntry, DailyEntry
from render import render_weather_image
from pack import quantize_and_pack


def _snap():
    return WeatherSnapshot(
        current_dt=1715000000, current_temp=18.4, current_feels_like=17.9,
        current_humidity=62, current_wind=3.1, current_uvi=4.2,
        current_pressure=1015, current_visibility_m=10000, current_clouds=40, current_aqi=2,
        tz_offset_s=7200,
        current_icon="01d", current_desc="klarer himmel",
        sunrise=1714970000, sunset=1715025000,
        hourly=[HourlyEntry(1715000000 + i * 3600, 18 + i * 0.4, "01d", 0.05 * i)
                for i in range(24)],
        daily=[DailyEntry(1715000000 + d * 86400, 10 + d, 20 + d, "01d", 0.0)
               for d in range(7)],
    )


def test_render_returns_800x480():
    img = render_weather_image(_snap(), "Bad Camberg")
    assert img.size == (800, 480)
    assert img.mode == "RGB"


def test_render_then_pack_is_192000():
    img = render_weather_image(_snap(), "Bad Camberg")
    raw = quantize_and_pack(img)
    assert len(raw) == 192_000
