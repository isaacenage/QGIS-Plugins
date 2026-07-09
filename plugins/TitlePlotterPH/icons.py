# -*- coding: utf-8 -*-
"""SVG icon assets + crisp rendering helpers for Title Plotter PH.

Ported from the sibling ``qgis_dashboards`` plugin so both share one icon
language: thin **stroke-width 1.0** monochrome glyphs on a ``0 0 24 24`` grid,
re-tinted to a single chrome color with ``CompositionMode_SourceIn`` and
supersampled 4x so they stay sharp at 125/150/200% display scaling.

``LOGO_SVG`` is the plugin's branding mark — the four-arrow geometry supplied by
the author, recolored to the dashboards pastel palette (soft blue / orange /
green) — and is rendered untouched (no tint) for the toolbar action.

``QtSvg`` ships with QGIS, but the import is guarded: if it is somehow absent
every helper degrades to an empty icon so the plugin never fails over an icon.
"""

from qgis.PyQt.QtCore import QByteArray, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap

try:
    from qgis.PyQt.QtSvg import QSvgRenderer
    _HAS_SVG = True
except ImportError:                       # pragma: no cover - QtSvg ships with QGIS
    _HAS_SVG = False

# Supersample factor: render this many times larger, then let Qt downscale.
_SS = 4


def _stroke(body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="#000000" stroke-width="1.0" '
        'stroke-linecap="round" stroke-linejoin="round">{}</svg>'
    ).format(body)


ICONS = {
    # --- info-panel glyphs (replace area.svg / discrepancy.svg / misclosure.svg)
    # area — a surveyed parcel with a marked interior
    "area": _stroke(
        '<polygon points="4 9 13 4 20 11 11 20"/>'
        '<circle cx="12" cy="11.5" r="1"/>'),
    # variance — a delta (change / difference) triangle
    "variance": _stroke(
        '<path d="M12 5 18.5 18 5.5 18 Z"/>'
        '<line x1="9" y1="18" x2="15" y2="18"/>'),
    # misclosure — an unclosed traverse (a visible gap where it should close)
    "misclosure": _stroke(
        '<path d="M6.5 18.5 5 7.5 12.5 4 19 11 11.5 18.2"/>'
        '<circle cx="6.5" cy="18.5" r="0.7"/>'
        '<circle cx="11.5" cy="18.2" r="0.7"/>'),

    # --- small action glyphs ----------------------------------------------
    "add": _stroke(
        '<line x1="12" y1="6" x2="12" y2="18"/>'
        '<line x1="6" y1="12" x2="18" y2="12"/>'),
    "remove": _stroke('<line x1="6" y1="12" x2="18" y2="12"/>'),
    "up": _stroke('<polyline points="6 14 12 8 18 14"/>'),
    "down": _stroke('<polyline points="6 10 12 16 18 10"/>'),
    "chevron_down": _stroke('<polyline points="6 9 12 15 18 9"/>'),
    "chevron_up": _stroke('<polyline points="6 15 12 9 18 15"/>'),
    # tie point — a survey control crosshair
    "tie_point": _stroke(
        '<circle cx="12" cy="12" r="7"/>'
        '<line x1="12" y1="2.5" x2="12" y2="6"/>'
        '<line x1="12" y1="18" x2="12" y2="21.5"/>'
        '<line x1="2.5" y1="12" x2="6" y2="12"/>'
        '<line x1="18" y1="12" x2="21.5" y2="12"/>'
        '<circle cx="12" cy="12" r="1"/>'),
    # plot on map — a parcel drawn inside a map frame
    "plot": _stroke(
        '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
        '<polygon points="7 15 9 9 15 8 17 14 12 16"/>'),
    # new plot — circular refresh arrow
    "new": _stroke(
        '<path d="M20 11a8 8 0 1 0-2.3 5.7"/>'
        '<polyline points="20 5 20 11 14 11"/>'),
    "search": _stroke(
        '<circle cx="11" cy="11" r="7"/>'
        '<line x1="20.5" y1="20.5" x2="16" y2="16"/>'),
    "select": _stroke('<polyline points="5 12.5 10 17.5 19 6.5"/>'),
    # OCR / image — a framed picture
    "image": _stroke(
        '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
        '<circle cx="8.6" cy="10" r="1.5"/>'
        '<path d="M4 17.5l4.8-4.6 3.2 3.1 3.4-3.3 5 5"/>'),
    "upload": _stroke(
        '<path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>'
        '<polyline points="8 8 12 4 16 8"/>'
        '<line x1="12" y1="4" x2="12" y2="15"/>'),
    "paste": _stroke(
        '<rect x="5" y="5" width="14" height="16" rx="2"/>'
        '<rect x="9" y="3" width="6" height="4" rx="1"/>'),
    "eye": _stroke(
        '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>'
        '<circle cx="12" cy="12" r="2.6"/>'),
    "eye_off": _stroke(
        '<path d="M4 5l16 14"/>'
        '<path d="M9.5 6.2A9.8 9.8 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 3.8"/>'
        '<path d="M6.1 8.1A16.8 16.8 0 0 0 2 12s3.5 7 10 7a9.8 9.8 0 0 0 3.3-.6"/>'),
    "zoom_reset": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#000" stroke-width="1.0" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4.5 9V4.5H9"/>'
        '<path d="M15 4.5H19.5V9"/>'
        '<path d="M4.5 15V19.5H9"/>'
        '<path d="M15 19.5H19.5V15"/>'
        '<circle cx="12" cy="12" r="2.1" stroke-width="1.0"/>'
        '</svg>'),
    "help": _stroke(
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9.2a2.6 2.6 0 0 1 5 0.9c0 1.7-2.5 2-2.5 3.4"/>'
        '<circle cx="12" cy="16.6" r="0.4"/>'),
}


# --- the gradient app logo (four-arrow mark, recolored to the dashboards
#     pastel palette: soft blue / orange / green) ---------------------------
#
# Geometry is the author-supplied four-arrow SVG; the saturated blue/pink
# gradients are replaced with the dashboards pastel pairs. Right + bottom arrows
# are soft blue, the left arrow soft orange, the top arrow soft green — echoing
# the three-color dashboards logo. Each shape keeps its original gradient
# coordinates so the directional shading stays correct.
def _lg(_id, x1, y1, x2, y2, c0, c1):
    return (
        '<linearGradient id="{i}" gradientUnits="userSpaceOnUse" '
        'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        'gradientTransform="matrix(7.8769 0 0 -7.8769 364.0537 4969.6694)">'
        '<stop offset="0" style="stop-color:{c0}"/>'
        '<stop offset="1" style="stop-color:{c1}"/></linearGradient>'
    ).format(i=_id, x1=x1, y1=y1, x2=x2, y2=y2, c0=c0, c1=c1)


_BLUE = ("#A7D2F5", "#5E97D0")
_ORANGE = ("#F8CDA6", "#E89A5C")
_GREEN = ("#A9DCC2", "#6FB890")

LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 504.123 504.123">'
    # right arrow (blue)
    + _lg("tp1", 29.7722, 598.915, -11.6478, 598.915, *_BLUE)
    + _lg("tp2", -5.9435, 572.0046, 8.6535, 609.0616, *_BLUE)
    # left arrow (orange)
    + _lg("tp3", -46.6008, 598.915, -13.9998, 598.915, *_ORANGE)
    + _lg("tp4", -20.9979, 567.0046, -35.4579, 605.6107, *_ORANGE)
    # bottom arrow (blue)
    + _lg("tp5", 33.172, 561.2034, -43.318, 602.6234, *_BLUE)
    + _lg("tp6", -41.1342, 590.6439, -4.0732, 576.0439, *_BLUE)
    # top arrow (green)
    + _lg("tp7", -14.1332, 631.1826, -14.2502, 598.5795, *_GREEN)
    + _lg("tp8", -46.1302, 605.6952, -7.5182, 620.1562, *_GREEN)
    + '<polygon style="fill:url(#tp1);" points="252.069,367.002 320.63,435.554 '
      '504.123,252.062 320.63,68.569 252.069,137.121 367.002,252.062"/>'
    + '<polyline style="fill:url(#tp2);" points="367.002,252.062 252.069,367.002 '
      '320.63,435.554 504.123,252.062"/>'
    + '<polygon style="fill:url(#tp3);" points="137.129,252.062 252.069,137.121 '
      '183.509,68.569 0,252.062 183.509,435.554 252.069,367.002"/>'
    + '<polyline style="fill:url(#tp4);" points="0,252.062 183.509,435.554 '
      '252.069,367.002 137.129,252.062"/>'
    + '<polygon style="fill:url(#tp5);" points="137.121,252.069 68.569,320.63 '
      '252.062,504.123 435.554,320.63 367.002,252.069 252.062,367.002"/>'
    + '<polyline style="fill:url(#tp6);" points="252.062,367.002 137.121,252.069 '
      '68.569,320.63 252.062,504.123"/>'
    + '<polygon style="fill:url(#tp7);" points="252.062,137.129 367.002,252.069 '
      '435.554,183.509 252.062,0 68.569,183.509 137.121,252.069"/>'
    + '<polyline style="fill:url(#tp8);" points="252.062,0 68.569,183.509 '
      '137.121,252.069 252.062,137.129"/>'
    + '</svg>'
)


# --- rendering -------------------------------------------------------------

def _render_px(svg_text, logical_size, tint=None, supersample=1):
    """Render *svg_text* into a transparent pixmap, crisp on hiDPI screens."""
    size = max(1, int(round(logical_size * supersample)))
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    if _HAS_SVG:
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        vb = renderer.viewBoxF()
        if vb.isValid() and vb.width() > 0 and vb.height() > 0:
            scale = min(size / vb.width(), size / vb.height())
            w = vb.width() * scale
            h = vb.height() * scale
            renderer.render(painter, QRectF((size - w) / 2.0, (size - h) / 2.0, w, h))
        else:
            renderer.render(painter)
        if tint is not None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(px.rect(), QColor(tint))
        painter.end()
    if supersample != 1:
        px.setDevicePixelRatio(float(supersample))
    return px


def monochrome_icon(name, color, size=22):
    """A crisp single-color :class:`QIcon` for one glyph."""
    if not _HAS_SVG:
        return QIcon()
    svg = ICONS.get(name)
    if not svg:
        return QIcon()
    return QIcon(_render_px(svg, size, tint=color, supersample=_SS))


def icon_pixmap(name, color, size=22):
    """A crisp single-color :class:`QPixmap` for one glyph."""
    svg = ICONS.get(name)
    if not _HAS_SVG or not svg:
        return QPixmap()
    return _render_px(svg, size, tint=color, supersample=_SS)


def logo_pixmap(size=64):
    """The recolored four-arrow logo as a crisp :class:`QPixmap`."""
    return _render_px(LOGO_SVG, size, tint=None, supersample=_SS)


def logo_icon(sizes=(16, 24, 32, 48, 64, 128, 256)):
    """The recolored four-arrow logo as a multi-resolution :class:`QIcon`."""
    if not _HAS_SVG:
        return QIcon()
    icon = QIcon()
    for s in sizes:
        icon.addPixmap(_render_px(LOGO_SVG, s, tint=None, supersample=1))
    return icon
