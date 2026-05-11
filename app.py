import os
import time
import threading
import logging
from io import BytesIO
from flask import Flask, Response, abort
from meteo_client import fetch_weather
from render import render_weather_image
from pack import quantize_and_pack

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weather-render")

LAT      = float(os.environ.get("WX_LAT", "52.52"))
LON      = float(os.environ.get("WX_LON", "13.41"))
LOC_NAME = os.environ.get("LOCATION_NAME", "Berlin")
TTL      = int(os.environ.get("CACHE_TTL_SECONDS", "3300"))

_cache = {"raw": None, "ts": 0.0}
_lock  = threading.Lock()


def _refresh() -> bytes:
    log.info("fetching open-meteo…")
    snap = fetch_weather(LAT, LON)
    img  = render_weather_image(snap, LOC_NAME)
    raw  = quantize_and_pack(img)
    assert len(raw) == 192_000
    return raw


def _get_image() -> bytes:
    now = time.time()
    with _lock:
        if _cache["raw"] is None or (now - _cache["ts"]) > TTL:
            _cache["raw"] = _refresh()
            _cache["ts"]  = now
        return _cache["raw"]


app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/image.bin")
def image_bin():
    try:
        raw = _get_image()
    except Exception as e:
        log.exception("render failed: %s", e)
        abort(503)
    return Response(
        raw, mimetype="application/octet-stream",
        headers={
            "Content-Length": str(len(raw)),
            "Cache-Control":  f"max-age={TTL}",
        },
    )


@app.get("/preview.png")
def preview_png():
    snap = fetch_weather(LAT, LON)
    img  = render_weather_image(snap, LOC_NAME)
    buf  = BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
