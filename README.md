# LandSync AI · Geo Harmon-X

SIH 2026 prototype for harmonizing multi-source urban land parcel records. The application overlays source boundaries, calculates explainable spatial differences, routes uncertain cases for human review, and records a provenance trail.

> This workspace uses fictional demonstration data. Match scores and recommendations are illustrative only; they are not legal findings, official records, or a substitute for a licensed survey and authorized officer decision.

## Run locally

Requirements: Node.js 18+ and Python 3.10+.

Start the API in one terminal:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Start the web app in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. OpenAPI docs are at `http://localhost:8000/docs`.

## Demo workflow

1. Use Overview to see the district snapshot, OSM map, source-boundary overlays, and pending reviews.
2. Choose Parcel map to search/filter parcels, toggle cadastral and municipal layers, select a boundary, and export the inventory as CSV.
3. Choose the incoming coordinate system (EPSG:4326, EPSG:3857, or UTM zone 43N). Select one of four quick-check GeoJSON files beside Import GeoJSON; use the eye control to inspect properties and geometry before importing. Analyze boundaries is next to Export CSV.
4. The samples cover overlap/isolated records, exact duplicate candidates, nearby boundaries, and EPSG:3857 reprojection. Import automatically normalizes to WGS 84 and runs spatial comparison. Review evidence, then approve, reject, or escalate. Closed approvals/rejections cannot be changed through the API.
5. Open the floating LandSync assistant to ask about workspace parcels, scores, CRS, thresholds, or workflow. It remembers the last 20 message turns in local SQLite and can fetch public Wikipedia search snippets for general geospatial questions.
6. Choose Audit log to review the action, parcel, actor, and detail recorded for each import and decision.

The map uses public OpenStreetMap tiles and requires an internet connection. Use **Download sample** in the app to get a ready-to-import GeoJSON file. Input must be a FeatureCollection with Polygon or MultiPolygon boundaries and closed rings. The CRS selector supports EPSG:4326, EPSG:3857, and WGS 84 UTM zones (EPSG:32601-32660 and EPSG:32701-32760). Imports are limited to 1,000 features per request.

The geometry engine measures local parcel pairs in a spherical Lambert azimuthal equal-area projection and reports polygon IoU, per-source coverage, area delta, and boundary Hausdorff distance. Its deterministic score weights overlap at 55%, area agreement at 25%, and boundary agreement at 20%. Review flags use an 85% minimum IoU target, a 5% maximum area-delta target, and a boundary tolerance of the greater of 2 m or 2% of parcel extent. These are demonstration thresholds, not cadastral standards.

## API

- `GET /health`
- `GET /api/overview`
- `GET /api/parcels`
- `GET /api/parcel/{parcel_id}`
- `GET /api/conflicts`
- `GET /api/review-queue`
- `GET /api/audit`
- `GET /api/harmonization`
- `GET /api/assistant/session/{session_id}`
- `POST /api/assistant/chat`
- `POST /api/ingest?source_crs=EPSG:4326` (also supports EPSG:3857 and UTM EPSG codes listed above)
- `POST /api/harmonize`
- `POST /api/review/{case_id}` with `decision` equal to `approve`, `reject`, or `escalate`

## Current architecture and limits

- React + Vite, Leaflet / React Leaflet, and OpenStreetMap tiles
- FastAPI API with durable SQLite by default; set `LANDSYNC_DATABASE_URL` to select PostGIS, which stores JSON application state plus SRID 4326 source geometries in a GIST-indexed table
- Shapely computes deterministic polygon comparisons; CRS normalization is implemented for WGS 84, Web Mercator, and WGS 84 UTM zones
- Scores and source records are demo-only. There is no trained ML model, user authentication, government data connector, raster processing, cryptographic ledger, or legal validation
- The assistant is a deterministic workspace Q&A and web-retrieval tool, not a pretrained or generative model; public reference search uses Wikipedia's API and needs internet access
- The engine identifies geometric agreement/candidates only; it does not establish parcel identity, ownership, title, or legal boundary

### Optional PostGIS

Docker Desktop is required. From PowerShell:

```powershell
cd backend
docker compose up -d postgis
$env:LANDSYNC_DATABASE_URL = "postgresql://landsync:landsync-local-dev-only@localhost:5432/landsync"
python -m uvicorn app.main:app --reload --port 8000
```

The Compose service applies `backend/migrations/001_postgis.sql` on first database creation. The example password is for local development only. SQLite remains active unless `LANDSYNC_DATABASE_URL` is set before starting FastAPI.

Before real deployment, add role-based identity and department authorization, durable immutable audit records, approved government data connectors, and validation with the relevant land authority and survey standards. The local PostGIS option is configured but requires a reachable PostGIS server; it cannot be exercised in environments without Docker/PostgreSQL.

## Tests

From the backend directory after installing `requirements-dev.txt`:

```powershell
pytest
```
