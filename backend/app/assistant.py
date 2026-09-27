import html
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _web_references(query: str) -> list[dict]:
    parameters = urlencode({
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': 3,
        'format': 'json',
        'utf8': 1,
    })
    request = Request(
        f'https://en.wikipedia.org/w/api.php?{parameters}',
        headers={'User-Agent': 'LandSyncAISpatialAssistant/1.0 (SIH prototype)'},
    )
    try:
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return []

    results = []
    for entry in payload.get('query', {}).get('search', []):
        snippet = re.sub(r'<[^>]+>', '', entry.get('snippet', ''))
        results.append({
            'title': entry.get('title', 'Reference'),
            'url': f"https://en.wikipedia.org/?curid={entry['pageid']}",
            'snippet': html.unescape(snippet),
        })
    return results


def _parcel_context(question: str, history: list[dict], parcels: list[dict]) -> tuple[dict | None, str | None]:
    search_text = ' '.join([question, *[item.get('content', '') for item in history[-8:]]])
    for parcel in parcels:
        if re.search(rf'(?<![\w-]){re.escape(parcel["id"])}(?![\w-])', search_text, re.IGNORECASE):
            return parcel, parcel['id']
    return None, None


def _parcel_summary(parcel: dict) -> str:
    assessment = parcel.get('assessment')
    identity = (
        f"Parcel {parcel['id']} is held by {parcel.get('owner', 'an unlisted holder')}, "
        f"has status '{parcel.get('status', 'Unknown')}', and comes from {parcel.get('source', 'an unspecified source')}."
    )
    if not assessment:
        return f"{identity} It has not been analyzed yet. Run Analyze boundaries for calculated spatial metrics."

    score = assessment.get('match_score', 0)
    details = []
    if assessment.get('comparison_type') == 'source_boundary_comparison':
        details.append(f"its cadastral/municipal IoU is {assessment['intersection_over_union_percent']:.2f}%")
        details.append(f"measured area delta is {assessment['geometry_area_delta_m2']:.2f} m2")
        details.append(f"boundary Hausdorff distance is {assessment['boundary_hausdorff_distance_m']:.2f} m")
    else:
        matches = assessment.get('candidate_matches', [])
        if matches:
            best = matches[0]
            details.append(f"nearest candidate is {best['parcel_id']} at {best['distance_m']:.2f} m with {best['intersection_over_union_percent']:.2f}% IoU")
        else:
            details.append(f"its measured footprint is {assessment.get('geometry_area_m2', 0):.2f} m2, with no nearby candidate")
    review_text = 'flagged for human review' if assessment.get('requires_review') else 'within the configured demo geometry thresholds'
    return f"{identity} Its computed spatial score is {score:.1f}% and it is {review_text}; " + '; '.join(details) + '. ' + ' '.join(assessment.get('reasons', []))


def answer_question(question: str, state: dict, history: list[dict]) -> dict:
    normalized = question.casefold()
    parcel, parcel_id = _parcel_context(question, history, state['parcels'])
    queue = state['queue']
    pending = sum(item['review_status'] not in {'Approved', 'Rejected'} for item in queue)
    flagged = [item for item in state.get('harmonization', []) if item.get('requires_review')]
    references = []

    if any(greeting in normalized.split() for greeting in ('hi', 'hello', 'hey')):
        answer = (
            'I can answer from this workspace. Ask about a parcel, spatial score, boundary flags, review cases, '
            'CRS imports, audit history, or how to use the workflow.'
        )
    elif normalized in {'help', 'what can you do', 'what do you do'}:
        answer = (
            'I inspect the loaded parcel records, explain geometry scores and review flags, summarize the review queue '
            'and audit log, explain supported CRS values, and describe the import workflow. I do not make legal ownership or boundary determinations.'
        )
    elif parcel and any(word in normalized for word in ('parcel', 'score', 'overlap', 'boundary', 'area', 'match', 'candidate', 'owner', 'status', 'source', 'this', 'it')):
        answer = _parcel_summary(parcel)
    elif any(word in normalized for word in ('crs', 'coordinate', 'epsg', 'projection', 'web mercator', 'utm')):
        answer = (
            'Geo Harmon-X accepts EPSG:4326, EPSG:3857, and WGS 84 UTM zones (EPSG:32601-32660 / EPSG:32701-32760). '
            'Imported polygons are converted to EPSG:4326 before storage and mapping. The CRS picker currently exposes EPSG:4326, EPSG:3857, and UTM zone 43 for the SIH demo.'
        )
        references = _web_references('coordinate reference system EPSG GeoJSON WGS 84')
    elif any(word in normalized for word in ('score', 'iou', 'intersection', 'threshold', 'weight', 'confidence', 'analysis method')):
        answer = (
            'The current score is a deterministic geometry heuristic, not a trained AI model: polygon IoU weighs 55%, area agreement 25%, and boundary agreement 20%. '
            'A comparison is flagged below 85% IoU, above 5% area delta, or beyond max(2 m, 2% of extent) boundary distance. These are demo thresholds, not legal/cadastral standards.'
        )
        references = _web_references('polygon intersection over union geospatial parcel boundary comparison')
    elif any(word in normalized for word in ('how many', 'count', 'pending', 'review queue', 'cases')):
        answer = f"The current workspace has {len(state['parcels'])} parcels, {len(queue)} review cases, and {pending} cases awaiting a final decision. {len(flagged)} of the latest spatial comparisons are flagged."
    elif any(word in normalized for word in ('how do i', 'how to', 'import', 'quick check', 'sample', 'use the app', 'button')):
        answer = (
            'Choose an input CRS, select a quick-check GeoJSON, and use the eye icon to inspect its features before importing. '
            'Import normalizes the geometry and runs harmonization. Review candidate evidence in Reconciliation, then approve/reject/escalate; the decision and rationale are retained in Audit log.'
        )
    elif any(word in normalized for word in ('postgis', 'database', 'sqlite', 'storage')):
        answer = (
            'The running workspace uses SQLite, which persists review and analysis data across restarts. '
            'PostGIS is optional: start backend/docker-compose.yml and set LANDSYNC_DATABASE_URL before starting FastAPI. '
            'This environment has no Docker/PostgreSQL executable, so the PostGIS connection cannot be verified here.'
        )
        references = _web_references('PostGIS documentation spatial database GiST index')
    else:
        references = _web_references(question)
        if references:
            answer = 'I searched current public web references. Here are the most relevant results; treat their snippets as starting points and verify standards against the issuing organization.'
        else:
            answer = (
                'I could not find a direct answer in the current workspace or reach a web reference for that question. '
                'I can inspect current parcel scores, CRS conversion, review cases, audit entries, the scoring thresholds, or the PostGIS setup.'
            )

    if parcel_id and not parcel:
        answer += f' I could not find parcel {parcel_id} in the current workspace.'
    return {'answer': answer, 'sources': references[:3], 'mode': 'workspace + public web retrieval'}