# -*- coding: utf-8 -*-
"""Online tie point access (Supabase PostgREST) plus the local offline cache.

The plugin no longer ships tiepoints.json. Searches query the hosted
database, and every successful result is merged into a cache file under the
user's QGIS profile so previously fetched tie points stay usable offline in
the field. Correction reports are POSTed to an insert-only table reviewed by
the developer.
"""

import json
import os
from datetime import datetime

from qgis.core import QgsApplication, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .tiepoint_data import DEFAULT_LIMIT, build_search_url

SUPABASE_URL = "https://dywixbogcfphybzmimqw.supabase.co"
# Publishable (anon) key - designed to ship in client code. Access is
# enforced server-side by Row Level Security: the tiepoints table is
# SELECT-only and tiepoint_corrections is INSERT-only for this key.
SUPABASE_ANON_KEY = "sb_publishable_boQFoicY4U3d2naPjM8Ogg_vurpLiro"
REQUEST_TIMEOUT_MS = 15000

CACHE_DIR_NAME = "TitlePlotterPH"
CACHE_FILE_NAME = "tiepoint_cache.json"

# ErrorCode is unscoped in Qt5 builds, scoped in some Qt6 builds
_NO_ERROR = getattr(QgsBlockingNetworkRequest, "NoError", None)
if _NO_ERROR is None:
    _NO_ERROR = QgsBlockingNetworkRequest.ErrorCode.NoError


def _request(method, url, body=None):
    """Run a blocking, proxy-aware HTTP request through the QGIS network
    stack. Returns (ok, payload_bytes, error_message)."""
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"apikey", SUPABASE_ANON_KEY.encode())
    request.setRawHeader(b"Authorization", ("Bearer " + SUPABASE_ANON_KEY).encode())
    request.setRawHeader(b"Accept", b"application/json")
    try:
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
    except AttributeError:
        pass  # Qt < 5.15 falls back to the global QGIS network timeout
    blocking = QgsBlockingNetworkRequest()
    if method == "GET":
        error = blocking.get(request)
    else:
        request.setRawHeader(b"Content-Type", b"application/json")
        request.setRawHeader(b"Prefer", b"return=minimal")
        error = blocking.post(request, body or b"")
    if error != _NO_ERROR:
        return False, b"", blocking.errorMessage() or "Network request failed"
    return True, bytes(blocking.reply().content()), ""


def _get_json(url):
    """GET url and decode the JSON list it returns. Returns (rows, error)
    where rows is None on any failure."""
    ok, payload, error = _request("GET", url)
    if not ok:
        return None, error
    try:
        rows = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, "Could not parse server response: {}".format(exc)
    if not isinstance(rows, list):
        return None, "Unexpected server response"
    return rows, ""


def search_tiepoints(name="", description="", municipality="", province="",
                     limit=DEFAULT_LIMIT):
    """Search the online tie point database. Returns (rows, error); rows is
    None when offline / on failure so the caller can fall back to the cache."""
    url = build_search_url(
        SUPABASE_URL, name=name, description=description,
        municipality=municipality, province=province, limit=limit)
    return _get_json(url)


def fetch_provinces():
    """Distinct province list for the combo box. Returns (names, error)."""
    url = SUPABASE_URL + "/rest/v1/tiepoint_provinces?select=province&order=province.asc"
    rows, error = _get_json(url)
    if rows is None:
        return None, error
    return [str(r.get("province")) for r in rows if r.get("province")], ""


def submit_correction(payload):
    """Send one correction report (requires internet). Returns (ok, error)."""
    url = SUPABASE_URL + "/rest/v1/tiepoint_corrections"
    body = json.dumps(payload).encode("utf-8")
    ok, _, error = _request("POST", url, body)
    return ok, error


def cache_file_path():
    return os.path.join(
        QgsApplication.qgisSettingsDirPath(), CACHE_DIR_NAME, CACHE_FILE_NAME)


def load_cache():
    """Load the offline cache: {"rows": {id: row}, "provinces": [...]}.
    Always returns a usable dict, empty when no cache exists yet."""
    try:
        with open(cache_file_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("rows"), dict):
            return {
                "rows": data["rows"],
                "provinces": list(data.get("provinces") or []),
            }
    except (OSError, ValueError):
        pass
    return {"rows": {}, "provinces": []}


def save_cache(cache):
    """Persist the offline cache. Returns False (without raising) when the
    profile directory is not writable."""
    path = cache_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "rows": cache.get("rows", {}),
            "provinces": cache.get("provinces", []),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return True
    except OSError:
        return False


def plugin_version():
    """Version string from metadata.txt, for correction-report triage."""
    try:
        path = os.path.join(os.path.dirname(__file__), "metadata.txt")
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("version="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""
