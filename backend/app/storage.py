import json
import os
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

from app.data import audit_events, conflicts, overview, parcels, queue

DATABASE_PATH = Path(
    os.getenv(
        'LANDSYNC_DATABASE_PATH',
        '/tmp/landsync-demo.sqlite3' if os.getenv('VERCEL') else str(Path(__file__).with_name('landsync-demo.sqlite3')),
    )
)
_POSTGIS_READY = False
_POSTGIS_LOCK = Lock()


def storage_backend() -> str:
    return 'postgis' if os.environ.get('LANDSYNC_DATABASE_URL', '').startswith(('postgres://', 'postgresql://')) else 'sqlite'


def _seed_state() -> dict:
    return {
        'overview': deepcopy(overview),
        'parcels': deepcopy(parcels),
        'conflicts': deepcopy(conflicts),
        'queue': deepcopy(queue),
        'audit_events': deepcopy(audit_events),
        'harmonization': [],
        'schema_version': 3,
    }


def _upgrade_state(state: dict) -> bool:
    changed = False
    if state.get('schema_version', 0) < 2:
        seed_by_id = {parcel['id']: parcel for parcel in parcels}
        for parcel in state.get('parcels', []):
            seed = seed_by_id.get(parcel.get('id'))
            if seed and parcel.get('source') == seed.get('source'):
                for field in ('geometry', 'municipal_geometry', 'area', 'difference', 'recorded_area', 'municipal_area', 'coordinates'):
                    if field in seed:
                        parcel[field] = seed[field]
        state.setdefault('harmonization', [])
        state['schema_version'] = 2
        changed = True
    if state.get('schema_version', 0) < 3:
        for parcel in state.get('parcels', []):
            assessment = parcel.get('assessment')
            if assessment:
                parcel['spatial_score'] = assessment['match_score']
            else:
                parcel.pop('spatial_score', None)
            parcel.pop('confidence', None)
            parcel.pop('match', None)
        for event in state.get('audit_events', []):
            if event.get('id') == 'AUD-00421' and event.get('actor') == 'LandSync Harmon-X':
                event['detail'] = 'Sample cadastral and municipal source geometries are ready for analysis.'
        state['schema_version'] = 3
        changed = True
    return changed


def _postgres_dsn() -> str:
    return os.environ['LANDSYNC_DATABASE_URL'].replace('postgres://', 'postgresql://', 1)


def _postgres_connection():
    import pg8000.dbapi as pg8000

    global _POSTGIS_READY
    dsn = urlsplit(_postgres_dsn())
    if not dsn.hostname or not dsn.path.strip('/'):
        raise ValueError('LANDSYNC_DATABASE_URL must include a PostgreSQL host and database name.')
    connection = pg8000.connect(
        user=unquote(dsn.username or ''),
        password=unquote(dsn.password or ''),
        host=dsn.hostname,
        port=dsn.port or 5432,
        database=unquote(dsn.path.lstrip('/')),
    )
    if not _POSTGIS_READY:
        with _POSTGIS_LOCK:
            if not _POSTGIS_READY:
                _execute(connection, 'CREATE EXTENSION IF NOT EXISTS postgis').close()
                _execute(connection,
                    'CREATE TABLE IF NOT EXISTS landsync_application_state '
                    '(state_id SMALLINT PRIMARY KEY CHECK (state_id = 1), payload JSONB NOT NULL)'
                ).close()
                _execute(connection,
                    'CREATE TABLE IF NOT EXISTS landsync_parcel_geometries '
                    '(parcel_id TEXT NOT NULL, source_name TEXT NOT NULL, '
                    'geom geometry(Geometry, 4326) NOT NULL, '
                    'PRIMARY KEY (parcel_id, source_name))'
                ).close()
                _execute(connection,
                    'CREATE INDEX IF NOT EXISTS landsync_parcel_geometries_gix '
                    'ON landsync_parcel_geometries USING GIST (geom)'
                ).close()
                connection.commit()
                _POSTGIS_READY = True
    return connection


def _execute(connection, statement: str, parameters: tuple = ()):
    cursor = connection.cursor()
    cursor.execute(statement, parameters)
    return cursor


def _save_postgres(state: dict) -> None:
    connection = _postgres_connection()
    try:
        _execute(connection,
            'INSERT INTO landsync_application_state (state_id, payload) VALUES (1, %s::jsonb) '
            'ON CONFLICT (state_id) DO UPDATE SET payload = EXCLUDED.payload',
            (json.dumps(state),),
        ).close()
        _execute(connection, 'DELETE FROM landsync_parcel_geometries').close()
        for parcel in state['parcels']:
            for source_name, geometry_field in (
                ('cadastral', 'geometry'),
                ('municipal', 'municipal_geometry'),
            ):
                geometry = parcel.get(geometry_field)
                if geometry:
                    _execute(connection,
                        'INSERT INTO landsync_parcel_geometries (parcel_id, source_name, geom) '
                        'VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) '
                        'ON CONFLICT (parcel_id, source_name) DO UPDATE SET geom = EXCLUDED.geom',
                        (parcel['id'], source_name, json.dumps(geometry)),
                    ).close()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _load_sqlite() -> dict:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS application_state '
            '(state_id INTEGER PRIMARY KEY CHECK (state_id = 1), payload TEXT NOT NULL)'
        )
        row = connection.execute(
            'SELECT payload FROM application_state WHERE state_id = 1'
        ).fetchone()
        if row is None:
            state = _seed_state()
            connection.execute(
                'INSERT INTO application_state (state_id, payload) VALUES (1, ?)',
                (json.dumps(state),),
            )
            return state
        return json.loads(row[0])


def load_state() -> dict:
    if storage_backend() == 'postgis':
        connection = _postgres_connection()
        try:
            cursor = _execute(connection,
                'SELECT payload FROM landsync_application_state WHERE state_id = 1'
            )
            row = cursor.fetchone()
            cursor.close()
        finally:
            connection.close()
        if row is None:
            state = _seed_state()
            save_state(state)
            return state
        state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        if _upgrade_state(state):
            save_state(state)
        return state

    state = _load_sqlite()
    if _upgrade_state(state):
        save_state(state)
    return state


def save_state(state: dict) -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS application_state '
            '(state_id INTEGER PRIMARY KEY CHECK (state_id = 1), payload TEXT NOT NULL)'
        )
        connection.execute(
            'INSERT INTO application_state (state_id, payload) VALUES (1, ?) '
            'ON CONFLICT(state_id) DO UPDATE SET payload = excluded.payload',
            (json.dumps(state),),
        )
