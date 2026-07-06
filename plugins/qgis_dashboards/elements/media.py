# -*- coding: utf-8 -*-
"""Small media-loading helpers shared by data-driven tiles.

Currently just an icon loader for the Indicator's optional symbol. Mirrors the
loading strategy of :mod:`image_element` (QPixmap for raster, QSvgRenderer for
SVG) but produces a square, aspect-preserving thumbnail at a target size rather
than filling a whole tile. The source is either a **file path** (the project
file stays small; the file must remain reachable on disk) or **raw ``<svg>``
markup** pasted straight into the field.
"""

import os

from qgis.PyQt.QtCore import Qt, QByteArray, QRectF
from qgis.PyQt.QtGui import QPixmap, QImage, QPainter

try:
    from qgis.PyQt.QtSvg import QSvgRenderer
except ImportError:          # QtSvg is optional on some builds
    QSvgRenderer = None


def _looks_like_svg_markup(source):
    """True when *source* is raw SVG markup rather than a file path."""
    return isinstance(source, str) and "<svg" in source.lower()


def _svg_pixmap(renderer, size):
    """Render a valid ``QSvgRenderer`` into a transparent ``size``×``size``
    pixmap, centered and aspect-preserving; ``None`` if the SVG is invalid."""
    if not renderer.isValid():
        return None
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    bounds = renderer.defaultSize()
    bw, bh = bounds.width(), bounds.height()
    if bw > 0 and bh > 0:
        scale = min(size / bw, size / bh)
        w, h = bw * scale, bh * scale
        renderer.render(painter, QRectF((size - w) / 2.0, (size - h) / 2.0, w, h))
    else:
        renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def icon_pixmap(source, size):
    """Return a ``QPixmap`` for *source* scaled to fit ``size``×``size``.

    *source* is either a file path (PNG/JPG/SVG/…) or **raw SVG markup** pasted
    straight into the field (e.g. copied from an icon site). Keeps aspect ratio;
    returns ``None`` when the source is empty, missing, or unreadable so the
    caller can simply skip the icon.
    """
    if not source:
        return None
    size = max(int(size), 1)
    if _looks_like_svg_markup(source):
        if QSvgRenderer is None:
            return None
        return _svg_pixmap(QSvgRenderer(QByteArray(source.encode("utf-8"))), size)
    if not os.path.isfile(source):
        return None
    ext = os.path.splitext(source)[1].lower()
    if ext == ".svg" and QSvgRenderer is not None:
        return _svg_pixmap(QSvgRenderer(source), size)
    pixmap = QPixmap(source)
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
