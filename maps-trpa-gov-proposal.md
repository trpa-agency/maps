# Map & Data Site Consolidation onto .gov

*Data Team → Comms. What's changing with our public map/data URLs and what Comms needs to update.*

## The plan

Two new .gov addresses, continuing what we started with data.trpa.gov:

- **maps.trpa.gov** — single public front door. A landing page linking to everything.
- **gis.trpa.gov** — our ArcGIS Enterprise portal, replacing the apps gallery (gis.trpa.org) and services (maps.trpa.org).

Most of our map layer is still on .org. This moves it onto the official .gov domain and gives us one link to hand out.

## Who does what

| Site | Role |
|---|---|
| **maps.trpa.gov** | Front door. Links to every map, app, dataset, dashboard. No data of its own. |
| **gis.trpa.gov** | ArcGIS Enterprise portal: viewers, web apps, and the services behind them. |
| **data.trpa.gov** | Data visualizations and dashboards. New, still building out. |
| **tahoeopendata.org** | Downloads and web services. |
| **ltinfo.org** | Indicator and threshold reporting (Lake Tahoe Info). |
| **trpa.gov/programs/maps** | Program context page. Links into maps.trpa.gov. |
| **maps.trpa.org / gis.trpa.org** | Legacy .org. Retire and redirect into gis.trpa.gov. |

Keep the three data surfaces distinct: **visualize** on data.trpa.gov, **download** on Tahoe Open Data, **report** on Lake Tahoe Info.

## Why .gov

Official government domain, restricted to gov entities, HTTPS enforced. Signals the maps are official and retires the .org addresses.

## Hosting

- **maps.trpa.gov** — static landing page on our existing GitHub setup, no new cost. Same model as data.trpa.gov.
- **gis.trpa.gov** — runs on ArcGIS Enterprise.

Front door stays fast and always up, separate from the portal's maintenance cycles. Mostly config and migration, not new development.

## Next steps

- **Data Team + IT:** register maps.trpa.gov and gis.trpa.gov.
- **Data Team:** build the maps.trpa.gov landing page.
- **Data Team + IT:** migrate the Enterprise portal to gis.trpa.gov; redirect the legacy .org addresses.
- **Comms:** update trpa.gov (incl. programs/maps) to point at maps.trpa.gov; refresh the link in print, decks, email signatures, and social.
- **Comms + Data Team:** align on announcement timing and messaging once the domains are live and secured.
