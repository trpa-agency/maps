"""Fetch PurpleAir sensor readings for the Tahoe Basin into a static JSON file.

The smoke map is a static page in a public repo, so it cannot hold a PurpleAir
API key. This script runs in GitHub Actions with the key in a repo secret,
writes tools/purpleair-tahoe.json, and the page fetches that file. The key never
reaches a browser, and the API is called once per run no matter how many people
load the map.

PurpleAir bills a one-time grant of points, not a monthly allowance, so the
budget is finite and unrecoverable. Two gates protect it, in order:

  1. Smoke gate   - skip entirely unless air quality is degraded or smoke is
                    forecast over the basin. Both checks use free, keyless
                    services. Clear-air days cost nothing.
  2. Balance gate - read the live balance from the API and refuse to spend
                    below RESERVE_POINTS.

Measured cost for the query below is about 800 points for roughly 113 sensors.
Balance accounting lags the call by up to a minute, which is why a reserve
floor exists rather than a stop-at-zero: PurpleAir balances can go negative.

Usage:
    PURPLEAIR_READ_KEY=... python scripts/fetch_purpleair.py

Exit codes are always 0 for a clean skip. A non-zero exit means the fetch was
attempted and genuinely failed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG = logging.getLogger("purpleair")

# ── Budget ───────────────────────────────────────────────────────────────────
# Never spend below this. The grant is one-time, so this is the floor that keeps
# a lagging balance read from pushing the account negative.
RESERVE_POINTS = int(os.environ.get("PURPLEAIR_RESERVE_POINTS", 100_000))

# Measured: billing settles within roughly a minute of the call.
BILLING_LAG_SECONDS = 75

# ── Area of interest ─────────────────────────────────────────────────────────
# The TRPA boundary bounding box. Widening this raises cost roughly linearly
# with the number of sensors returned: the basin box returns about 113 sensors
# at ~800 points, the regional box about 262 at ~2,360.
BBOX = {"nwlng": -120.21, "nwlat": 39.29, "selng": -119.84, "selat": 38.84}

# Six fields, deliberately. Each extra field costs roughly one point per sensor
# per call. name and confidence were dropped: sensor_index identifies a sensor
# well enough for a popup, and PurpleAir's own max_age filter covers most of
# what confidence was screening out.
FIELDS = "sensor_index,latitude,longitude,pm2.5_cf_1,humidity,last_seen"

PURPLEAIR_SENSORS = "https://api.purpleair.com/v1/sensors"
PURPLEAIR_ORG = "https://api.purpleair.com/v1/organization"

# ── Free services used by the smoke gate ─────────────────────────────────────
AIRNOW = ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
          "Air%20Now%20Current%20Monitor%20Data%20Public/FeatureServer/0/query")
SMOKE = ("https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/services/"
         "NDGD_SmokeForecast_v1/FeatureServer/0/query")

# Gate opens at Moderate. Below that there is nothing a sensor network would
# tell the public that the regulatory monitors are not already saying.
AQI_TRIGGER = int(os.environ.get("PURPLEAIR_AQI_TRIGGER", 51))
# How far ahead to look in the smoke forecast, so the sensors are already
# populated by the time smoke actually arrives.
FORECAST_LOOKAHEAD_HOURS = 12

OUT_PATH = Path(__file__).resolve().parent.parent / "tools" / "purpleair-tahoe.json"


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: int = 60) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


# ── Gate 1: is there smoke worth spending points on? ─────────────────────────
def basin_air_is_degraded() -> bool:
    """True if any AirNow monitor in or near the basin is at Moderate or worse."""
    try:
        data = get_json(AIRNOW, {
            "geometry": f"{BBOX['nwlng']},{BBOX['selat']},{BBOX['selng']},{BBOX['nwlat']}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "where": f"Status = 'Active' AND PM_AQI >= {AQI_TRIGGER}",
            "returnCountOnly": "true",
            "f": "json",
        })
        count = data.get("count", 0)
        LOG.info("AirNow monitors at or above AQI %d in the basin: %s", AQI_TRIGGER, count)
        return count > 0
    except Exception:
        # A gate failure must not silently spend points, but it also should not
        # block a genuine smoke event. Fall through to the forecast check.
        LOG.exception("AirNow gate check failed")
        return False


def smoke_is_forecast() -> bool:
    """True if the NWS forecasts more than trace smoke over the basin soon."""
    try:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=FORECAST_LOOKAHEAD_HOURS)
        data = get_json(SMOKE, {
            "geometry": f"{BBOX['nwlng']},{BBOX['selat']},{BBOX['selng']},{BBOX['nwlat']}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            # The 0-3 band is trace smoke and covers very large areas, so it is
            # not on its own a reason to start polling.
            "where": (
                "smoke_classdesc <> '0 - 3' AND "
                f"todate >= timestamp '{now:%Y-%m-%d %H:00:00}' AND "
                f"todate <= timestamp '{horizon:%Y-%m-%d %H:00:00}'"
            ),
            "returnCountOnly": "true",
            "f": "json",
        })
        count = data.get("count", 0)
        LOG.info("Forecast smoke polygons above trace over the basin: %s", count)
        return count > 0
    except Exception:
        LOG.exception("Smoke forecast gate check failed")
        return False


# ── Gate 2: balance ──────────────────────────────────────────────────────────
def remaining_points(key: str) -> int:
    data = get_json(PURPLEAIR_ORG, headers={"X-API-Key": key})
    points = int(data.get("remaining_points", 0))
    LOG.info("PurpleAir balance: %s points", f"{points:,}")
    return points


# ── Readings ─────────────────────────────────────────────────────────────────
def epa_correct(pa_cf1, humidity):
    """EPA's PurpleAir correction (Barkjohn 2021, extended for high values).

    Raw PurpleAir readings run high in wildfire smoke. Without this the map
    would overstate the hazard, which is the one thing a smoke map must not do.
    """
    if pa_cf1 is None:
        return None
    rh = 35 if humidity is None else humidity
    if pa_cf1 <= 343:
        value = 0.52 * pa_cf1 - 0.086 * rh + 5.75
    else:
        value = 0.46 * pa_cf1 + 3.93e-4 * pa_cf1 ** 2 + 2.97
    return max(0.0, value)


# 2024 EPA PM2.5 breakpoints.
AQI_BREAKS = [
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500),
]


def pm_to_aqi(pm):
    if pm is None:
        return None
    c = round(max(0.0, pm), 1)
    for c_lo, c_hi, i_lo, i_hi in AQI_BREAKS:
        if c <= c_hi:
            return round((i_hi - i_lo) / (c_hi - c_lo) * (c - c_lo) + i_lo)
    return 500


def fetch_sensors(key: str) -> list[dict]:
    params = {
        "fields": FIELDS,
        "location_type": "0",   # outdoor only
        "max_age": "3600",      # drop anything silent for over an hour
        **BBOX,
    }
    data = get_json(PURPLEAIR_SENSORS, params, headers={"X-API-Key": key})
    idx = {name: i for i, name in enumerate(data["fields"])}
    sensors = []
    for row in data.get("data", []):
        raw = row[idx["pm2.5_cf_1"]]
        rh = row[idx["humidity"]]
        corrected = epa_correct(raw, rh)
        if corrected is None:
            continue
        sensors.append({
            "id": row[idx["sensor_index"]],
            "lon": row[idx["longitude"]],
            "lat": row[idx["latitude"]],
            "pm25": round(corrected, 1),
            "pm25raw": raw,
            "humidity": rh,
            "aqi": pm_to_aqi(corrected),
            "lastSeen": row[idx["last_seen"]],
        })
    return sensors


def write_output(sensors, balance_before, balance_after, reason):
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": reason,
        "count": len(sensors),
        "pointsRemaining": balance_after,
        "pointsSpent": (balance_before - balance_after) if balance_after is not None else None,
        "sensors": sensors,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    LOG.info("Wrote %s with %d sensors", OUT_PATH, len(sensors))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    key = os.environ.get("PURPLEAIR_READ_KEY", "").strip()
    if not key:
        LOG.error("PURPLEAIR_READ_KEY is not set")
        return 1

    # Gate 1, spend nothing on clear air.
    degraded = basin_air_is_degraded()
    forecast = smoke_is_forecast() if not degraded else True
    if not (degraded or forecast):
        LOG.info("No degraded air and no smoke forecast. Skipping, 0 points spent.")
        return 0
    reason = "observed" if degraded else "forecast"

    # Gate 2, never spend into the reserve.
    balance = remaining_points(key)
    if balance <= RESERVE_POINTS:
        LOG.warning(
            "Balance %s is at or below the %s reserve. Skipping, 0 points spent. "
            "Buy points or lower RESERVE_POINTS to resume.",
            f"{balance:,}", f"{RESERVE_POINTS:,}",
        )
        return 0

    sensors = fetch_sensors(key)

    # Read back so the committed file records real spend rather than an estimate.
    # Billing lags the call by up to a minute, reading immediately reports the
    # pre-call balance and the file ends up claiming the fetch was free. Waiting
    # costs nothing but wall clock, and it makes the recorded budget trustworthy.
    time.sleep(BILLING_LAG_SECONDS)
    after = remaining_points(key)
    write_output(sensors, balance, after, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
