# raspberry — Wetter-Render-Server

Render-Server für das ESP32-Wetter-Display. Holt Wetterdaten, rendert ein 800×480-Pixel-Bild und liefert es als 192 000-Byte-Rohbild für das 6-Farben-Spectra-e-Paper aus.

Der Server ist als Docker-Container ausgelegt (idealer Betriebsort: ein Raspberry Pi im selben LAN wie der ESP32). Lokales Ausführen aus einem Python-venv funktioniert genauso.

## Was läuft hier

```
            ┌──────────────────────────────────────┐
   /image.bin│  Flask-App (app.py)                  │
  ──────────►│  ┌─────────┐  ┌───────┐  ┌────────┐  │
            │  │meteo_   │→│render │→│pack    │  │
            │  │client.py│  │.py    │  │.py     │  │
            │  └─────────┘  └───────┘  └────────┘  │
            │  Cache 55 min (CACHE_TTL_SECONDS)   │
            └──────────────────────────────────────┘
                       │            │
                       ▼            ▼
              api.open-meteo  air-quality-api.
                  .com         open-meteo.com
```

- **`meteo_client.py`** — fetch der Open-Meteo-`/v1/forecast`- und `/v1/air-quality`-Endpoints, parst die Antwort in eine `WeatherSnapshot`-Datenklasse. Open-Meteo nutzt für Deutschland bevorzugt das DWD-ICON-Modell, ist kostenlos und braucht **keinen API-Key**.
- **`render.py`** — Pillow-Renderer. Erzeugt ein 800×480-RGB-Bild.
- **`pack.py`** — Floyd-Steinberg-Quantisierung auf die 6 Spectra-Farben (Schwarz, Weiß, Gelb, Rot, Blau, Grün) und 4-Bit-Packing in genau 192 000 Bytes (high-nibble = linker Pixel).
- **`app.py`** — Flask-Endpoints + In-Memory-Cache. Antwortet stündlich aus dem Cache, refresht bei Ablauf.

## HTTP-API

| Endpoint        | Beschreibung                                           |
|-----------------|--------------------------------------------------------|
| `GET /healthz`  | Liveness-Check, antwortet `ok`                         |
| `GET /image.bin`| 192 000 Bytes 4-bpp Rohbild für das Display (kein Header) |
| `GET /preview.png` | Debug — RGB-PNG vor der 6-Farben-Quantisierung      |

`/image.bin` ist der einzige Endpoint, den die ESP32-Firmware abfragt. `/preview.png` dient nur der visuellen Layout-Kontrolle im Browser.

## Layout

800 × 480 Pixel, weißer Hintergrund, vier vertikale Bereiche:

| Bereich     | Y-Bereich  | Inhalt                                                      |
|-------------|-----------:|-------------------------------------------------------------|
| Header      | 0..72      | Ortsname (groß zentriert) + Datum (`Sonntag, 10. Mai`)      |
| Today       | 92..255    | Großes Wetter-Icon · Temperatur (96 px) · Gefühlt °         |
| Datapoints  | 90..250 r. | 2 Spalten × 4 Zeilen (rechte Hälfte)                         |
| Chart       | 258..365   | Stunden-Temperatur als Linie (8 h, 1-h-Schritte)             |
| Forecast    | 375..475   | 7 Tage in Boxen: Wochentag · Icon · `max° / min°`            |

**Datapoints-Anordnung** (jeweils mit InkyPi-Icon links + Label/Wert rechts):

| Zeile | linke Spalte           | rechte Spalte           |
|-------|------------------------|-------------------------|
| 1     | Aufgang (`%H:%M`)      | Untergang (`%H:%M`)     |
| 2     | Wind (m/s)             | Luftfeuchte (%)         |
| 3     | Druck (hPa)            | UV-Index                |
| 4     | Sicht (km)             | Luftqualität (Sehr gut..Sehr schlecht) |

## Konfiguration

Konfiguration über Umgebungsvariablen (z.B. via `.env` für Docker-Compose):

| Variable             | Default        | Beschreibung                                       |
|----------------------|----------------|----------------------------------------------------|
| `WX_LAT`             | `52.52`        | Latitude des Anzeige-Orts                          |
| `WX_LON`             | `13.41`         | Longitude des Anzeige-Orts                         |
| `LOCATION_NAME`      | `Berlin`  | Anzeigename im Header (Werte mit Leerzeichen quoten) |
| `CACHE_TTL_SECONDS`  | `3300`         | Cache-Lebensdauer in Sekunden (55 min, sodass 1-h-ESP32-Wakeup garantiert frische Daten sieht) |

Standortwechsel: Werte in `.env` ändern und Container neu starten — kein ESP32-Reflash nötig.

## Installation & Betrieb

### Variante A: Docker (empfohlen)

```bash
cd raspberry
cp .env.example .env   # falls vorhanden, sonst .env mit Werten oben anlegen
docker compose --env-file .env up -d --build
curl -s http://localhost:8080/healthz   # → ok
curl -s -o /tmp/img.bin -w "%{size_download}\n" http://localhost:8080/image.bin
# 192000
```

### Variante B: Lokales venv (für Entwicklung / Debug)

```bash
cd raspberry
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a && source .env && set +a
.venv/bin/python app.py
```

### Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

10 Tests decken Packer (Format & Palette), Open-Meteo-Client (Icon-Mapping, AQI-Banding, Fixture-Parsing) und Renderer (Bildgröße + Pack-Roundtrip) ab.

### Layout-Vorschau im Browser

```bash
open http://localhost:8080/preview.png
```

Pixelgenaue Vergleiche mit dem InkyPi-Original können hierüber visuell gemacht werden, ohne dass der ESP32 oder das Display angeschlossen sein muss.

## Zeitzone

Open-Meteo liefert `utc_offset_seconds` für den abgefragten Standort mit (z.B. `7200` für CEST). Dieser Offset wird in `WeatherSnapshot.tz_offset_s` mitgeführt; sämtliche Zeitformatierungen im Renderer (Datum, Aufgang/Untergang, Stunden-Achse, Wochentage) nutzen diesen Offset. Folge: Anzeige stimmt unabhängig davon, in welcher Zeitzone der Container läuft (Docker-Default = UTC ist also unproblematisch).

## Bilddatenformat (verbindlich)

- 800 × 480 px, 4 bpp, **High-Nibble = linker Pixel**.
- 192 000 Bytes ohne Header.
- Hardware-Farbwerte (Spectra 6, aus `esp32/src/EPD_7in3e.h`): `BLACK=0x0`, `WHITE=0x1`, `YELLOW=0x2`, `RED=0x3`, `BLUE=0x5`, `GREEN=0x6`. `0x4` ist Hersteller-reserviert (Orange) und darf nicht verwendet werden.

Diese Spezifikation **muss** vom Server eingehalten werden. Tests in `tests/test_pack.py` decken Größe, Nibble-Reihenfolge und Palette ab.
