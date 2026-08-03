# -*- coding: utf-8 -*-
"""Embedded SVG glyphs for the AutoQAD tool rail.

Same approach as the sibling plugins: artwork lives in this table rather than
on disk, and every glyph is re-tinted to a single colour with
``CompositionMode_SourceIn``. Because the tint recolours every opaque pixel,
the stroke colour baked into each glyph is irrelevant — only its shape matters.

Icons are supersampled and tagged with a device-pixel ratio so Qt *downscales*
them to the physical size, which stays sharp at 125/150/200 % display scaling
instead of blurring up from a too-small raster.

``QtSvg`` ships with QGIS, but the import is guarded anyway: if it is missing
every helper degrades to a null icon and callers fall back to text, so the
plugin never fails to load over an icon.
"""

from qgis.PyQt.QtCore import QByteArray, QRectF
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap

try:
    from qgis.PyQt.QtSvg import QSvgRenderer
    _HAS_SVG = True
except ImportError:                       # pragma: no cover - present in QGIS
    _HAS_SVG = False

_SS = 4          # supersample factor


def _stroke(body, width="1.4"):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="#000000" stroke-width="{0}" '
        'stroke-linecap="round" stroke-linejoin="round">{1}</svg>'
    ).format(width, body)


ICONS = {
    # --- draw -------------------------------------------------------------
    "line": _stroke('<line x1="4" y1="20" x2="20" y2="4"/>'
                    '<circle cx="4" cy="20" r="1.6" fill="#000"/>'
                    '<circle cx="20" cy="4" r="1.6" fill="#000"/>'),
    "polyline": _stroke('<polyline points="3,18 9,8 15,14 21,5"/>'
                        '<circle cx="3" cy="18" r="1.5" fill="#000"/>'
                        '<circle cx="9" cy="8" r="1.5" fill="#000"/>'
                        '<circle cx="15" cy="14" r="1.5" fill="#000"/>'
                        '<circle cx="21" cy="5" r="1.5" fill="#000"/>'),
    "rectangle": _stroke('<rect x="3.5" y="6" width="17" height="12"/>'
                         '<circle cx="3.5" cy="6" r="1.5" fill="#000"/>'
                         '<circle cx="20.5" cy="18" r="1.5" fill="#000"/>'),
    "circle": _stroke('<circle cx="12" cy="12" r="8"/>'
                      '<circle cx="12" cy="12" r="1.3" fill="#000"/>'
                      '<line x1="12" y1="12" x2="20" y2="12" '
                      'stroke-dasharray="2 2"/>'),
    "arc": _stroke('<path d="M4 18 A 9 9 0 0 1 20 12"/>'
                   '<circle cx="4" cy="18" r="1.5" fill="#000"/>'
                   '<circle cx="20" cy="12" r="1.5" fill="#000"/>'),
    "polygon": _stroke('<polygon points="12,3 20.5,8.5 17.5,19 6.5,19 '
                       '3.5,8.5"/>'),
    "ellipse": _stroke('<ellipse cx="12" cy="12" rx="9" ry="5.5"/>'),
    "point": _stroke('<line x1="12" y1="5" x2="12" y2="19"/>'
                     '<line x1="5" y1="12" x2="19" y2="12"/>'
                     '<circle cx="12" cy="12" r="2" fill="#000"/>'),
    "text": _stroke('<line x1="5" y1="6" x2="19" y2="6"/>'
                    '<line x1="12" y1="6" x2="12" y2="19"/>'),
    "hatch": _stroke('<rect x="3.5" y="5" width="17" height="14"/>'
                     '<line x1="6" y1="17" x2="12" y2="7"/>'
                     '<line x1="10" y1="17" x2="16" y2="7"/>'
                     '<line x1="14" y1="17" x2="18.5" y2="9.5"/>'),

    # --- modify -----------------------------------------------------------
    "move": _stroke('<line x1="12" y1="3" x2="12" y2="21"/>'
                    '<line x1="3" y1="12" x2="21" y2="12"/>'
                    '<polyline points="9,6 12,3 15,6"/>'
                    '<polyline points="9,18 12,21 15,18"/>'
                    '<polyline points="6,9 3,12 6,15"/>'
                    '<polyline points="18,9 21,12 18,15"/>'),
    "copy": _stroke('<rect x="3.5" y="3.5" width="12" height="12" rx="1.5"/>'
                    '<rect x="8.5" y="8.5" width="12" height="12" rx="1.5"/>'),
    "rotate": _stroke('<path d="M20 12a8 8 0 1 1-2.4-5.7"/>'
                      '<polyline points="20 4 20 8 16 8"/>'
                      '<circle cx="12" cy="12" r="1.3" fill="#000"/>'),
    "scale": _stroke('<polyline points="4,20 4,10 14,20 4,20"/>'
                     '<rect x="12" y="4" width="8" height="8"/>'),
    "mirror": _stroke('<line x1="12" y1="3" x2="12" y2="21" '
                      'stroke-dasharray="2 2"/>'
                      '<polygon points="9,7 3,12 9,17"/>'
                      '<polygon points="15,7 21,12 15,17"/>'),
    "offset": _stroke('<path d="M6 20 L6 8 A 3 3 0 0 1 9 5 L18 5"/>'
                      '<path d="M10 20 L10 10 A 1 1 0 0 1 11 9 L18 9" '
                      'stroke-dasharray="2 2"/>'),
    "trim": _stroke('<line x1="3" y1="16" x2="21" y2="16"/>'
                    '<line x1="12" y1="4" x2="12" y2="20" '
                    'stroke-dasharray="2 2"/>'
                    '<circle cx="7" cy="8" r="2.5"/>'
                    '<circle cx="7" cy="14" r="2.5"/>'),
    "extend": _stroke('<line x1="19" y1="4" x2="19" y2="20" '
                      'stroke-dasharray="2 2"/>'
                      '<line x1="3" y1="12" x2="14" y2="12"/>'
                      '<polyline points="11,9 14,12 11,15"/>'),
    "fillet": _stroke('<path d="M4 20 L4 11 A 7 7 0 0 1 11 4 L20 4"/>'),
    "erase": _stroke('<path d="M4 16 L11 9 L18 16 L14 20 L8 20 Z"/>'
                     '<line x1="11" y1="9" x2="16" y2="4"/>'
                     '<line x1="16" y1="4" x2="21" y2="9"/>'
                     '<line x1="21" y1="9" x2="18" y2="16"/>'),
    "array": _stroke('<rect x="3" y="3" width="6" height="6"/>'
                     '<rect x="15" y="3" width="6" height="6"/>'
                     '<rect x="3" y="15" width="6" height="6"/>'
                     '<rect x="15" y="15" width="6" height="6"/>'),
    "explode": _stroke('<polyline points="12,3 12,7"/>'
                       '<polyline points="12,17 12,21"/>'
                       '<polyline points="3,12 7,12"/>'
                       '<polyline points="17,12 21,12"/>'
                       '<rect x="9" y="9" width="6" height="6"/>'),
    "join": _stroke('<path d="M4 12 L10 12"/><path d="M14 12 L20 12"/>'
                    '<circle cx="12" cy="12" r="2.2"/>'),

    # --- tools ------------------------------------------------------------
    "layers": _stroke('<polygon points="12,3 21,8 12,13 3,8"/>'
                      '<polyline points="3,12 12,17 21,12"/>'
                      '<polyline points="3,16 12,21 21,16"/>'),
    "settings": _stroke(
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 '
        '2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 '
        '2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06'
        '.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 '
        '0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 '
        '0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 '
        '4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 '
        '1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a'
        '1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 '
        '4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    "snap": _stroke('<rect x="7" y="7" width="10" height="10"/>'
                    '<line x1="12" y1="2" x2="12" y2="7"/>'
                    '<line x1="12" y1="17" x2="12" y2="22"/>'
                    '<line x1="2" y1="12" x2="7" y2="12"/>'
                    '<line x1="17" y1="12" x2="22" y2="12"/>'),
    "measure": _stroke('<rect x="2" y="8" width="20" height="8" rx="1"/>'
                       '<line x1="7" y1="8" x2="7" y2="12"/>'
                       '<line x1="12" y1="8" x2="12" y2="12"/>'
                       '<line x1="17" y1="8" x2="17" y2="12"/>'),
    "undo": _stroke('<polyline points="9 14 4 9 9 4"/>'
                    '<path d="M20 20v-7a4 4 0 0 0-4-4H4"/>'),
    "redo": _stroke('<polyline points="15 14 20 9 15 4"/>'
                    '<path d="M4 20v-7a4 4 0 0 1 4-4h12"/>'),
    "export": _stroke('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                      '<polyline points="7 10 12 15 17 10"/>'
                      '<line x1="12" y1="15" x2="12" y2="3"/>'),
    "help": _stroke('<circle cx="12" cy="12" r="9"/>'
                    '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 '
                    '1.7v.5"/>'
                    '<circle cx="12" cy="17.5" r="1" fill="#000"/>'),
}

#: The AutoQAD mark — a drafting compass over a grid, in the plugin accent.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0%" stop-color="#4a7fb5"/>'
    '<stop offset="100%" stop-color="#2f5d8c"/>'
    '</linearGradient></defs>'
    '<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/>'
    '<g stroke="#ffffff" stroke-width="2.6" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="32" y1="14" x2="20" y2="46"/>'
    '<line x1="32" y1="14" x2="44" y2="46"/>'
    '<line x1="24" y1="35" x2="40" y2="35"/>'
    '<circle cx="32" cy="14" r="3.2" fill="#ffffff"/>'
    '</g></svg>'
)


def _render(svg_text, size):
    """Render *svg_text* to a supersampled, DPR-tagged pixmap."""
    if not _HAS_SVG:
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    pixmap = QPixmap(size * _SS, size * _SS)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size * _SS, size * _SS))
    painter.end()
    pixmap.setDevicePixelRatio(_SS)
    return pixmap


def monochrome_pixmap(key, colour, size=22):
    """Return the glyph *key* tinted to a single *colour*."""
    svg_text = ICONS.get(key)
    if svg_text is None:
        return QPixmap()
    pixmap = _render(svg_text, size)
    if pixmap.isNull():
        return pixmap

    painter = QPainter(pixmap)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(colour))
    painter.end()
    return pixmap


def monochrome_icon(key, colour, size=22):
    """Return the glyph *key* as a tinted :class:`QIcon`."""
    pixmap = monochrome_pixmap(key, colour, size)
    return QIcon(pixmap) if not pixmap.isNull() else QIcon()


def logo_pixmap(size=34):
    """Return the AutoQAD mark, rendered with its own colours."""
    return _render(LOGO_SVG, size)


def logo_icon():
    """Return the AutoQAD mark as a :class:`QIcon` for toolbars and windows."""
    pixmap = logo_pixmap(64)
    return QIcon(pixmap) if not pixmap.isNull() else QIcon()


def swatch_pixmap(colour, size=14, border="#e2e6ec"):
    """Return a small filled square — used for layer colour cells."""
    pixmap = QPixmap(size * _SS, size * _SS)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(colour))
    painter.setPen(QColor(border))
    radius = 3 * _SS
    painter.drawRoundedRect(
        1, 1, size * _SS - 2, size * _SS - 2, radius, radius)
    painter.end()
    pixmap.setDevicePixelRatio(_SS)
    return pixmap
