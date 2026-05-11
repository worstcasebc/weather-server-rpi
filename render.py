"""Pillow-Renderer im InkyPi-weather-Layout.

Layout (800x480, 6-Farben e-Paper):
  Header  : 0..72   – Ortsname (groß, zentriert) + Datum (klein, zentriert)
  Today   : 72..255 – links Icon+Temp+FeelsLike+MinMax | rechts 4x2 Data-Grid
  Chart   : 255..370 – Stunden-Temperatur als Linie
  Forecast: 370..480 – 7 Tage in Boxen (Wochentag, Icon, High/Low)
"""
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
import os


def _tz(snap) -> timezone:
    return timezone(timedelta(seconds=getattr(snap, "tz_offset_s", 0)))


def _local(ts: int, snap) -> datetime:
    """Unix-Timestamp in der vom Snapshot vorgegebenen Zeitzone (z.B. Bad Camberg)."""
    return datetime.fromtimestamp(ts, tz=_tz(snap))

W, H = 800, 480
ICON_DIR = os.path.join(os.path.dirname(__file__), "assets", "icons")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

DE_WEEKDAY = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
DE_WEEKDAY_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
DE_MONTH = ["Januar", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _de_date(ts: int, snap) -> str:
    dt = _local(ts, snap)
    return f"{DE_WEEKDAY[dt.weekday()]}, {dt.day}. {DE_MONTH[dt.month - 1]}"


def _de_weekday_short(ts: int, snap) -> str:
    return DE_WEEKDAY_SHORT[_local(ts, snap).weekday()]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _icon(code: str, size: int) -> Image.Image:
    # Reihenfolge: exakte Variante → Tag-Pendant (z.B. 04n → 04d)
    # → Datenpunkt-Symbol → Sonne als Notnagel.
    candidates = [f"{code}.png"]
    if code.endswith("n"):
        candidates.append(f"{code[:-1]}d.png")
    candidates += [f"{code}.png", "01d.png"]
    for name in candidates:
        p = os.path.join(ICON_DIR, name)
        if os.path.exists(p):
            return Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    raise FileNotFoundError(f"no icon found for {code}")


def _paste(canvas, ic, x, y):
    canvas.paste(ic, (int(x), int(y)), ic)


def _format_visibility(m: int, units: str) -> str:
    if m <= 0:
        return "—"
    km = m / 1000.0
    if km >= 10:
        return ">10 km"
    return f"{km:.1f} km"


def _render_header(d: ImageDraw.ImageDraw, location: str, snap):
    title_f = _font(40, bold=True)
    date_f  = _font(20)
    d.text((W // 2, 8),  location, fill=BLACK, font=title_f, anchor="ma")
    d.text((W // 2, 50), _de_date(snap.current_dt, snap), fill=BLACK, font=date_f, anchor="ma")


def _render_today(img: Image.Image, d: ImageDraw.ImageDraw, snap):
    # ---------------- linke Hälfte (0..400) ----------------
    icon_size = 150
    icon_x = 20
    icon_y = 92
    _paste(img, _icon(snap.current_icon, icon_size), icon_x, icon_y)

    # Temp + FeelsLike + MinMax rechts vom Icon
    text_x = icon_x + icon_size + 12
    temp_f      = _font(96, bold=True)
    unit_f      = _font(36, bold=True)
    feels_f     = _font(20)
    minmax_f    = _font(22, bold=True)

    temp_str = f"{round(snap.current_temp)}"
    d.text((text_x, 88), temp_str, fill=BLACK, font=temp_f, anchor="la")
    # Einheiten-Suffix °C hochgestellt
    bbox = d.textbbox((text_x, 88), temp_str, font=temp_f, anchor="la")
    d.text((bbox[2] + 2, 98), "°C", fill=BLACK, font=unit_f, anchor="la")

    feels = f"Gefühlt {round(snap.current_feels_like)}°"
    d.text((text_x, 204), feels, fill=BLACK, font=feels_f, anchor="la")

    # ---------------- rechte Hälfte (400..800), 4x2 Grid ----------------
    aqi_labels = {1: "Sehr gut", 2: "Gut", 3: "Mäßig", 4: "Schlecht", 5: "Sehr schlecht"}
    aqi_value = aqi_labels.get(snap.current_aqi, "—")
    points = [
        # Zeile 1: Sonnenaufgang | Sonnenuntergang
        ("sunrise",    "Aufgang",     _local(snap.sunrise, snap).strftime("%H:%M"), ""),
        ("sunset",     "Untergang",   _local(snap.sunset,  snap).strftime("%H:%M"), ""),
        # Zeile 2: Wind | Luftfeuchte
        ("wind",       "Wind",        f"{snap.current_wind:.1f}", "m/s"),
        ("humidity",   "Luftfeuchte", f"{snap.current_humidity}", "%"),
        # Zeile 3: Druck | UV-Index
        ("pressure",   "Druck",       f"{snap.current_pressure}", "hPa"),
        ("uvi",        "UV-Index",    f"{snap.current_uvi:.1f}", ""),
        # Zeile 4: Sicht | Luftqualität
        ("visibility", "Sicht",       _format_visibility(snap.current_visibility_m, "metric"), ""),
        ("aqi",        "Luftqualität", aqi_value, ""),
    ]
    # 2 Spalten × 4 Zeilen, rechte Hälfte (~408..800 = 392 px breit, 78..238 = 160 px hoch)
    grid_x0, grid_y0 = 408, 90
    cell_w, cell_h = 196, 40
    label_f = _font(13)
    value_f = _font(20, bold=True)
    unit_f  = _font(12)
    for idx, (icon_code, label, value, unit) in enumerate(points):
        col = idx % 2
        row = idx // 2
        cx = grid_x0 + col * cell_w
        cy = grid_y0 + row * cell_h
        # Icon links (~36 px), vertikal zentriert in Zelle
        ic_size = 32
        _paste(img, _icon(icon_code, ic_size), cx + 4, cy + (cell_h - ic_size) // 2)
        # Text rechts vom Icon
        tx = cx + 4 + ic_size + 8
        d.text((tx, cy + 4),  label, fill=BLACK, font=label_f, anchor="la")
        d.text((tx, cy + 19), value, fill=BLACK, font=value_f, anchor="la")
        if unit:
            vbbox = d.textbbox((tx, cy + 19), value, font=value_f, anchor="la")
            d.text((vbbox[2] + 3, cy + 26), unit, fill=BLACK, font=unit_f, anchor="la")


def _render_chart(d: ImageDraw.ImageDraw, snap):
    # Bereich y=255..370, x=20..780
    x0, y0, x1, y1 = 20, 258, 780, 365
    pad_top = 8
    pad_bot = 18  # für Stunden-Labels
    chart_top = y0 + pad_top
    chart_bot = y1 - pad_bot

    pts = snap.hourly[:8]  # 8 Punkte ≙ 24 h in 3-h-Schritten
    if len(pts) < 2:
        return
    temps = [p.temp for p in pts]
    tmin, tmax = min(temps), max(temps)
    if tmax - tmin < 1:
        tmax = tmin + 1

    # Y-Skala: 4 Gridlines
    label_f = _font(11)
    n_grid = 4
    for i in range(n_grid):
        gy = chart_top + (chart_bot - chart_top) * i / (n_grid - 1)
        val = tmax - (tmax - tmin) * i / (n_grid - 1)
        d.line([(x0 + 30, gy), (x1, gy)], fill=(180, 180, 180), width=1)
        d.text((x0 + 26, gy), f"{round(val)}°", fill=BLACK, font=label_f, anchor="ra")

    # X-Punkte
    plot_x0 = x0 + 35
    plot_x1 = x1
    n = len(pts)
    coords = []
    for i, p in enumerate(pts):
        px = plot_x0 + (plot_x1 - plot_x0) * i / (n - 1)
        py = chart_top + (chart_bot - chart_top) * (1 - (p.temp - tmin) / (tmax - tmin))
        coords.append((px, py))

    # Linie zeichnen
    for i in range(len(coords) - 1):
        d.line([coords[i], coords[i + 1]], fill=BLACK, width=2)
    # Punkte + Stunden-Labels
    for (px, py), p in zip(coords, pts):
        d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=BLACK)
        hr = _local(p.dt, snap).strftime("%H")
        d.text((px, y1 - 12), hr, fill=BLACK, font=label_f, anchor="ma")


def _render_forecast(img: Image.Image, d: ImageDraw.ImageDraw, snap):
    # Bereich y=375..475, 7 Tage in Boxen
    y0 = 375
    y1 = 475
    days = snap.daily[:7]
    if not days:
        return
    n = len(days)
    gap = 8
    box_w = (W - 20 - 20 - gap * (n - 1)) // n
    box_h = y1 - y0
    name_f = _font(18, bold=True)
    temp_f = _font(16, bold=True)
    for i, dy in enumerate(days):
        bx = 20 + i * (box_w + gap)
        # Border
        d.rounded_rectangle([bx, y0, bx + box_w, y1], radius=8, outline=BLACK, width=1)
        # Wochentag
        wd = _de_weekday_short(dy.dt, snap)
        d.text((bx + box_w // 2, y0 + 4), wd, fill=BLACK, font=name_f, anchor="ma")
        # Icon
        ic_size = 40
        _paste(img, _icon(dy.icon, ic_size),
               bx + box_w // 2 - ic_size // 2, y0 + 28)
        # High / Low
        d.text((bx + box_w // 2, y0 + box_h - 20),
               f"{round(dy.tmax)}° / {round(dy.tmin)}°",
               fill=BLACK, font=temp_f, anchor="ma")


def render_weather_image(snap, location_name: str) -> Image.Image:
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    _render_header(d, location_name, snap)
    _render_today(img, d, snap)
    _render_chart(d, snap)
    _render_forecast(img, d, snap)
    return img
