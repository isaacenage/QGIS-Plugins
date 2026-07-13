# -*- coding: utf-8 -*-
"""HTTP client that publishes a dashboard straight to Supabase.

Files go into the public ``dashboards`` storage bucket and one metadata row
into the ``dashboards`` table — both with the publishable (anon) key, whose
power is bounded server-side by Row Level Security: insert-only, first write
wins, no overwrite/delete, published rows only. Publishing is **instant** —
no Pull Request, no review wait — and the old 4 MB request cap is gone
because nothing routes through a serverless function anymore.

Requests go through ``QgsNetworkAccessManager`` (so QGIS proxy/SSL settings
apply), blocked on a local event loop with a timeout. Failures surface as
:class:`PublishError` with a user-safe message.
"""

import json

from qgis.PyQt.QtCore import QUrl, QByteArray, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import QgsNetworkAccessManager

from .submit_payload import (
    MAX_SLUG_ATTEMPTS, build_row, candidate_slug, object_key, slugify,
    view_url,
)

SUPABASE_URL = "https://dywixbogcfphybzmimqw.supabase.co"
# Publishable (anon) key — designed to ship in client code; Row Level
# Security is what limits it (see module docstring).
SUPABASE_ANON_KEY = "sb_publishable_boQFoicY4U3d2naPjM8Ogg_vurpLiro"  # pragma: allowlist secret  # nosec B105
BUCKET = "dashboards"

GALLERY_URL = "https://qgis.byzenterra.org/qdashboards/gallery"

USER_AGENT = "QGIS-Dashboard-Plugin"
TIMEOUT_MS = 60000
# Dashboards can be tens of MB; give slow field connections room.
UPLOAD_TIMEOUT_MS = 300000


class PublishError(Exception):
    """A publish failure with a message safe to show the user."""


def _request(url, content_type):
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"apikey", SUPABASE_ANON_KEY.encode())
    request.setRawHeader(
        b"Authorization", ("Bearer " + SUPABASE_ANON_KEY).encode())
    request.setRawHeader(b"Content-Type", content_type.encode())
    request.setRawHeader(b"User-Agent", USER_AGENT.encode())
    return request


def _blocking_post(request, body, timeout_ms):
    """POST and block on a local event loop. Returns (status, body_bytes);
    raises :class:`PublishError` on timeout or transport failure."""
    nam = QgsNetworkAccessManager.instance()
    reply = nam.post(request, QByteArray(body))

    loop = QEventLoop()
    reply.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timed_out = {"value": False}

    def _on_timeout():
        timed_out["value"] = True
        reply.abort()

    timer.timeout.connect(_on_timeout)
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()

    err = reply.error()
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    data = bytes(reply.readAll())
    reply.deleteLater()

    if timed_out["value"]:
        raise PublishError("The upload didn't finish in time. Check your "
                           "connection and try again.")
    if err != QNetworkReply.NetworkError.NoError and status is None:
        raise PublishError(
            "Couldn't reach the gallery storage. Check your internet "
            "connection or QGIS proxy settings.")
    return int(status or 0), data


def _is_duplicate(status, data):
    """Storage/PostgREST 'already exists' responses (first write wins)."""
    if status == 409:
        return True
    try:
        body = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(body, dict) and (
        body.get("statusCode") == "409" or body.get("error") == "Duplicate")


def _error_message(data, fallback):
    try:
        body = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return fallback
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or fallback
    return fallback


def upload_object(key, data, content_type, timeout_ms=UPLOAD_TIMEOUT_MS):
    """Upload one object into the bucket. Returns ``"ok"`` or ``"conflict"``
    (the key is already taken); raises :class:`PublishError` otherwise."""
    url = "{}/storage/v1/object/{}/{}".format(SUPABASE_URL, BUCKET, key)
    status, body = _blocking_post(
        _request(url, content_type), data, timeout_ms)
    if 200 <= status < 300:
        return "ok"
    if _is_duplicate(status, body):
        return "conflict"
    if status == 413:
        raise PublishError(
            "This dashboard is too large for the gallery (over the 50 MB "
            "file limit). Try skipping or removing large layers, using "
            "lighter images, or splitting it into fewer pages.")
    raise PublishError(_error_message(
        body, "The gallery storage rejected the upload (error {}). Please "
              "try again later.".format(status or "unknown")))


def insert_row(row):
    """Insert the metadata row. Returns ``"ok"`` or ``"conflict"``; raises
    :class:`PublishError` otherwise."""
    url = SUPABASE_URL + "/rest/v1/dashboards"
    request = _request(url, "application/json")
    request.setRawHeader(b"Prefer", b"return=minimal")
    body = json.dumps(row).encode("utf-8")
    status, data = _blocking_post(request, body, TIMEOUT_MS)
    if 200 <= status < 300:
        return "ok"
    if _is_duplicate(status, data):
        return "conflict"
    raise PublishError(_error_message(
        data, "The gallery rejected the dashboard details (error {}). "
              "Please try again later.".format(status or "unknown")))


def publish(title, author, html_bytes, thumb_bytes, description=None,
            progress=None):
    """Publish one dashboard: upload files under a free slug, then register
    the metadata row. Returns ``{"slug", "view_url", "gallery_url"}``.

    The slug is claimed by the index.html upload itself (storage inserts are
    first-write-wins), so concurrent publishers can never overwrite each
    other; on a name collision we retry with ``-2``, ``-3``, …
    """
    def _tick(step, frac):
        if progress:
            progress(step, frac)

    base = slugify(title)
    slug = None
    for attempt in range(MAX_SLUG_ATTEMPTS):
        candidate = candidate_slug(base, attempt)
        _tick("Uploading dashboard…", 0.55)
        outcome = upload_object(
            object_key(candidate, "index.html"), html_bytes, "text/html")
        if outcome == "ok":
            slug = candidate
            break
    if slug is None:
        raise PublishError(
            "Couldn't find a free gallery name for \"{}\" — too many "
            "dashboards share this title. Rename your QGIS project and "
            "publish again.".format(title))

    # A missing thumbnail degrades the gallery card, not the dashboard —
    # publish anyway rather than failing after the HTML is already up.
    has_thumb = False
    if thumb_bytes:
        _tick("Uploading thumbnail…", 0.8)
        try:
            has_thumb = upload_object(
                object_key(
                    slug,
                    "thumb.png"),
                thumb_bytes,
                "image/png") == "ok"
        except PublishError:
            has_thumb = False

    _tick("Registering in the gallery…", 0.9)
    row = build_row(slug, title, author, description, len(html_bytes),
                    has_thumb=has_thumb)
    if insert_row(row) != "ok":
        # The slug's files uploaded but a (possibly hidden) row already holds
        # the slug — surface it rather than half-publishing.
        raise PublishError(
            "The gallery name \"{}\" is reserved. Rename your QGIS project "
            "and publish again.".format(slug))

    return {"slug": slug, "view_url": view_url(slug),
            "gallery_url": GALLERY_URL}
