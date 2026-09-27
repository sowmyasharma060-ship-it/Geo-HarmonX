import json
from pathlib import Path

import pytest

from app.data import parcels
from app.geometry import GeometryInputError, WEB_MERCATOR_RADIUS_M, analyze_parcels, compare_geometries, find_candidate_matches, normalize_geometry


def test_identical_polygon_scores_full_agreement():
    polygon = {
        'type': 'Polygon',
        'coordinates': [[[77.2, 28.6], [77.2004, 28.6], [77.2004, 28.6003], [77.2, 28.6003], [77.2, 28.6]]],
    }

    result = compare_geometries(polygon, polygon)

    assert result['match_score'] == 100
    assert result['intersection_over_union_percent'] == 100
    assert result['geometry_area_delta_m2'] == 0
    assert result['requires_review'] is False


def test_demo_pairs_have_one_flagged_boundary_conflict():
    results = analyze_parcels(parcels)

    assert [result['requires_review'] for result in results] == [True, False, False]
    assert results[0]['geometry_area_delta_m2'] > 80
    assert results[0]['score_weights'] == {
        'overlap': 0.55,
        'area_agreement': 0.25,
        'boundary_agreement': 0.20,
    }
    assert results[0]['reasons']


def test_web_mercator_coordinates_normalize_to_wgs84():
    from math import log, pi, radians, tan

    longitude, latitude = 77.2, 28.6
    ring = [[longitude, latitude], [longitude + 0.001, latitude], [longitude + 0.001, latitude + 0.001], [longitude, latitude + 0.001], [longitude, latitude]]
    projected = [[WEB_MERCATOR_RADIUS_M * radians(x), WEB_MERCATOR_RADIUS_M * log(tan(pi / 4 + radians(y) / 2))] for x, y in ring]
    geometry = {'type': 'Polygon', 'coordinates': [projected]}

    normalized = normalize_geometry(geometry, 'EPSG:3857')

    assert normalized['type'] == 'Polygon'
    assert normalized['coordinates'][0][0][0] == pytest.approx(longitude, abs=1e-8)
    assert normalized['coordinates'][0][0][1] == pytest.approx(latitude, abs=1e-8)


def test_utm_central_meridian_converts_to_wgs84():
    geometry = {
        'type': 'Polygon',
        'coordinates': [[[500000, 0], [500100, 0], [500100, 100], [500000, 100], [500000, 0]]],
    }

    normalized = normalize_geometry(geometry, 'EPSG:32643')

    assert normalized['coordinates'][0][0][0] == pytest.approx(75, abs=1e-9)
    assert normalized['coordinates'][0][0][1] == pytest.approx(0, abs=1e-9)


def test_unknown_crs_is_rejected_instead_of_guessed():
    geometry = {'type': 'Polygon', 'coordinates': [[[77, 28], [77.1, 28], [77.1, 28.1], [77, 28]]]}

    with pytest.raises(GeometryInputError, match='not supported'):
        normalize_geometry(geometry, 'EPSG:999999')


def test_sample_upload_has_one_overlapping_candidate_and_one_isolated_parcel():
    sample_path = Path(__file__).parents[2] / 'frontend' / 'public' / 'sih-sample-parcels.geojson'
    features = json.loads(sample_path.read_text(encoding='utf-8'))['features']
    overlap_feature, isolated_feature = features

    candidates = find_candidate_matches(overlap_feature['geometry'], parcels, 'DEMO-OVERLAP-704')
    isolated = find_candidate_matches(isolated_feature['geometry'], parcels, 'DEMO-ISOLATED-2')

    assert candidates[0]['parcel_id'] == '704-B'
    assert candidates[0]['intersection_area_m2'] > 0
    assert isolated == []


def test_duplicate_sample_finds_exact_geometry_candidate():
    sample_path = Path(__file__).parents[2] / 'frontend' / 'public' / 'samples' / 'duplicate-candidate.geojson'
    feature = json.loads(sample_path.read_text(encoding='utf-8'))['features'][0]

    candidates = find_candidate_matches(feature['geometry'], parcels, feature['properties']['parcel_id'])

    assert candidates[0]['parcel_id'] == '704-B'
    assert candidates[0]['intersection_over_union_percent'] == 100


def test_nearby_sample_finds_nonoverlapping_candidate_within_tolerance():
    sample_path = Path(__file__).parents[2] / 'frontend' / 'public' / 'samples' / 'nearby-boundary.geojson'
    feature = json.loads(sample_path.read_text(encoding='utf-8'))['features'][0]

    candidates = find_candidate_matches(feature['geometry'], parcels, feature['properties']['parcel_id'])

    assert candidates[0]['parcel_id'] == '704-B'
    assert candidates[0]['distance_m'] <= 25
    assert candidates[0]['intersection_area_m2'] == 0


def test_web_mercator_sample_metadata_matches_its_coordinates():
    sample_path = Path(__file__).parents[2] / 'frontend' / 'public' / 'samples' / 'web-mercator.geojson'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    feature = sample['features'][0]

    normalized = normalize_geometry(feature['geometry'], sample['source_crs'])
    candidates = find_candidate_matches(normalized, parcels, feature['properties']['parcel_id'])

    assert normalized['coordinates'][0][0][0] == pytest.approx(77.208360, abs=1e-7)
    assert candidates[0]['parcel_id'] == '704-B'