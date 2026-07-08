# TRPA Maps

Official production mapping apps of TRPA, served at **maps.trpa.gov** via GitHub Pages. This site replaces the gallery at gis.trpa.org as apps are migrated and new apps are built.

## Structure

```
maps/
├── index.html          # Main gallery — all apps grouped by category
├── apps.json           # Single source of truth for the app registry
├── 404.html            # Branded not-found page
├── assets/
│   ├── site.css        # Shared styles (TRPA brand)
│   ├── gallery.js      # Shared gallery renderer
│   └── thumbs/         # App thumbnails
├── planning/           # Planning apps (zoning, transportation, housing, shoreline)
├── permitting/         # Permitting apps (parcels, permits)
├── eip/                # Environmental Improvement Program apps (stormwater, forest health, SEZ)
└── tools/              # General viewers, open data, developer resources
```

Each category folder has an `index.html` landing page that lists only its apps. Migrated and new apps live as subfolders inside their category, e.g. `planning/localplans/` → `maps.trpa.gov/planning/localplans/`.

## Adding or updating an app

Edit `apps.json` — every page reads from it, so no HTML changes are needed:

```json
{
  "id": "myapp",
  "title": "My App",
  "category": "planning",
  "url": "planning/myapp/",
  "thumbnail": "assets/thumbs/myapp.png",
  "description": "One or two sentences. TRPA style: spell out acronyms on first use.",
  "tags": ["Zoning"],
  "external": false
}
```

- `category` must match a `slug` in the `categories` array (`planning`, `permitting`, `eip`, `tools`).
- `url` can be relative (apps hosted in this repo) or absolute (apps still on gis.trpa.org or external sites like Lake Tahoe Info).
- Set `"external": true` for non-TRPA-hosted sites. Thumbnails are 200 x 133 PNGs in `assets/thumbs/`.

## Migrating an app from gis.trpa.org

1. Copy the app's files into a subfolder of the right category, e.g. `eip/bmpmappingtool/`.
2. Update its entry in `apps.json` to the new relative URL.
3. Set up a redirect from the old gis.trpa.org URL once DNS and traffic cut over.

## Local preview

Serve the repo root (fetch of `apps.json` requires http, not file://):

```
python -m http.server 8000
```

Then open http://localhost:8000.

## Deployment

Pushed to `main` → published by GitHub Pages at `trpa-agency.github.io/maps`.

To cut over to the maps.trpa.gov custom domain later:

1. Add a DNS CNAME record pointing `maps.trpa.gov` to `trpa-agency.github.io`.
2. Add a `CNAME` file at the repo root containing `maps.trpa.gov` (or set the custom domain in Settings → Pages, which commits the file).
3. Enforce HTTPS in Settings → Pages once the certificate provisions.

Do not commit the `CNAME` file before DNS is in place — GitHub Pages redirects the github.io URL to the custom domain, which breaks the site if the domain does not resolve.
