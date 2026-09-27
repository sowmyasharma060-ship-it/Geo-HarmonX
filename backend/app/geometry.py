from math import atan, atan2, cos, degrees, exp, isfinite, log, pi, radians, sin, sqrt, tan
import re
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import transform

EARTH_RADIUS_M = 6371008.8
WEB_MERCATOR_RADIUS_M = 6378137.0
SCORE_WEIGHTS = {'overlap': 0.55, 'area_agreement': 0.25, 'boundary_agreement': 0.20}
REVIEW_THRESHOLDS = {'minimum_iou_percent': 85.0, 'maximum_area_delta_percent': 5.0}


class GeometryInputError(ValueError):
    pass


def _crs_transformer(source_crs: str):
    normalized = source_crs.strip().upper().replace(' ', '')
    match = re.fullmatch(r'(?:EPSG:)?(\d+)', normalized)
    if not match:
        raise GeometryInputError('CRS must be specified as an EPSG code.')
    epsg = int(match.group(1))
    if epsg == 4326:
        return lambda x, y: (x, y)
    if epsg == 3857:
        def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
            longitude = degrees(x / WEB_MERCATOR_RADIUS_M)
            latitude = degrees(2 * atan(exp(y / WEB_MERCATOR_RADIUS_M)) - pi / 2)
            return longitude, latitude
        return web_mercator_to_wgs84
    if 32601 <= epsg <= 32660 or 32701 <= epsg <= 32760:
        northern = epsg < 32700
        zone = epsg - (32600 if northern else 32700)
        return lambda x, y: _utm_to_wgs84(x, y, zone, northern)
    raise GeometryInputError(f'EPSG:{epsg} is not supported. Use EPSG:4326, EPSG:3857, or a WGS 84 UTM zone.')


def _utm_to_wgs84(easting: float, northing: float, zone: int, northern: bool) -> tuple[float, float]:
    semi_major = 6378137.0
    eccentricity_squared = 0.00669437999014
    scale = 0.9996
    x = easting - 500000.0
    y = northing if northern else northing - 10000000.0
    eccentricity_prime_squared = eccentricity_squared / (1 - eccentricity_squared)
    e1 = (1 - sqrt(1 - eccentricity_squared)) / (1 + sqrt(1 - eccentricity_squared))
    meridian = y / scale
    mu = meridian / (semi_major * (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256))
    footpoint = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * sin(4 * mu)
        + (151 * e1**3 / 96) * sin(6 * mu)
        + (1097 * e1**4 / 512) * sin(8 * mu)
    )
    sin_footpoint = sin(footpoint)
    cos_footpoint = cos(footpoint)
    tan_footpoint = tan(footpoint)
    radius = semi_major * (1 - eccentricity_squared) / (1 - eccentricity_squared * sin_footpoint**2) ** 1.5
    prime_vertical = semi_major / sqrt(1 - eccentricity_squared * sin_footpoint**2)
    tangent_squared = tan_footpoint**2
    curvature = eccentricity_prime_squared * cos_footpoint**2
    d = x / (prime_vertical * scale)
    latitude = footpoint - (prime_vertical * tan_footpoint / radius) * (
        d**2 / 2
        - (5 + 3 * tangent_squared + 10 * curvature - 4 * curvature**2 - 9 * eccentricity_prime_squared) * d**4 / 24
        + (61 + 90 * tangent_squared + 298 * curvature + 45 * tangent_squared**2 - 252 * eccentricity_prime_squared - 3 * curvature**2) * d**6 / 720
    )
    longitude = radians((zone - 1) * 6 - 180 + 3) + (
        d
        - (1 + 2 * tangent_squared + curvature) * d**3 / 6
        + (5 - 2 * curvature + 28 * tangent_squared - 3 * curvature**2 + 8 * eccentricity_prime_squared + 24 * tangent_squared**2) * d**5 / 120
    ) / cos_footpoint
    return degrees(longitude), degrees(latitude)


def normalize_geometry(geojson_geometry: dict[str, Any], source_crs: str = 'EPSG:4326') -> dict[str, Any]:
    try:
        convert = _crs_transformer(source_crs)
        geometry = shape(geojson_geometry)
    except Exception as error:
        raise GeometryInputError(f'Could not parse geometry or CRS: {error}') from error

    if geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
        raise GeometryInputError('Only Polygon and MultiPolygon geometries are supported.')
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise GeometryInputError('Geometry must be a valid, non-empty polygon with positive area.')

    geometry = transform(convert, geometry)

    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise GeometryInputError('Geometry is invalid after conversion to WGS 84.')
    west, south, east, north = geometry.bounds
    if not all(isfinite(value) for value in geometry.bounds) or not (-180 <= west <= east <= 180) or not (-90 <= south <= north <= 90):
        raise GeometryInputError('Converted geometry falls outside valid WGS 84 longitude/latitude bounds.')
    return mapping(geometry)


def _projected(geometry: dict[str, Any], center_lon: float, center_lat: float):
    try:
        parsed = shape(geometry)
    except Exception as error:
        raise GeometryInputError(f'Could not parse polygon: {error}') from error
    if parsed.geom_type not in {'Polygon', 'MultiPolygon'} or parsed.is_empty or not parsed.is_valid or parsed.area <= 0:
        raise GeometryInputError('Geometry must be a valid, non-empty polygon with positive area.')
    center_lon_rad = radians(center_lon)
    center_lat_rad = radians(center_lat)
    sin_center = sin(center_lat_rad)
    cos_center = cos(center_lat_rad)

    def project(longitude: float, latitude: float):
        longitude_rad = radians(longitude)
        latitude_rad = radians(latitude)
        delta_longitude = longitude_rad - center_lon_rad
        denominator = 1 + sin_center * sin(latitude_rad) + cos_center * cos(latitude_rad) * cos(delta_longitude)
        if denominator <= 0:
            raise GeometryInputError('Geometry is too far from the selected local map area.')
        scale = sqrt(2 / denominator)
        x = EARTH_RADIUS_M * scale * cos(latitude_rad) * sin(delta_longitude)
        y = EARTH_RADIUS_M * scale * (cos_center * sin(latitude_rad) - sin_center * cos(latitude_rad) * cos(delta_longitude))
        return x, y

    projected = transform(project, parsed)
    if projected.is_empty or not projected.is_valid or projected.area <= 0:
        raise GeometryInputError('Geometry could not be measured in the equal-area projection.')
    return projected


def measure_geometry_area(geometry: dict[str, Any]) -> float:
    parsed = shape(geometry)
    center = parsed.centroid
    return round(_projected(geometry, center.x, center.y).area, 2)


def compare_geometries(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_shape = shape(first)
    second_shape = shape(second)
    center = first_shape.union(second_shape).centroid
    left = _projected(first, center.x, center.y)
    right = _projected(second, center.x, center.y)
    intersection_area = left.intersection(right).area
    union_area = left.union(right).area
    left_area = left.area
    right_area = right.area
    area_delta = abs(left_area - right_area)
    area_delta_percent = area_delta / max(left_area, right_area) * 100
    iou_percent = intersection_area / union_area * 100 if union_area else 0
    area_agreement_percent = min(left_area, right_area) / max(left_area, right_area) * 100
    boundary_distance = left.boundary.hausdorff_distance(right.boundary)
    left_bounds = left.bounds
    right_bounds = right.bounds
    extent = max(
        left_bounds[2] - left_bounds[0],
        left_bounds[3] - left_bounds[1],
        right_bounds[2] - right_bounds[0],
        right_bounds[3] - right_bounds[1],
    )
    boundary_tolerance = max(2.0, extent * 0.02)
    boundary_agreement_percent = max(0.0, 1 - boundary_distance / boundary_tolerance) * 100
    score = (
        SCORE_WEIGHTS['overlap'] * iou_percent
        + SCORE_WEIGHTS['area_agreement'] * area_agreement_percent
        + SCORE_WEIGHTS['boundary_agreement'] * boundary_agreement_percent
    )

    reasons = []
    if iou_percent < REVIEW_THRESHOLDS['minimum_iou_percent']:
        reasons.append(f'Boundary intersection-over-union is {iou_percent:.1f}%, below the 85% review target.')
    if area_delta_percent > REVIEW_THRESHOLDS['maximum_area_delta_percent']:
        reasons.append(f'Equal-area polygon measurements differ by {area_delta_percent:.1f}%, above the 5% review target.')
    if boundary_distance > boundary_tolerance:
        reasons.append(f'Boundary Hausdorff distance is {boundary_distance:.2f} m, above the {boundary_tolerance:.2f} m tolerance.')
    if not reasons:
        reasons.append('Overlap, polygon area, and boundary distance meet the configured demo thresholds.')

    return {
        'match_score': round(score, 1),
        'intersection_over_union_percent': round(iou_percent, 2),
        'first_coverage_percent': round(intersection_area / left_area * 100, 2),
        'second_coverage_percent': round(intersection_area / right_area * 100, 2),
        'first_geometry_area_m2': round(left_area, 2),
        'second_geometry_area_m2': round(right_area, 2),
        'intersection_area_m2': round(intersection_area, 2),
        'union_area_m2': round(union_area, 2),
        'geometry_area_delta_m2': round(area_delta, 2),
        'geometry_area_delta_percent': round(area_delta_percent, 2),
        'area_agreement_percent': round(area_agreement_percent, 2),
        'boundary_hausdorff_distance_m': round(boundary_distance, 2),
        'boundary_tolerance_m': round(boundary_tolerance, 2),
        'boundary_agreement_percent': round(boundary_agreement_percent, 2),
        'measurement_method': 'Local spherical Lambert azimuthal equal-area projection',
        'score_weights': SCORE_WEIGHTS,
        'requires_review': bool(
            iou_percent < REVIEW_THRESHOLDS['minimum_iou_percent']
            or area_delta_percent > REVIEW_THRESHOLDS['maximum_area_delta_percent']
            or boundary_distance > boundary_tolerance
        ),
        'reasons': reasons,
    }


def find_candidate_matches(
    geometry: dict[str, Any],
    candidates: list[dict[str, Any]],
    exclude_id: str,
    maximum_distance_m: float = 25.0,
) -> list[dict[str, Any]]:
    matches = []
    for candidate in candidates:
        if candidate['id'] == exclude_id or not candidate.get('geometry'):
            continue
        try:
            candidate_shape = shape(candidate['geometry'])
            imported_shape = shape(geometry)
            center = imported_shape.union(candidate_shape).centroid
            imported = _projected(geometry, center.x, center.y)
            projected_candidate = _projected(candidate['geometry'], center.x, center.y)
        except GeometryInputError:
            continue
        distance = imported.distance(projected_candidate)
        if imported.intersects(projected_candidate) or distance <= maximum_distance_m:
            comparison = compare_geometries(geometry, candidate['geometry'])
            matches.append({
                'parcel_id': candidate['id'],
                'distance_m': round(distance, 2),
                **comparison,
            })
    return sorted(matches, key=lambda match: (-match['match_score'], match['distance_m']))[:3]


def analyze_parcels(parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    analyses = []
    for parcel in parcels:
        geometry = parcel.get('geometry')
        if not geometry:
            continue
        if parcel.get('municipal_geometry'):
            comparisons = compare_geometries(geometry, parcel['municipal_geometry'])
            analyses.append({
                'parcel_id': parcel['id'],
                'comparison_type': 'source_boundary_comparison',
                'source_a': parcel.get('source', 'Cadastral record'),
                'source_b': 'Municipal GIS boundary',
                **comparisons,
            })
        else:
            candidates = find_candidate_matches(geometry, parcels, parcel['id'])
            best_match = candidates[0] if candidates else None
            analyses.append({
                'parcel_id': parcel['id'],
                'comparison_type': 'cross_parcel_candidate_search',
                'match_score': best_match['match_score'] if best_match else 0.0,
                'geometry_area_m2': measure_geometry_area(geometry),
                'candidate_matches': candidates,
                'requires_review': best_match is not None,
                'reasons': (
                    [f"Spatial candidate {best_match['parcel_id']} found within {best_match['distance_m']:.2f} m; verify identity and source records."]
                    if best_match
                    else ['No overlapping or nearby candidate parcel was found in the current dataset.']
                ),
            })
    return analyses