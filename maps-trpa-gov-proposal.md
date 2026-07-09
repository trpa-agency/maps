# Map & Data Site Consolidation onto .gov

## The plan

Two new .gov addresses, continuing what we started with data.trpa.gov:

- **maps.trpa.gov:** Front door. A landing page linking to everything maps.
- **gis.trpa.gov:**  ArcGIS Enterprise portal landing URL, replacing the legacy .org URL.

## Who does what

| Site | Role |
|---|---|
| **maps.trpa.gov** | Front door. Links to every map app. |
| **gis.trpa.gov** | ArcGIS Enterprise portal. |
| **data.trpa.gov** | Data visualizations and dashboards. |
| **tahoeopendata.org** | Downloads and web services. |
| **ltinfo.org** | Indicators, trackers, and threshold evaluations. |
| **trpa.gov/programs/maps** | Program context page. Links into maps.trpa.gov. |
| **maps.trpa.org / gis.trpa.org** | Legacy .org. Retire and redirect into gis.trpa.gov. |

Keep the pages distinct: **maps** on maps.trpa.gov, **visualize** on data.trpa.gov, **download** on Tahoe Open Data, **report** on Lake Tahoe Info.

## Why .gov

Official government domain. Signals the maps are official and retires the .org addresses.

## Hosting

- **maps.trpa.gov:** static landing page on our existing GitHub setup, no new cost. Same model as data.trpa.gov.
- **gis.trpa.gov:** runs on ArcGIS Enterprise.

Front door stays fast and always up, separate from the portal's maintenance cycles. Mostly config and migration, not new development.

## Next steps

- **Data Team + IT:** register maps.trpa.gov and gis.trpa.gov.
- **Data Team:** build the maps.trpa.gov landing page.
- **Data Team + IT:** migrate the Enterprise portal to gis.trpa.gov; redirect the legacy .org addresses.
- **Comms:** update trpa.gov/programs/maps to point at (embed?) maps.trpa.gov.
- **Comms + Data Team:** align on announcement timing and messaging once the domains are live and secured.
