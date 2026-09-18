# US offline maps and directions

## Setup and use

1. **Maps → Download US offline maps**, once while connected. An existing US archive is reused. The app installs the entire US walking dataset and its runtime; no radius, current position, example, or individual area selection is needed.
2. Wait for **US map and walking directions are ready offline**. This machine has the 20,750,661,818-byte CRM basemap copied independently plus 1,865,911,232 bytes of routing data. Initial sizes on other dates may differ.
3. **Find my location**: search a city or town, then a familiar road or landmark. Inspect the point and confirm **I am here**, or pin a point yourself. Searching and exploring never set your position. No default location, coordinates, GPS, or internet geocoder is required.
4. Search nearby resources, select a destination point, or ask Jarvis:
   - “Where is the nearest water?”
   - “How many miles to [recorded place]?”
   - “I'm on [road]. How do I get to [place]?”
   - “Give me directions.” (continues the preceding route)

Map answers work with the language model stopped. Nearby resource lookup covers 5 km around your confirmed point; city/town discovery searches an index built from local overview labels. Missing labels are not proof a place doesn't exist. Select distant destinations by finding their city and clicking the destination on the map. A city label identifies an approximate town center, not a street address. Duplicate names require a choice. A road name alone requires a confirmed nearby position or a more specific map point. Rendering-line crossings are never assumed to be connected intersections.

## Coverage and route meaning

The basemap and routing dataset cover the lower 48, Alaska/Aleutians, and the main Hawaiian islands. `resources/routing/us-coverage.geojson` defines the cutouts. Nearby foreign areas are included by the bounding boxes, but US territories, remote NW Hawaiian islands, and the Canadian corridor to Alaska are outside the advertised coverage. There is no land route between disconnected islands.

BRouter 1.7.10 runs as a local Java subprocess with local graph files. Its internal 5-degree files are installed together and traversed automatically; users never prepare them individually. No routing server or network fallback runs. Turn instructions come from the graph engine, and distances are measured along its route. The routing data omits street names, so national directions give compass orientation, turns, distances and the map line. The basemap retains visible street labels. Routes favor walking paths over busy roads and are not advertised as the absolute shortest path.

The walking profile excludes mapped private/no-access ways, motorways/trunks, ferries, fords, construction, and mountain paths tagged above ordinary hiking. This is not a complete access or hazard model: conditional restrictions and pedestrian-only one-way tags are not retained by this dataset, and untagged barriers or hazards may be missing. The source graph is a snapshot, not evidence of current passability. Water and resource records do not establish water quality, supplies, or facility operation.

Straight-line distance is labeled separately from walking miles. Gaps between the chosen endpoints and mapped walking paths are listed separately and excluded from walking mileage; gaps over 250 m are rejected. Disconnected networks return no route. Long routes have a 180-second/2 GiB calculation budget; if exceeded, choose intermediate destinations using the already-installed nationwide data. No further area download is required.

## Downloads, persistence and transfer

- `local-maps/us-z15.pmtiles`, `manifest.json`, `us-coverage.geojson`: independent copy of the local CRM Protomaps archive, with source and snapshot metadata.
- `local-maps/routing-us/`: all routing graph files, per-file receipts, and completion manifest. Missing/truncated files prevent a ready status. Partial downloads resume with checked HTTP byte ranges. Completed files are retained. Local SHA-256 hashes are recorded; these are not provider-signed checksums.
- Integrity: neither provider publishes checksums, so the hashes recorded at download time are the only reference. Startup only compares the basemap size with its manifest and reports a difference on the Maps tab; **Check setup** on a complete install re-hashes the basemap and every routing tile against those records (pausable, shown as “Checking US map files… N%”), deletes anything that no longer matches or lacks a receipt, and downloads only those files again.
- `runtime/brouter/`: pinned BRouter release and platform-specific Temurin Java 21 runtime, whose download is checked against the publisher's SHA-256.
- `resources/routing/`: versioned walking profile, lookup schema, coverage and BRouter license, included in packaged backend resources.
- `local-data/map-index/`: city/town index rebuilt entirely from the archive, offline.
- `local-data/`: saved position, settings, conversations and optional legacy imported map data.

Copy `local-maps/`, `runtime/`, `models/` and your `local-data/` to transfer a prepared workspace to the same OS/architecture. Packaged apps use their application-data workspace; source launchers use this repository. Prepare each platform's runtime while connected. Virtual environments are not portable. The Maps screen's **Choose basemap** attaches an external file in place; copy that external file too if used.

A fresh installation downloads the latest compatible Protomaps v4 daily build's US cutout using the pinned official PMTiles CLI. Extraction is verified before the file is published. An interrupted basemap extraction must be restarted; the much smaller routing files resume. Routing/search never trigger downloads. Only the explicit US setup action accesses the download providers. Once ready, clicking setup again is a no-op with no network requests.

## Model/download controls

The service exposes its active operation and progress. Conflicting buttons are disabled, including after a renderer reload. **Start model** remains disabled until a GGUF is selected and exists. The backend validates that file before stopping a working model. Completion/failure restores controls and updates the selected model automatically. Voice/model progress appears in Settings; it no longer appears as map preparation progress.

## Verification

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node electron/tests/atlas-protocol.cjs
node electron/tests/atlas.cjs
node electron/tests/operations.cjs
node electron/tests/smoke.cjs
```

Real file-only routes verified across all 50 states and DC: 102 walks, with every route checked against Census state boundaries. Additional routes include Philadelphia → New York (about 121 mapped miles) and Los Angeles → New York (about 3,367 mapped miles). UI tests use isolated data directories, block external HTTP(S), and check no default position, city/landmark discovery, explicit confirmation, grounded answers, map drawing, stale-route clearing and busy/download recovery. Runtime verification was on Apple silicon macOS; Windows/Linux download selection is implemented but not exercised on those systems.

## Sources and licenses

- [BRouter source and documentation](https://github.com/abrensch/brouter), MIT; [prebuilt routing data](https://brouter.de/brouter/segments4/), OpenStreetMap ODbL.
- [Protomaps downloads](https://docs.protomaps.com/basemaps/downloads) and [PMTiles extraction/verification](https://docs.protomaps.com/pmtiles/cli).
- [Eclipse Temurin releases](https://github.com/adoptium/temurin21-binaries), runtime license files retained in the extracted distribution.
- [US Census 2025 state boundaries](https://www.census.gov/geographies/mapping-files/2025/geo/carto-boundary-file.html), used to disambiguate city names and verify state coverage.
- [OpenStreetMap attribution](https://www.openstreetmap.org/copyright), [MapLibre](https://maplibre.org/maplibre-gl-js/docs/), [vector tile decoder](https://github.com/tilezen/mapbox-vector-tile).

Style/font licenses remain under `electron/map-assets/`. The app keeps source metadata with both datasets. No CRM customer data was copied.
