overview = {
    "title": "LandSync AI",
    "subtitle": "Boundary Dispersion and Geospatial Harmonization",
    "metrics": [
        {"label": "Parcel 704-B", "status": "Dispute Solved", "value": "98.4%", "tone": "success"},
        {"label": "Records Harmonized", "value": "3,240", "tone": "info"},
        {"label": "Conflicts Resolved", "value": "210", "tone": "highlight"},
        {"label": "Departments Linked", "value": "6", "tone": "neutral"},
    ],
    "integrity": {
        "blocks": 4,
        "verified": "100%",
        "integrity": "2 of 2",
        "status": "Multi-Sig Validated",
    },
    "system_health": {
        "last_sync": "2 min ago",
        "geodetic": "Valid",
        "ledger": "Chain Verified",
    },
}

parcels = [
    {
        "id": "704-B",
        "status": "Inspection Complete",
        "priority": "High",
        "source": "Municipal GIS + Revenue Registry",
        "area": 1240.5,
        "difference": 87.7,
        "drift": 1.84,
        "owner": "Heritage Realty Corp",
        "recorded_area": 1240.5,
        "municipal_area": 1328.2,
        "resolution": "AI Harmonization accepted",
        "geometry": {"type": "Polygon", "coordinates": [[[77.208000, 28.613000], [77.208410, 28.613000], [77.208410, 28.613279], [77.208000, 28.613279], [77.208000, 28.613000]]]},
        "municipal_geometry": {"type": "Polygon", "coordinates": [[[77.208000, 28.612995], [77.208431, 28.612995], [77.208431, 28.613279], [77.208000, 28.613279], [77.208000, 28.612995]]]},
        "coordinates": {"lat": 28.613928, "lon": 77.209022},
    },
    {
        "id": "4819Z",
        "status": "Flagged",
        "priority": "Medium",
        "source": "Cadastral + Survey",
        "area": 1460.3,
        "difference": 42.1,
        "drift": 1.66,
        "owner": "Atlas Urban Developers",
        "recorded_area": 1460.3,
        "municipal_area": 1502.8,
        "resolution": "Awaiting field review",
        "geometry": {"type": "Polygon", "coordinates": [[[77.213800, 28.619500], [77.214271, 28.619500], [77.214271, 28.619786], [77.213800, 28.619786], [77.213800, 28.619500]]]},
        "municipal_geometry": {"type": "Polygon", "coordinates": [[[77.213803, 28.619503], [77.214287, 28.619503], [77.214287, 28.619789], [77.213803, 28.619789], [77.213803, 28.619503]]]},
        "coordinates": {"lat": 28.620312, "lon": 77.215451},
    },
    {
        "id": "9034-C",
        "status": "Validated",
        "priority": "Low",
        "source": "Revenue + Utility Map",
        "area": 1198.8,
        "difference": 12.4,
        "drift": 0.91,
        "owner": "North Sector Housing",
        "recorded_area": 1198.8,
        "municipal_area": 1211.2,
        "resolution": "Approved by GIS division",
        "geometry": {"type": "Polygon", "coordinates": [[[77.200700, 28.609200], [77.201100, 28.609200], [77.201100, 28.609477], [77.200700, 28.609477], [77.200700, 28.609200]]]},
        "municipal_geometry": {"type": "Polygon", "coordinates": [[[77.200700, 28.609200], [77.201104, 28.609200], [77.201104, 28.609477], [77.200700, 28.609477], [77.200700, 28.609200]]]},
        "coordinates": {"lat": 28.609821, "lon": 77.201901},
    },
]

conflicts = []

queue = [
    {
        "case_id": "P-704-B",
        "parcel_id": "704-B",
        "owner": "Heritage Realty Corp",
        "issue": "Boundary drift mismatch detected between deed and municipal map",
        "review_status": "Awaiting officer review",
    },
    {
        "case_id": "P-4819Z",
        "parcel_id": "4819Z",
        "owner": "Atlas Urban Developers",
        "issue": "Survey discrepancy near internal drainage easement",
        "review_status": "Escalated for validation",
    },
    {
        "case_id": "P-9034-C",
        "parcel_id": "9034-C",
        "owner": "North Sector Housing",
        "issue": "Variance within tolerance threshold",
        "review_status": "Approved",
    },
]

audit_events = [
    {
        "id": "AUD-00421",
        "action": "AI assessment generated",
        "parcel_id": "704-B",
        "actor": "LandSync Harmon-X",
        "detail": "Sample cadastral and municipal source geometries are ready for analysis.",
        "time": "2 hrs ago",
    },
    {
        "id": "AUD-00420",
        "action": "Survey source attached",
        "parcel_id": "4819Z",
        "actor": "GIS Analyst",
        "detail": "Imported field survey with EPSG:4326 coordinates.",
        "time": "Yesterday 16:42",
    },
    {
        "id": "AUD-00419",
        "action": "Parcel record validated",
        "parcel_id": "9034-C",
        "actor": "Ward Officer",
        "detail": "Approved variance within configured tolerance.",
        "time": "Yesterday 14:08",
    },
]
