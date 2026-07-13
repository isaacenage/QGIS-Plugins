# -*- coding: utf-8 -*-
"""Collect feature data from QGIS for the HTML export.

This is the QGIS-touching layer: it reads bound vector layers into plain,
JSON-safe Python (so :mod:`serialize` can stay pure), evaluates each tile's
static ``base_filter`` into a set of passing feature *indices* (so the browser
needs no expression parser), embeds image files as base64 data URIs, and
estimates layer size for the pre-export guard.

Cross-filtering is deliberately NOT applied here — only the per-tile
``base_filter`` is. The live cross-filter is reproduced client-side.
"""

import base64
import contextlib
import mimetypes
import os

from qgis.core import QgsFeatureRequest, QgsExpression


def jsonify(value):
    """Coerce a QGIS attribute value into a JSON-serializable Python value."""
    if value is None:
        return None
    # QGIS NULL is a typed null QVariant exposing isNull(); treat it as None.
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        with contextlib.suppress(Exception):
            if value.isNull():
                return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    # QDate / QDateTime / QTime and anything exotic -> ISO-ish string.
    to_string = getattr(value, "toString", None)
    if callable(to_string):
        with contextlib.suppress(Exception):
            return value.toString("yyyy-MM-dd HH:mm:ss").strip() or str(value)
    return str(value)


def collect_layer_data(layer):
    """Read *layer* into ``({"fields", "features"}, fid_index)``.

    ``features`` is a list of ``{field_name: value}`` dicts (all fields, all
    rows). ``fid_index`` maps each feature id to its position in that list and
    is used to compute ``base_pass`` masks; it is not part of the export model.
    """
    field_names = [f.name() for f in layer.fields()]
    features = []
    fid_index = {}
    for feat in layer.getFeatures():
        fid_index[feat.id()] = len(features)
        features.append({name: jsonify(feat[name]) for name in field_names})
    return {"fields": field_names, "features": features}, fid_index


def base_pass_indices(layer, base_filter, fid_index):
    """Return sorted feature indices passing *base_filter*, or ``None``.

    ``None`` means "no base filter" (all rows pass). An invalid expression is
    treated as no filter (the export must not abort over a bad expression).
    """
    if not base_filter or layer is None:
        return None
    expr = QgsExpression(base_filter)
    if expr.hasParserError():
        return None
    request = QgsFeatureRequest()
    request.setFilterExpression(base_filter)
    indices = []
    try:
        for feat in layer.getFeatures(request):
            idx = fid_index.get(feat.id())
            if idx is not None:
                indices.append(idx)
    except Exception:
        return None
    return sorted(indices)


def image_data_uri(path):
    """Return a base64 ``data:`` URI for *path*, or ``None`` if unreadable.

    *path* may also be **raw SVG markup** pasted into an icon field, which is
    embedded directly as an ``image/svg+xml`` data URI.
    """
    if not path:
        return None
    if isinstance(path, str) and "<svg" in path.lower():
        raw = path.strip().encode("utf-8")
        return "data:image/svg+xml;base64,{}".format(
            base64.b64encode(raw).decode("ascii"))
    if not os.path.isfile(path):
        return None
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return "data:{};base64,{}".format(
        mime, base64.b64encode(raw).decode("ascii"))


def layer_size_info(layer):
    """Return ``(feature_count, estimated_bytes)`` for the size guard.

    The byte estimate (from :mod:`size_estimate`) now includes the per-feature
    WGS84 geometry the interactive map embeds, so the guard reflects the real
    single-file payload.
    """
    from .size_estimate import estimate_layer_bytes
    count = layer.featureCount()
    if count is None or count < 0:
        count = 0
    cols = len(layer.fields())
    return count, estimate_layer_bytes(count, cols, include_geometry=True)
