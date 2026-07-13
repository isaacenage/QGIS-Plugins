# -*- coding: utf-8 -*-
"""Pure helpers for tie point search.

PostgREST query building, offline-cache filtering/merging and correction
payload assembly. No QGIS/Qt imports so everything here is unit-testable
outside QGIS (see test/test_tiepoint_data.py).
"""

from urllib.parse import urlencode

SEARCH_COLUMNS = "id,name,description,province,municipality,northing,easting"
DEFAULT_LIMIT = 1000


def normalize_name(text):
    """Space-insensitive, case-insensitive key so 'BLLM1' matches 'BLLM 1'."""
    return (text or "").replace(" ", "").lower()


def build_search_params(name="", description="", municipality="", province="",
                        limit=DEFAULT_LIMIT):
    """PostgREST query parameters mirroring the original filter semantics:
    name is space/case-insensitive contains, description and municipality are
    case-insensitive contains, province is an exact match."""
    params = [("select", SEARCH_COLUMNS)]
    name_key = normalize_name(name)
    if name_key:
        params.append(("name_key", "ilike.*{}*".format(name_key)))
    description = (description or "").strip()
    if description:
        params.append(("description", "ilike.*{}*".format(description)))
    municipality = (municipality or "").strip()
    if municipality:
        params.append(("municipality", "ilike.*{}*".format(municipality)))
    province = (province or "").strip()
    if province:
        params.append(("province", "eq.{}".format(province)))
    params.append(("order", "province.asc,municipality.asc,name.asc"))
    params.append(("limit", str(limit)))
    return params


def build_search_url(base_url, name="", description="", municipality="",
                     province="", limit=DEFAULT_LIMIT):
    query = urlencode(build_search_params(
        name=name, description=description, municipality=municipality,
        province=province, limit=limit))
    return "{}/rest/v1/tiepoints?{}".format(base_url, query)


def row_matches(row, name="", description="", municipality="", province=""):
    """Offline-cache filter with the same semantics as build_search_params."""
    if name and normalize_name(name) not in normalize_name(
            str(row.get("name") or "")):
        return False
    description = (description or "").strip().lower()
    if description and description not in str(
            row.get("description") or "").lower():
        return False
    municipality = (municipality or "").strip().lower()
    if municipality and municipality not in str(
            row.get("municipality") or "").lower():
        return False
    province = (province or "").strip()
    if province and str(row.get("province") or "") != province:
        return False
    return True


def filter_rows(rows, name="", description="", municipality="", province=""):
    """Filter + sort cached rows like the server query would."""
    matched = [r for r in rows if row_matches(
        r, name=name, description=description,
        municipality=municipality, province=province)]
    return sorted(matched, key=lambda r: (
        str(r.get("province") or ""),
        str(r.get("municipality") or ""),
        str(r.get("name") or ""),
    ))


def merge_rows(existing_by_id, new_rows):
    """Return a NEW id->row dict with new_rows merged in (no mutation)."""
    merged = dict(existing_by_id)
    for row in new_rows:
        row_id = row.get("id")
        if row_id is not None:
            merged[str(row_id)] = row
    return merged


def provinces_from_rows(rows):
    """Sorted unique province names, for the offline province combo."""
    return sorted({str(r.get("province")) for r in rows if r.get("province")})


def parse_coordinate(text):
    """Parse a user-typed coordinate. Returns (value, is_valid) where an
    empty field is (None, True) and garbage is (None, False)."""
    text = (text or "").strip().replace(",", "")
    if not text:
        return None, True
    try:
        return float(text), True
    except ValueError:
        return None, False


def correction_payload(
        tiepoint,
        proposed_northing=None,
        proposed_easting=None,
        remarks="",
        reporter_name="",
        contact="",
        plugin_version=""):
    """Assemble the tiepoint_corrections insert payload from the tie point
    being reported plus the user's proposed values."""
    return {
        "tiepoint_id": tiepoint.get("id"),
        "tiepoint_name": str(tiepoint.get("name") or ""),
        "tiepoint_description": tiepoint.get("description"),
        "province": tiepoint.get("province"),
        "municipality": tiepoint.get("municipality"),
        "current_northing": tiepoint.get("northing"),
        "current_easting": tiepoint.get("easting"),
        "proposed_northing": proposed_northing,
        "proposed_easting": proposed_easting,
        "remarks": (remarks or "").strip() or None,
        "reporter_name": (reporter_name or "").strip() or None,
        "reporter_contact": (contact or "").strip() or None,
        "plugin_version": plugin_version or None,
    }
