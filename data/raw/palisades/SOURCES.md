# Palisades demo data sources

Demo bounding box: `-118.72,33.99,-118.46,34.16` (WGS84).

| File | Source | Notes |
|---|---|---|
| `fire_progression_lafd.geojson` | [LAFD Palisades Fire Progression](https://services.arcgis.com/xsiPoFK0f7RrxF0D/arcgis/rest/services/Palisades_Fire_Progression/FeatureServer) | 11 timestamped perimeter polygons, January 7–11, 2025. |
| `roads_osm_overpass.json` | [OpenStreetMap Overpass API](https://overpass-api.de/) | Drivable-road extract for the demo bounding box. ODbL attribution required. |
| `elevation_usgs_3dep.tif` | [USGS 3DEP Elevation ImageServer](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer) | 1,400×920 float elevation raster in WGS84. |
| `airnow_*.dat` | [EPA AirNow historical files](https://files.airnowtech.org/) | Daily observations for January 7–11, 2025. PM2.5 is used as the initial smoke-risk proxy. |
| `airnow_monitoring_sites.dat` | [EPA AirNow historical files](https://files.airnowtech.org/) | Monitoring station metadata and coordinates. |

NASA FIRMS historical VIIRS detections are not included yet because archive/API access requires a NASA Earthdata account or FIRMS MAP_KEY. Do not commit a MAP_KEY; add it through `.env` when available.

## Redis replay contract

`scripts/replay_palisades_to_redis.py` writes every normalized event to the `aegis:events` Redis stream, updates `aegis:state:<event_type>`, and publishes the full envelope on `aegis:updates`. Synthetic SAR events are labeled with `"synthetic": true`.
