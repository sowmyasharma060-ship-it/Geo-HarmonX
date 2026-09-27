from math import log, pi, radians, tan

import pytest
from fastapi.testclient import TestClient

from app import data, storage
from app.geometry import WEB_MERCATOR_RADIUS_M
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATABASE_PATH', tmp_path / 'test.sqlite3')
    with TestClient(app) as test_client:
        yield test_client


def feature_collection(parcel_id='TEST-1', area=120):
    return {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'properties': {'parcel_id': parcel_id, 'area': area, 'owner': 'Test owner'},
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[[77, 28], [77.1, 28], [77.1, 28.1], [77, 28]]],
            },
        }],
    }


def test_geojson_import_creates_parcel_queue_and_audit_event(client):
    seed_ids = [parcel['id'] for parcel in data.parcels]
    response = client.post('/api/ingest', json=feature_collection())

    assert response.status_code == 200
    assert response.json()['imported_count'] == 1
    assert client.get('/api/parcel/TEST-1').status_code == 200
    assert client.get('/api/review-queue').json()[0]['case_id'] == 'P-TEST-1'
    assert client.get('/api/audit').json()[0]['action'] == 'GeoJSON imported'
    assert [parcel['id'] for parcel in data.parcels] == seed_ids


def test_geojson_import_rejects_unclosed_ring(client):
    payload = feature_collection()
    payload['features'][0]['geometry']['coordinates'][0][-1] = [77.05, 28.05]

    response = client.post('/api/ingest', json=payload)

    assert response.status_code == 422


def test_geojson_import_reprojects_web_mercator_coordinates(client):
    payload = feature_collection()
    ring = payload['features'][0]['geometry']['coordinates'][0]
    payload['features'][0]['geometry']['coordinates'] = [[[
        WEB_MERCATOR_RADIUS_M * radians(longitude),
        WEB_MERCATOR_RADIUS_M * log(tan(pi / 4 + radians(latitude) / 2)),
    ] for longitude, latitude in ring]]

    response = client.post('/api/ingest?source_crs=EPSG:3857', json=payload)

    assert response.status_code == 200
    first_position = response.json()['parcels'][0]['geometry']['coordinates'][0][0]
    assert first_position[0] == pytest.approx(77, abs=1e-8)
    assert first_position[1] == pytest.approx(28, abs=1e-8)


def test_harmonize_returns_explainable_metrics_and_persists_audit(client):
    response = client.post('/api/harmonize')

    assert response.status_code == 200
    result = response.json()
    assert result['analyzed_count'] == 3
    assert result['flagged_count'] == 1
    assert [item['requires_review'] for item in result['assessments']] == [True, False, False]
    assert result['assessments'][0]['score_weights']['overlap'] == 0.55
    assert result['assessments'][0]['reasons']
    assert len(client.get('/api/harmonization').json()) == 3
    assert client.get('/api/audit').json()[0]['action'] == 'Spatial harmonization run'


def test_postgis_backend_is_selected_from_environment(monkeypatch):
    monkeypatch.setenv('LANDSYNC_DATABASE_URL', 'postgresql://landsync@localhost/landsync')

    assert storage.storage_backend() == 'postgis'


def test_sqlite_remains_the_default_backend(monkeypatch):
    monkeypatch.delenv('LANDSYNC_DATABASE_URL', raising=False)

    assert storage.storage_backend() == 'sqlite'


def test_assistant_remembers_parcel_context_after_api_client_restart(client):
    first = client.post('/api/assistant/chat', json={
        'session_id': 'test-session-1234',
        'message': 'Tell me about parcel 704-B.',
    })
    assert first.status_code == 200
    assert '704-B' in first.json()['reply']

    with TestClient(app) as restarted_client:
        follow_up = restarted_client.post('/api/assistant/chat', json={
            'session_id': 'test-session-1234',
            'message': 'What is its score?',
        })

    assert follow_up.status_code == 200
    assert '704-B' in follow_up.json()['reply']
    assert 'not been analyzed yet' in follow_up.json()['reply']
    assert follow_up.json()['remembered_messages'] == 4
    history = restarted_client.get('/api/assistant/session/test-session-1234')
    assert len(history.json()['messages']) == 4


def test_assistant_rejects_invalid_session_identifiers(client):
    response = client.post('/api/assistant/chat', json={
        'session_id': 'bad session id',
        'message': 'How do I import a parcel?',
    })

    assert response.status_code == 422


def test_local_frontend_ports_can_call_api(client):
    response = client.options(
        '/api/overview',
        headers={
            'Origin': 'http://localhost:5174',
            'Access-Control-Request-Method': 'GET',
        },
    )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5174'


def test_assistant_answers_with_grounded_parcel_identity(client):
    response = client.post('/api/assistant/chat', json={
        'session_id': 'grounded-test-123',
        'message': 'Who owns parcel 704-B and what is its status?',
    })

    assert response.status_code == 200
    assert 'Heritage Realty Corp' in response.json()['reply']
    assert 'Inspection Complete' in response.json()['reply']


def test_review_decision_updates_metrics_and_is_audited(client):
    pending_before = int(client.get('/api/overview').json()['metrics'][2]['value'])
    response = client.post('/api/review/P-704-B', json={'decision': 'approve', 'actor': 'Test Officer'})

    assert response.status_code == 200
    assert response.json()['review_status'] == 'Approved'
    pending_after = int(client.get('/api/overview').json()['metrics'][2]['value'])
    assert pending_after == pending_before - 1
    assert client.get('/api/audit').json()[0]['actor'] == 'Test Officer'
    assert client.post('/api/review/P-704-B', json={'decision': 'reject'}).status_code == 409
