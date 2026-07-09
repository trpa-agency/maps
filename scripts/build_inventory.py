#!/usr/bin/env python3
"""Rebuild tools/data-inventory.json for the Tahoe Data Inventory grid.

Sources, in order:
  1. Tahoe Open Data  — every dataset in the tahoeopendata.org DCAT feed,
                        with geometry probed from the live layer.
  2. LT Info          — static seed (scripts/inventory_seed.json); no
                        crawlable directory exists for the tabular API.
  3. REST Only        — services on maps.trpa.org not referenced by the
                        DCAT feed or the LT Info seed.
  4. Partner agencies — public REST directories (USFS EDW, CTC, El Dorado,
                        Placer, Washoe, Douglas NV, City of South Lake Tahoe).

Failsafe: if a source errors out or returns less than MIN_KEEP_RATIO of its
previous row count, the previous rows for that source are kept and the drop
is flagged in inventory_summary.md. Stdlib only — safe for GitHub Actions.
"""
import concurrent.futures
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "data-inventory.json"
SEED = ROOT / "scripts" / "inventory_seed.json"
SUMMARY = ROOT / "inventory_summary.md"

TRPA_BASE = "https://maps.trpa.org/server/rest/services"
DCAT_URL = "https://www.tahoeopendata.org/api/feed/dcat-us/1.1.json"
VIEWER = "https://www.arcgis.com/apps/mapviewer/index.html?url="

PARTNERS = [
    # (source label, directory base, only these folders (None = root + all), crawl folders?)
    ("USFS EDW", "https://apps.fs.usda.gov/arcx/rest/services", ["EDW"], False),
    ("California Tahoe Conservancy", "https://tahoegis.org/server/rest/services", None, True),
    ("El Dorado County", "https://see-eldorado.edcgov.us/arcgis/rest/services", None, True),
    ("Washoe County", "https://wcgisweb.washoecounty.us/arcgis/rest/services", None, True),
    ("Douglas County NV", "https://gisservices.douglasnv.us/server/rest/services", None, True),
    ("Placer County", "https://services9.arcgis.com/NENkjkswKTzMfG3A/ArcGIS/rest/services", None, False),
    ("City of South Lake Tahoe", "https://services2.arcgis.com/gWRYLIS16mKUskSO/arcgis/rest/services", None, False),
    ("Tahoe RCD", "https://services6.arcgis.com/1KtlSd2mklZMBKaz/arcgis/rest/services", None, False),
]
PARTNER_SOURCES = {p[0] for p in PARTNERS}
KEEP_TYPES = {"MapServer", "FeatureServer", "ImageServer", "SceneServer", "GPServer"}
SKIP_FOLDERS = {"test", "demo", "temp", "utilities"} - {"utilities"}  # keep Utilities (real data at counties)
SKIP_FOLDERS = {"test", "demo", "temp"}
MIN_KEEP_RATIO = 0.7

THEMES = [
    ("Imagery & Elevation", ["imagery", "ortho", "aerial", "lidar", "elevation", "hillshade", "dem", "basemap", "bathymetr"]),
    ("Vegetation & Forest", ["vegetation", "forest", "tree", "fuel", "timber", "silvicult", "stand", "conifer",
                             "aspen", "meadow", "agricult", "crop"]),
    ("Parcels & Ownership", ["parcel", "assessor", "apn", "ownership", "property", "tax", "address", "situs",
                             "deed", "assessed", "leasehold", "easement"]),
    ("Permitting", ["permit", "accela", "inspection", "code_enforce", "bmp", "ipes", "land capability", "land_capability", "coverage"]),
    ("Air & Climate", ["air quality", "climate", "carbon", "emission", "greenhouse", "ghg", "ozone",
                       "renewable", "solar", "electrif", "energy"]),
    ("Planning & Zoning", ["planning", "zoning", "zoned", "land_use", "land use", "landuse", "boundar", "district",
                           "general_plan", "redistrict", "census", "jurisdiction", "town center", "area plan",
                           "development", "housing", "homeless", "affordable", "dwelling", "building", "built environment"]),
    ("Transportation", ["transportation", "road", "street", "traffic", "transit", "bike", "bridge", "pavement",
                        "highway", "crash", "taz", "nbi", "airport", "aluc", "mobility"]),
    ("Recreation", ["recreation", "trail", "park", "campground", "ski", "beach", "boat"]),
    ("Utilities", ["utilit", "sewer", "wastewater", "septic", "well "]),
    ("Soils & Hydrology", ["soil", "hydro", "water", "stream", "flood", "fema", "storm", "watershed", "sez",
                           "wetland", "drainage", "erosion", "geol", "impervious", "catchment", "contour", "nhd", "wbd"]),
    ("Shorezone", ["shorezone", "shoreline", "pier", "buoy", "mooring", "calcium"]),
    ("Wildlife & Aquatic", ["wildlife", "habitat", "fish", "species", "invasive", "eagle", "osprey", "goshawk",
                            "falcon", "frog", "marten", "bat ", "biodiversity", "edna", "aquatic", "ais ", "aip "]),
    ("Fire & Emergency", ["fire", "emergency", "evac", "hazard", "eoc", "rapidsos", "spillman", "wildfire",
                          "burn", "smoke", "avalanche", "cwpp", "defensible"]),
    ("Demographics", ["demograph", "population", "zip code", "zip data", "zipdata", "block group"]),
    ("Civic & Elections", ["ballot", "election", "precinct", "supervisor", "voting", "vote "]),
    # Monitoring is nearly a catch-all — keep it after every specific theme
    ("Monitoring", ["monitoring", "survey", "transect", "sampling", "sample", "periphyton", "site assessment"]),
    ("Historic", ["histor", "heritage", "archaeo"]),
]


def log(msg):
    print(msg, flush=True)


def fetch_json(url, timeout=30, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TRPA-inventory-bot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — retry any transport/parse error
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


# Broad categories for the pill filter — derived from theme, with a
# title-keyword override for economic datasets (no theme captures those).
THEME_CATEGORY = {
    "Vegetation & Forest": "Environment", "Soils & Hydrology": "Environment",
    "Wildlife & Aquatic": "Environment", "Air & Climate": "Environment",
    "Shorezone": "Environment", "Monitoring": "Environment", "Stormwater": "Environment",
    "EIP / Projects": "Environment", "EIP / Indicators": "Environment",
    "Thresholds": "Environment", "Mooring": "Environment", "Contours": "Environment",
    "Impervious": "Environment",
    "Planning & Zoning": "Land Use & Planning", "Parcels & Ownership": "Land Use & Planning",
    "Permitting": "Land Use & Planning", "Historic": "Land Use & Planning",
    "Development Rights": "Land Use & Planning", "Parcels": "Land Use & Planning",
    "Boundaries": "Land Use & Planning", "Planning & Jurisdictions": "Land Use & Planning",
    "Transportation": "Transportation",
    "Recreation": "Recreation",
    "Fire & Emergency": "Public Safety",
    "Utilities": "Infrastructure",
    "Demographics": "Demographic & Economic", "Civic & Elections": "Demographic & Economic",
    "Imagery & Elevation": "Basemaps & Imagery",
}
ECON_KEYWORDS = ["economic", "economy", "business", "sales tax", "income", "employment",
                 "lodging", "occupancy", "visitation", "workforce", "labor"]
CATEGORY_ORDER = ["Environment", "Land Use & Planning", "Transportation", "Recreation",
                  "Public Safety", "Infrastructure", "Demographic & Economic",
                  "Basemaps & Imagery", "Other"]


def category_for(theme, name):
    key = name.lower()
    if any(k in key for k in ECON_KEYWORDS):
        return "Demographic & Economic"
    return THEME_CATEGORY.get(theme, "Other")


# Folder names that make useless themes (org/plumbing folders, not topics)
FOLDER_THEME_SKIP = {"edw", "hosted", "agol", "opendata", "datasharing", "publicrequests",
                     "ugotnetandextracts", "csd_app", "dts", "douglas", "pw", "basemaps"}
# Folder names that map onto an existing theme instead of minting a duplicate
FOLDER_THEME_ALIAS = {"parcels": "Parcels & Ownership", "stormwater": "Soils & Hydrology",
                      "hydrology": "Soils & Hydrology", "fema": "Soils & Hydrology",
                      "boundaries": "Planning & Zoning", "trakit": "Permitting",
                      "spillman": "Fire & Emergency", "wastewater": "Utilities"}


def theme_for(name, folder=""):
    key = name.lower()
    for theme, kws in THEMES:
        if any(k in key for k in kws):
            return theme
    if folder:
        fl = folder.lower()
        if fl in FOLDER_THEME_ALIAS:
            return FOLDER_THEME_ALIAS[fl]
        if fl not in FOLDER_THEME_SKIP:
            f = folder.replace("_", " ").strip()
            if len(f) <= 24:
                return f
    return "General"


def enc_url(url):
    scheme, rest = url.split("://", 1)
    host, _, path = rest.partition("/")
    return f"{scheme}://{host}/{urllib.parse.quote(path)}"


def viewer_for(service_url):
    if re.search(r"/(MapServer|FeatureServer|ImageServer)(/\d+)?$", service_url):
        return VIEWER + urllib.parse.quote(service_url, safe="")
    return ""


GEOM_LABEL = {
    "esriGeometryPoint": "Point", "esriGeometryMultipoint": "Point",
    "esriGeometryPolyline": "Polyline", "esriGeometryPolygon": "Polygon",
    "esriGeometryEnvelope": "Polygon",
}


def probe_geometry(url):
    """Layer URL -> Point/Polyline/Polygon/Table/Raster/''."""
    try:
        meta = fetch_json(url + "?f=json", timeout=20, tries=2)
    except Exception:
        return ""
    if "ImageServer" in url:
        return "Raster"
    if meta.get("type") == "Table":
        return "Table"
    return GEOM_LABEL.get(meta.get("geometryType"), "")


# ── Tahoe Open Data (DCAT feed) ──────────────────────────────────────────────
def build_tod_rows():
    feed = fetch_json(DCAT_URL, timeout=60)
    rows, layer_urls = [], {}
    for ds in feed.get("dataset", []):
        title = (ds.get("title") or "").strip()
        landing = ds.get("landingPage") or ""
        if not title or not landing:
            continue
        geo = next((d.get("accessURL") for d in ds.get("distribution", [])
                    if d.get("format") == "ArcGIS GeoServices REST API"), None)
        if geo:
            geo = enc_url(geo.strip().rstrip("/"))
            host = urllib.parse.urlparse(geo).hostname or ""
            if host.endswith("maps.trpa.org"):
                channel = "ArcGIS REST (maps.trpa.org)"
            elif host.endswith("arcgis.com"):
                channel = "AGOL hosted"
            else:
                channel = f"External ({host})"
            if re.search(r"/(MapServer|FeatureServer)/\d+$", geo):
                dtype = "Feature Layer"
            elif geo.endswith("ImageServer"):
                dtype = "Image Service"
            elif geo.endswith("FeatureServer"):
                dtype = "Feature Service"
            else:
                dtype = "Map Service"
            endpoint = re.sub(r"^https?://[^/]+/(server/rest/services/|arcgis/rest/services/|ArcGIS/rest/services/)?", "", geo)
        else:
            channel, dtype, endpoint = "Hub download", "Document Link", landing
        row = {
            "source": "Tahoe Open Data", "channel": channel, "theme": theme_for(title),
            "name": title, "type": dtype, "access": "No key", "geometry": "",
            "endpoint": endpoint, "serviceUrl": geo or landing,
            "downloadUrl": landing, "viewerUrl": viewer_for(geo) if geo else "",
        }
        rows.append(row)
        if geo and re.search(r"/(MapServer|FeatureServer)/\d+$", geo):
            layer_urls[geo] = row
    # probe layer geometry concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for url, geom in zip(layer_urls, ex.map(probe_geometry, layer_urls)):
            layer_urls[url]["geometry"] = geom
    rows.sort(key=lambda r: (r["theme"], r["name"].lower()))
    return rows, feed


# ── TRPA REST Only ───────────────────────────────────────────────────────────
def build_rest_only_rows(feed):
    root = fetch_json(TRPA_BASE + "?f=json")
    # services already represented on Tahoe Open Data (by service name) or LT Info
    covered = set()
    for ds in feed.get("dataset", []):
        for d in ds.get("distribution", []):
            u = d.get("accessURL") or ""
            m = re.search(r"maps\.trpa\.org/server/rest/services/([^/?]+)/(?:Map|Feature|Image)Server", u, re.I)
            if m:
                covered.add(m.group(1).lower())
    by_name = {}
    for s in root.get("services", []):
        by_name.setdefault(s["name"], set()).add(s["type"])
    rows = []
    for name in sorted(by_name, key=str.lower):
        if name.lower() in covered or name.lower().startswith("ltinfo"):
            continue
        types = by_name[name]
        if not types & KEEP_TYPES:
            continue
        tlabel, probe = type_label(types)
        service_url = f"{TRPA_BASE}/{name}/{probe}"
        rows.append({
            "source": "REST Only", "channel": "ArcGIS REST (maps.trpa.org)",
            "theme": theme_for(name), "name": name.replace("_", " "),
            "type": tlabel, "access": "No key", "geometry": "",
            "endpoint": f"{name}/{probe}", "serviceUrl": service_url,
            "downloadUrl": "", "viewerUrl": viewer_for(service_url),
        })
    return rows


def type_label(types):
    if "MapServer" in types and "FeatureServer" in types:
        return "Map + Feature Service", "MapServer"
    for t, label in [("MapServer", "Map Service"), ("FeatureServer", "Feature Service"),
                     ("ImageServer", "Image Service"), ("SceneServer", "Scene Service"),
                     ("GPServer", "Geoprocessing Service")]:
        if t in types:
            return label, t
    t = sorted(types)[0]
    return t, t


# ── Partner agencies ─────────────────────────────────────────────────────────
def build_partner_rows(source, base, only_folders, crawl_folders):
    root = fetch_json(base + "?f=json")
    services = []
    folders = only_folders if only_folders is not None else (root.get("folders", []) if crawl_folders else [])
    if only_folders is None:
        services += root.get("services", [])
    for f in folders:
        if f.lower() in SKIP_FOLDERS:
            continue
        try:
            services += fetch_json(f"{base}/{f}?f=json").get("services", [])
        except Exception as e:
            log(f"  warn: {source}/{f} folder failed ({type(e).__name__})")
    host = urllib.parse.urlparse(base).hostname
    by_name = {}
    for s in services:
        if s["type"] in KEEP_TYPES:
            by_name.setdefault(s["name"], set()).add(s["type"])
    rows = []
    for full in sorted(by_name, key=str.lower):
        folder, _, short = full.rpartition("/")
        if folder.lower() in SKIP_FOLDERS or short.lower() in SKIP_FOLDERS:
            continue
        tlabel, probe = type_label(by_name[full])
        service_url = enc_url(f"{base}/{full}/{probe}")
        rows.append({
            "source": source, "channel": f"ArcGIS REST ({host})",
            "theme": theme_for(short, folder), "name": short.replace("_", " "),
            "type": tlabel, "access": "No key", "geometry": "",
            "endpoint": f"{full}/{probe}", "serviceUrl": service_url,
            "downloadUrl": "", "viewerUrl": viewer_for(service_url),
        })
    return rows


# ── Assembly with failsafe ───────────────────────────────────────────────────
def main():
    previous = {}
    if OUT.exists():
        for r in json.loads(OUT.read_text(encoding="utf-8")).get("rows", []):
            previous.setdefault(r["source"], []).append(r)

    notes, out_rows = [], []

    def take(source, builder):
        """Run a source builder; fall back to previous rows on failure/shrink."""
        old = previous.get(source, [])
        try:
            new = builder()
        except Exception as e:  # noqa: BLE001 — a dead server must not empty the catalog
            notes.append(f"- **{source}: crawl failed ({type(e).__name__}) — kept previous {len(old)} rows.**")
            out_rows.extend(old)
            return
        if old and len(new) < len(old) * MIN_KEEP_RATIO:
            notes.append(f"- **{source}: count dropped {len(old)} -> {len(new)} (>30%) — kept previous rows; investigate.**")
            out_rows.extend(old)
            return
        delta = f" ({len(old)} -> {len(new)})" if old and len(old) != len(new) else ""
        notes.append(f"- {source}: {len(new)} rows{delta}")
        out_rows.extend(new)

    log("Tahoe Open Data (DCAT)…")
    feed_holder = {}

    def tod():
        rows, feed = build_tod_rows()
        feed_holder["feed"] = feed
        return rows

    take("Tahoe Open Data", tod)

    log("LT Info (seed)…")
    take("LT Info", lambda: json.loads(SEED.read_text(encoding="utf-8")))

    log("TRPA REST Only…")
    feed = feed_holder.get("feed") or {"dataset": []}
    take("REST Only", lambda: build_rest_only_rows(feed))

    for source, base, only, crawl in PARTNERS:
        log(f"{source}…")
        take(source, lambda s=source, b=base, o=only, c=crawl: build_partner_rows(s, b, o, c))

    # Broad category for the pill filter — applied to every row, seed included
    for r in out_rows:
        r["category"] = category_for(r.get("theme", ""), r.get("name", ""))

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # generated on its own line so CI can diff-ignore timestamp-only changes
    OUT.write_text('{"generated":"%s",\n"rows":%s}\n'
                   % (generated, json.dumps(out_rows, ensure_ascii=True, separators=(",", ":"))),
                   encoding="utf-8")

    counts = Counter(r["source"] for r in out_rows)
    lines = [f"Data inventory refresh — {generated}", "",
             f"**{len(out_rows):,} total rows**", ""] + notes
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("\n".join(lines))
    log(f"\nWrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
