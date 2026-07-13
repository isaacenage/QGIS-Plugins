# -*- coding: utf-8 -*-
"""Orchestrates *Publish to public*: dashboard -> Supabase, live instantly.

Runs on the UI thread (it renders widgets and shows a progress dialog). Builds
the self-contained HTML (:mod:`export.html_export`) and an off-screen thumbnail,
then uploads both straight to the gallery's Supabase storage bucket and
registers a metadata row via :mod:`submit_client`. No server middleman, no
Pull Request: the dashboard is live in the gallery the moment publish returns.
"""

from qgis.PyQt.QtCore import Qt, QByteArray, QBuffer, QIODevice

from .export.html_export import build_dashboard_html, oversize_layers, _project_title
from .submit_client import publish, PublishError
from . import submit_payload

THUMB_WIDTH = 800
# Mirror the export-dialog large-data guard.
MAX_FEATURES = 100000
MAX_BYTES = 50 * 1024 * 1024


def _noop(_step, _frac):
    pass


def render_thumbnail_png(window):
    """Render the current page to PNG bytes (~THUMB_WIDTH wide), or ``None``.

    Uses the canvas's own ``export_pixmap`` (which hides editing chrome and the
    region frame and restores them after) so the thumbnail is the clean page.
    """
    view = window.current_view()
    if view is None:
        return None
    pixmap = view.export_pixmap(scale=2.0)
    if pixmap is None or pixmap.isNull():
        return None
    image = pixmap.toImage()
    image.setDevicePixelRatio(1.0)   # normalize: work in physical pixels
    if image.width() > THUMB_WIDTH:
        image = image.scaledToWidth(
            THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
    buffer_bytes = QByteArray()
    buffer = QBuffer(buffer_bytes)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        return None
    return bytes(buffer_bytes)


def publish_dashboard(window, author, description=None, skip_layers=None,
                      progress=None):
    """Publish the current dashboard to the gallery. Returns the result dict.

    On success the result is ``{"slug", "view_url", "gallery_url"}`` and the
    dashboard is **already live** at ``view_url``. Raises
    :class:`PublishError` (user-safe message) on any failure.
    """
    progress = progress or _noop

    # --- local work first (UI thread): build HTML + thumbnail -------------
    progress("Building dashboard…", 0.15)
    html = build_dashboard_html(window, skip_layers=skip_layers)
    html_bytes = html.encode("utf-8") if isinstance(html, str) else html

    # Refuse oversize dashboards before the wire so the user gets an
    # actionable message instead of the storage service's opaque rejection.
    if submit_payload.exceeds_size_limit(html_bytes):
        size_mb = len(html_bytes) / (1024.0 * 1024.0)
        cap_mb = submit_payload.MAX_HTML_BYTES / (1024.0 * 1024.0)
        raise PublishError(
            "This dashboard is too large to publish ({:.1f} MB; the gallery "
            "accepts up to {:.0f} MB per dashboard). Try skipping or removing "
            "large layers, using lighter images, or splitting it into fewer "
            "pages, then publish again.".format(size_mb, cap_mb))

    progress("Rendering thumbnail…", 0.35)
    thumb_bytes = render_thumbnail_png(window)
    if not thumb_bytes:
        raise PublishError(
            "Couldn't render a dashboard thumbnail. Make sure the "
            "dashboard window is open with at least one page.")

    title = _project_title()

    # --- upload straight to the gallery's storage --------------------------
    result = publish(title, author, html_bytes, thumb_bytes,
                     description=description, progress=progress)

    progress("Done", 1.0)
    return result


def oversize_referenced_layers(window):
    """Large bound layers, for the pre-publish warning (reuses the export guard)."""
    return oversize_layers(window, MAX_FEATURES, MAX_BYTES)
