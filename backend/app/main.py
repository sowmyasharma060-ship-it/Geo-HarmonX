from datetime import datetime, timezone
from math import isfinite
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.assistant import answer_question
from app.geometry import GeometryInputError, analyze_parcels, normalize_geometry
from app.storage import load_state, save_state, storage_backend

app = FastAPI(title='LandSync AI', version='0.1.0')

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        'LANDSYNC_CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173',
    ).split(',')
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


class ReviewDecision(BaseModel):
    decision: Literal['approve', 'reject', 'escalate']
    actor: str = Field(default='Review Officer', min_length=1, max_length=100)
    note: str = Field(default='', max_length=1000)


class AssistantChat(BaseModel):
    session_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    message: str = Field(min_length=1, max_length=2000)


def add_audit_event(state: dict, action: str, parcel_id: str, actor: str, detail: str) -> None:
    latest_id = max((int(event['id'].split('-')[1]) for event in state['audit_events']), default=0)
    state['audit_events'].insert(0, {
        'id': f'AUD-{latest_id + 1:05d}',
        'action': action,
        'parcel_id': parcel_id,
        'actor': actor,
        'detail': detail,
        'time': datetime.now(timezone.utc).isoformat(timespec='minutes'),
    })


def valid_ring(ring: object) -> bool:
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    points = []
    for point in ring:
        if (
            not isinstance(point, list)
            or len(point) < 2
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in point[:2])
        ):
            return False
        if not all(isfinite(value) for value in point[:2]):
            return False
        points.append(point[:2])
    return points[0] == points[-1]


def valid_geometry(geometry: dict) -> bool:
    coordinates = geometry.get('coordinates')
    if not isinstance(coordinates, list):
        return False
    polygons = [coordinates] if geometry['type'] == 'Polygon' else coordinates
    return bool(polygons) and all(
        isinstance(polygon, list) and bool(polygon) and all(valid_ring(ring) for ring in polygon)
        for polygon in polygons
    )


@app.get('/')
def root():
    return {'message': 'LandSync AI backend is running'}


@app.get('/health')
@app.get('/api/health')
def health():
    return {'status': 'ok', 'storage': storage_backend(), 'geometry_engine': 'shapely'}


@app.get('/api/overview')
def get_overview():
    state = load_state()
    pending = sum(item['review_status'] not in {'Approved', 'Rejected'} for item in state['queue'])
    resolved = sum(item['review_status'] == 'Approved' for item in state['queue'])
    return {
        **state['overview'],
        'metrics': [
            {'label': 'Parcels in demo', 'value': str(len(state['parcels'])), 'tone': 'info'},
            {'label': 'Review cases', 'value': str(len(state['queue'])), 'tone': 'highlight'},
            {'label': 'Awaiting decision', 'value': str(pending), 'tone': 'warning'},
            {'label': 'Approved', 'value': str(resolved), 'tone': 'success'},
        ],
    }


@app.get('/api/parcels')
def get_parcels():
    return load_state()['parcels']


@app.get('/api/conflicts')
def get_conflicts():
    return load_state()['conflicts']


@app.get('/api/review-queue')
def get_review_queue():
    return load_state()['queue']


@app.get('/api/audit')
def get_audit_events():
    return load_state()['audit_events']


@app.get('/api/harmonization')
def get_harmonization():
    return load_state().get('harmonization', [])


@app.post('/api/assistant/chat')
def assistant_chat(message: AssistantChat):
    state = load_state()
    sessions = state.setdefault('assistant_sessions', {})
    history = sessions.get(message.session_id, [])
    result = answer_question(message.message, state, history)
    history.extend([
        {'role': 'user', 'content': message.message},
        {'role': 'assistant', 'content': result['answer'], 'sources': result['sources']},
    ])
    sessions[message.session_id] = history[-40:]
    save_state(state)
    return {
        'session_id': message.session_id,
        'reply': result['answer'],
        'sources': result['sources'],
        'mode': result['mode'],
        'remembered_messages': len(sessions[message.session_id]),
    }


@app.get('/api/assistant/session/{session_id}')
def get_assistant_session(session_id: str = PathParam(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')):
    state = load_state()
    return {'session_id': session_id, 'messages': state.get('assistant_sessions', {}).get(session_id, [])}


@app.get('/api/parcel/{parcel_id}')
def get_parcel(parcel_id: str):
    for parcel in load_state()['parcels']:
        if parcel['id'].lower() == parcel_id.lower():
            return parcel
    raise HTTPException(status_code=404, detail='Parcel not found')


@app.post('/api/review/{case_id}')
def decide_review(case_id: str, decision: ReviewDecision):
    state = load_state()
    case = next((item for item in state['queue'] if item['case_id'].lower() == case_id.lower()), None)
    if case is None:
        raise HTTPException(status_code=404, detail='Review case not found')
    if case['review_status'] in {'Approved', 'Rejected'}:
        raise HTTPException(status_code=409, detail='This review case is already closed.')

    new_status = {
        'approve': 'Approved',
        'reject': 'Rejected',
        'escalate': 'Escalated for validation',
    }[decision.decision]
    case['review_status'] = new_status
    action = decision.decision.capitalize()
    detail = decision.note or f'Review case status changed to {new_status}.'
    add_audit_event(state, action, case['parcel_id'], decision.actor, detail)
    save_state(state)
    return case


@app.post('/api/harmonize')
def run_harmonization():
    state = load_state()
    assessments = analyze_parcels(state['parcels'])
    queue_by_parcel = {item['parcel_id']: item for item in state['queue']}

    for assessment in assessments:
        parcel_id = assessment['parcel_id']
        parcel = next((item for item in state['parcels'] if item['id'] == parcel_id), None)
        if parcel is None:
            continue
        parcel['assessment'] = assessment
        parcel['analysis_status'] = 'Review recommended' if assessment['requires_review'] else 'Within demo tolerances'
        parcel['spatial_score'] = assessment['match_score']
        parcel.pop('confidence', None)
        parcel.pop('match', None)

        case = queue_by_parcel.get(parcel_id)
        if assessment['requires_review'] and case and case['review_status'] not in {'Approved', 'Rejected'}:
            case['issue'] = ' '.join(assessment['reasons'])
        elif assessment['requires_review'] and not case:
            case = {
                'case_id': f'P-{parcel_id}',
                'parcel_id': parcel_id,
                'owner': parcel.get('owner', 'Not provided'),
                'issue': ' '.join(assessment['reasons']),
                'review_status': 'Awaiting officer review',
            }
            state['queue'].insert(0, case)
            queue_by_parcel[parcel_id] = case

    state['harmonization'] = assessments
    flagged_count = sum(item['requires_review'] for item in assessments)
    add_audit_event(
        state,
        'Spatial harmonization run',
        'DISTRICT',
        'LandSync geometry engine',
        f'Analyzed {len(assessments)} parcel geometries; {flagged_count} comparisons were flagged for human review.',
    )
    save_state(state)
    return {
        'analyzed_count': len(assessments),
        'flagged_count': flagged_count,
        'assessment_method': 'Shapely topology with local spherical Lambert azimuthal equal-area measurements',
        'assessments': assessments,
    }


@app.post('/api/ingest')
def ingest_geojson(payload: dict, source_crs: str = Query(default='EPSG:4326', max_length=32)):
    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        raise HTTPException(status_code=422, detail='Upload a GeoJSON FeatureCollection.')
    features = payload['features']
    if not features or len(features) > 1000:
        raise HTTPException(status_code=422, detail='FeatureCollection must contain 1 to 1000 features.')

    imported = []
    state = load_state()
    existing_ids = {parcel['id'].lower() for parcel in state['parcels']}
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict) or feature.get('type') != 'Feature':
            raise HTTPException(status_code=422, detail=f'Feature {index} is invalid.')
        geometry = feature.get('geometry')
        if not isinstance(geometry, dict) or geometry.get('type') not in {'Polygon', 'MultiPolygon'}:
            raise HTTPException(status_code=422, detail=f'Feature {index} needs Polygon or MultiPolygon geometry.')
        if not valid_geometry(geometry):
            raise HTTPException(status_code=422, detail=f'Feature {index} has invalid coordinates or an unclosed boundary ring.')
        try:
            normalized_geometry = normalize_geometry(geometry, source_crs)
        except GeometryInputError as error:
            raise HTTPException(status_code=422, detail=f'Feature {index}: {error}') from error
        properties = feature.get('properties') or {}
        if not isinstance(properties, dict):
            raise HTTPException(status_code=422, detail=f'Feature {index} properties must be an object.')
        parcel_id = str(properties.get('parcel_id') or properties.get('id') or f"IMPORT-{len(state['parcels']) + len(imported) + 1}")
        if parcel_id.lower() in existing_ids:
            raise HTTPException(status_code=409, detail=f'Parcel {parcel_id} already exists.')
        existing_ids.add(parcel_id.lower())
        try:
            area = float(properties.get('area') or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f'Feature {index} area must be a number.') from None
        if not isfinite(area) or area < 0:
            raise HTTPException(status_code=422, detail=f'Feature {index} area must be a finite, non-negative number.')
        imported.append({
            'id': parcel_id,
            'status': 'Needs review',
            'priority': 'Medium',
            'source': str(properties.get('source') or 'Uploaded GeoJSON'),
            'area': area,
            'difference': 0,
            'drift': 0,
            'owner': str(properties.get('owner') or 'Not provided'),
            'recorded_area': area,
            'municipal_area': area,
            'resolution': 'Imported; pending harmonization',
            'geometry': normalized_geometry,
            'source_crs': source_crs,
            'normalized_crs': 'EPSG:4326',
            'coordinates': None,
        })

    state['parcels'].extend(imported)
    for parcel in imported:
        case_id = f"P-{parcel['id']}"
        state['queue'].insert(0, {
            'case_id': case_id,
            'parcel_id': parcel['id'],
            'owner': parcel['owner'],
            'issue': 'New geometry imported; run harmonization and verify source attributes.',
            'review_status': 'Awaiting officer review',
        })
        add_audit_event(state, 'GeoJSON imported', parcel['id'], 'Dataset Analyst', 'Feature added to the review queue.')
    save_state(state)
    return {'imported_count': len(imported), 'parcels': imported}
