CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS landsync_application_state (
    state_id SMALLINT PRIMARY KEY CHECK (state_id = 1),
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS landsync_parcel_geometries (
    parcel_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    geom geometry(Geometry, 4326) NOT NULL,
    PRIMARY KEY (parcel_id, source_name)
);

CREATE INDEX IF NOT EXISTS landsync_parcel_geometries_gix
    ON landsync_parcel_geometries USING GIST (geom);
