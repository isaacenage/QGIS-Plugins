# -*- coding: utf-8 -*-
"""SVG icon assets + rendering helpers for the dashboard chrome.

Icons are rendered to **crisp** ``QPixmap``\\ s via ``QSvgRenderer``. Two
flavours:

* **Monochrome action icons** for the left rail. Their artwork is embedded
  directly in the ``ICONS`` table below — no external files — and every glyph
  is re-tinted to one color with ``CompositionMode_SourceIn`` so the rail
  follows the active :class:`~theme.Theme` (light or dark). Because the tint
  recolors every opaque pixel, the stroke/fill colors baked into each glyph are
  irrelevant; only its shape matters.
* **The app logo** (``LOGO_SVG``) keeps its own pastel gradients and is rendered
  untouched — used for the window title-bar icon, the QGIS toolbar action, and
  the rail header.

**Crispness.** Every icon is supersampled (rendered at ``size × _SS``) and the
resulting pixmap is tagged with ``setDevicePixelRatio(_SS)``. Qt then *down*\\
scales it to whatever physical size the screen needs — and downscaling is
always sharp — so the icons stay crisp at 125/150/200 % Windows display
scaling instead of being upscaled from a too-small raster (the old blur).

``QtSvg`` ships with QGIS, but the import is still guarded: if it is somehow
absent every helper degrades to an empty / blank icon and callers fall back to
text, so the plugin never fails to load over a missing icon.
"""

from qgis.PyQt.QtCore import QByteArray, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap

try:
    from qgis.PyQt.QtSvg import QSvgRenderer
    _HAS_SVG = True
except ImportError:                       # pragma: no cover - QtSvg always present in QGIS
    _HAS_SVG = False

# Supersample factor: render this many times larger, then let Qt downscale.
# 4× keeps icons sharp up to 4.0 device-pixel-ratio screens.
_SS = 4

# --- embedded, stroke-based icons (24×24) ----------------------------------


def _stroke(body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="#000000" stroke-width="1.0" '
        'stroke-linecap="round" stroke-linejoin="round">{}</svg>'
    ).format(body)


ICONS = {
    # add a tile to the canvas
    "add_element": _stroke(
        '<rect x="3" y="3" width="18" height="18" rx="2.5"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'),
    # add a dashboard page (tab)
    "add_page": _stroke(
        '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>'
        '<polyline points="14 3 14 9 20 9"/>'
        '<line x1="12" y1="11.5" x2="12" y2="17.5"/>'
        '<line x1="9" y1="14.5" x2="15" y2="14.5"/>'),
    # cross-filter wiring (two interlocking chain links) — tinted to one color
    "connections": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2048 1280">'
        '<path d="m 1536,384 v 128 q 76,0 145,17 69,17 123,56 54,39 84,99 '
        '30,60 32,148 0,66 -25,124 -25,58 -69,101 -44,43 -102,69 -58,26 -124,26 '
        'h -512 q -66,0 -124,-25 -58,-25 -101,-69 -43,-44 -69,-102 -26,-58 -26,-124 '
        '0,-87 31,-147 31,-60 85,-99 54,-39 122,-56 68,-17 146,-18 V 384 h -64 '
        'q -93,0 -174,35 -81,35 -142,96 -61,61 -96,142 -35,81 -36,175 0,93 35,174 '
        '35,81 96,142 61,61 142,96 81,35 175,36 h 512 q 93,0 174,-35 81,-35 142,-96 '
        '61,-61 96,-142 35,-81 36,-175 0,-93 -35,-174 -35,-81 -96,-142 -61,-61 -142,-96 '
        '-81,-35 -175,-36 z M 896,896 V 768 q 76,0 145,-17 69,-17 123,-56 54,-39 84,-99 '
        '30,-60 32,-148 0,-66 -25,-124 -25,-58 -69,-101 -44,-43 -102,-69 -58,-26 -124,-26 '
        'H 448 q -66,0 -124,25 -58,25 -101,69 -43,44 -69,102 -26,58 -26,124 0,87 31,147 '
        '31,60 85,99 54,39 122,56 68,17 146,18 V 896 H 448 Q 355,896 274,861 193,826 132,765 '
        '71,704 36,623 1,542 0,448 0,355 35,274 70,193 131,132 192,71 273,36 354,1 448,0 '
        'h 512 q 93,0 174,35 81,35 142,96 61,61 96,142 35,81 36,175 0,93 -35,174 -35,81 -96,142 '
        '-61,61 -142,96 -81,35 -175,36 z"/>'
        '</svg>'),
    # appearance / theme (half-filled circle) — tinted to one color
    "appearance": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        '<path d="M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 '
        '3 7.02944 3 12C3 16.9706 7.02944 21 12 21Z" stroke="#000" stroke-width="1.0"/>'
        '<path d="M12 5.25V18.75C15.7279 18.75 18.75 15.7279 18.75 12C18.75 8.27208 '
        '15.7279 5.25 12 5.25Z" fill="#000"/>'
        '</svg>'),
    # style guide / open appearance (Fluent "style guide" glyph) — tinted
    "style_guide": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000">'
        '<path d="M14.0358344,2.77749671 C15.5028662,2.38440673 17.0107928,3.25500857 '
        '17.4038828,4.72204036 L20.1214828,14.8642615 C20.5145728,16.3312933 '
        '19.6439709,17.8392199 18.1769391,18.2323099 L11.8984213,19.9146337 '
        'C10.4313895,20.3077237 8.92346284,19.4371219 8.53037286,17.9700901 '
        'L5.81277289,7.8278689 C5.41968291,6.36083711 6.29028475,4.85291048 '
        '7.75731654,4.4598205 L14.0358344,2.77749671 Z M5.80276379,11.6579669 '
        'L7.56444704,18.2289091 C7.74541549,18.9042926 8.09965838,19.4869754 '
        '8.56653105,19.9419445 L8.12368161,19.9181345 C6.60697998,19.8386475 '
        '5.4418873,18.544681 5.52137427,17.0279794 L5.80276379,11.6579669 Z '
        'M14.424063,4.22638545 L8.1455451,5.90870924 C7.47871248,6.08738651 '
        '7.08298436,6.7728077 7.26166163,7.43964033 L9.9792616,17.5818615 '
        'C10.1579389,18.2486941 10.8433601,18.6444222 11.5101927,18.465745 '
        'L17.7887106,16.7834212 C18.4555432,16.6047439 18.8512713,15.9193227 '
        '18.672594,15.2524901 L15.9549941,5.11026892 C15.7763168,4.44343629 '
        '15.0908956,4.04770818 14.424063,4.22638545 Z M4.87817105,10.1797973 '
        'L4.52274473,16.9756434 C4.4861276,17.6743399 4.64319766,18.3383733 '
        '4.94700819,18.915604 L4.53260907,18.7550052 C3.11470293,18.210722 '
        '2.40649159,16.6200533 2.95077476,15.2021471 L4.87817105,10.1797973 Z '
        'M9.74118095,7.03407417 C10.2746471,6.89113236 10.822984,7.20771485 '
        '10.9659258,7.74118095 C11.1088676,8.27464706 10.7922851,8.82298401 '
        '10.258819,8.96592583 C9.72535294,9.10886764 9.17701599,8.79228515 '
        '9.03407417,8.25881905 C8.89113236,7.72535294 9.20771485,7.17701599 '
        '9.74118095,7.03407417 Z"/>'
        '</svg>'),
    # layout (2x2 grid of tiles) — Settings nav glyph
    "layout": _stroke(
        '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/>'
        '<rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/>'
        '<rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/>'
        '<rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>'),
    # spacing / element gap (an inner card inset within an outer one) —
    # Settings nav glyph
    "spacing": _stroke(
        '<rect x="3" y="3" width="18" height="18" rx="2.5"/>'
        '<rect x="7.5" y="7.5" width="9" height="9" rx="1.5"/>'),
    # info (circled "i") — Settings "About" nav glyph
    "info": _stroke(
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="11" x2="12" y2="16"/>'
        '<circle cx="12" cy="7.8" r="0.4"/>'),
    # undo (curved arrow returning anticlockwise to the left)
    "undo": _stroke(
        '<polyline points="8 7 4 11 8 15"/>'
        '<path d="M4 11h9a5 5 0 0 1 0 10h-3.5"/>'),
    # redo (mirror of undo — curved arrow returning clockwise to the right)
    "redo": _stroke(
        '<polyline points="16 7 20 11 16 15"/>'
        '<path d="M20 11h-9a5 5 0 0 0 0 10h3.5"/>'),
    # clear the active cross-filter (funnel + slash)
    "clear_filter": _stroke(
        '<path d="M3 4h18l-7 8.2V19l-4 2v-8.8z"/>'
        '<line x1="3.5" y1="3.5" x2="20.5" y2="20.5"/>'),
    # settings hub (gear) — opens the Settings dialog
    "settings": _stroke(
        '<circle cx="12" cy="12" r="3.1"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83'
        'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0'
        'v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83'
        'l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4'
        'h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83'
        'l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0'
        'v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83'
        'l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4'
        'h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    # save the dashboard to a .qdash file (floppy-disk outline)
    "save": _stroke(
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
        '<polyline points="17 21 17 13 7 13 7 21"/>'
        '<polyline points="7 3 7 8 15 8"/>'),
    # return to the Start screen (house)
    "home": _stroke(
        '<path d="M3 11.5 12 4l9 7.5"/>'
        '<path d="M5 10v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9"/>'
        '<rect x="9.5" y="14" width="5" height="6"/>'),
    # open a dashboard file (open folder)
    "open": _stroke(
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1"/>'
        '<path d="M3 8h17.5a1 1 0 0 1 .96 1.27l-2 7A2 2 0 0 1 17.5 18H5a2 2 0 0 1-2-2z"/>'),
    "zoom_out": _stroke(
        '<circle cx="11" cy="11" r="7"/>'
        '<line x1="20.5" y1="20.5" x2="16" y2="16"/>'
        '<line x1="8" y1="11" x2="14" y2="11"/>'),
    # fit / reset (corner brackets + center dot) — tinted to one color
    "zoom_reset": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#000" stroke-width="1.0" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4.5 9V4.5H9"/>'
        '<path d="M15 4.5H19.5V9"/>'
        '<path d="M4.5 15V19.5H9"/>'
        '<path d="M15 19.5H19.5V15"/>'
        '<circle cx="12" cy="12" r="2.1" stroke-width="1.0"/>'
        '</svg>'),
    "zoom_in": _stroke(
        '<circle cx="11" cy="11" r="7"/>'
        '<line x1="20.5" y1="20.5" x2="16" y2="16"/>'
        '<line x1="8" y1="11" x2="14" y2="11"/>'
        '<line x1="11" y1="8" x2="11" y2="14"/>'),
    # auto-arrange / fit tiles to page (grid cells inside a frame)
    "auto_arrange": _stroke(
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<line x1="3" y1="12" x2="21" y2="12"/>'
        '<line x1="12" y1="3" x2="12" y2="12"/>'),
    # export / share (box with an arrow leaving it) — tinted to one color
    "export": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#000" stroke-width="1.0" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M13 11L21.2 2.80005"/>'
        '<path d="M22 6.8V2H17.2"/>'
        '<path d="M11 2H9C4 2 2 4 2 9V15C2 20 4 22 9 22H15C20 22 22 20 22 15V13"/>'
        '</svg>'),
    # layout locked (closed padlock) — tinted to one color
    "lock": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000">'
        '<path fill-rule="evenodd" clip-rule="evenodd" d="M5.25 10.0546V8C5.25 '
        '4.27208 8.27208 1.25 12 1.25C15.7279 1.25 18.75 4.27208 18.75 8V10.0546C19.8648 '
        '10.1379 20.5907 10.348 21.1213 10.8787C22 11.7574 22 13.1716 22 16C22 18.8284 '
        '22 20.2426 21.1213 21.1213C20.2426 22 18.8284 22 16 22H8C5.17157 22 3.75736 22 '
        '2.87868 21.1213C2 20.2426 2 18.8284 2 16C2 13.1716 2 11.7574 2.87868 '
        '10.8787C3.40931 10.348 4.13525 10.1379 5.25 10.0546ZM6.75 8C6.75 5.10051 9.10051 '
        '2.75 12 2.75C14.8995 2.75 17.25 5.10051 17.25 8V10.0036C16.867 10 16.4515 10 16 '
        '10H8C7.54849 10 7.13301 10 6.75 10.0036V8ZM14 16C14 17.1046 13.1046 18 12 '
        '18C10.8954 18 10 17.1046 10 16C10 14.8954 10.8954 14 12 14C13.1046 14 14 14.8954 '
        '14 16Z"/>'
        '</svg>'),
    # layout unlocked (open padlock) — tinted to one color
    "unlock": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000">'
        '<path fill-rule="evenodd" clip-rule="evenodd" d="M6.75 8C6.75 5.10051 9.10051 '
        '2.75 12 2.75C14.4453 2.75 16.5018 4.42242 17.0846 6.68694C17.1879 7.08808 '
        '17.5968 7.32957 17.9979 7.22633C18.3991 7.12308 18.6405 6.7142 18.5373 '
        '6.31306C17.788 3.4019 15.1463 1.25 12 1.25C8.27208 1.25 5.25 4.27208 5.25 '
        '8V10.0546C4.13525 10.1379 3.40931 10.348 2.87868 10.8787C2 11.7574 2 13.1716 2 '
        '16C2 18.8284 2 20.2426 2.87868 21.1213C3.75736 22 5.17157 22 8 22H16C18.8284 22 '
        '20.2426 22 21.1213 21.1213C22 20.2426 22 18.8284 22 16C22 13.1716 22 11.7574 '
        '21.1213 10.8787C20.2426 10 18.8284 10 16 10H8C7.54849 10 7.13301 10 6.75 '
        '10.0036V8ZM14 16C14 17.1046 13.1046 18 12 18C10.8954 18 10 17.1046 10 16C10 '
        '14.8954 10.8954 14 12 14C13.1046 14 14 14.8954 14 16Z"/>'
        '</svg>'),

    # --- element-type glyphs (the Add-element picker) ----------------------
    # One per registered element type; keyed "el_<type_name>" so the picker
    # can look them up generically. Same monochrome stroke style as the rail
    # glyphs above, so they tint to the active theme.
    # indicator — a gauge with a needle (one big KPI value)
    "el_indicator": _stroke(
        '<path d="M4.5 16a7.5 7.5 0 0 1 15 0"/>'
        '<line x1="12" y1="16" x2="16" y2="11.5"/>'
        '<circle cx="12" cy="16" r="1.1"/>'),
    # chart — three vertical bars on a baseline
    "el_chart": _stroke(
        '<line x1="4" y1="18.5" x2="20" y2="18.5"/>'
        '<rect x="5.6" y="11" width="3.1" height="7" rx="0.6"/>'
        '<rect x="10.4" y="6.5" width="3.1" height="11.5" rx="0.6"/>'
        '<rect x="15.2" y="13" width="3.1" height="5" rx="0.6"/>'),
    # pivot / matrix — a table with a header row + first column
    "el_pivot": _stroke(
        '<rect x="3.5" y="4.5" width="17" height="15" rx="1.8"/>'
        '<line x1="3.5" y1="9.5" x2="20.5" y2="9.5"/>'
        '<line x1="9" y1="4.5" x2="9" y2="19.5"/>'),
    # list — bulleted rows
    "el_list": _stroke(
        '<line x1="9" y1="7" x2="19" y2="7"/>'
        '<line x1="9" y1="12" x2="19" y2="12"/>'
        '<line x1="9" y1="17" x2="19" y2="17"/>'
        '<circle cx="5.2" cy="7" r="0.5"/>'
        '<circle cx="5.2" cy="12" r="0.5"/>'
        '<circle cx="5.2" cy="17" r="0.5"/>'),
    # map — a location pin (the live canvas mirror)
    "el_map": _stroke(
        '<path d="M12 21c4.2-4.3 6-7.2 6-10a6 6 0 1 0-12 0c0 2.8 1.8 5.7 6 10z"/>'
        '<circle cx="12" cy="11" r="2.2"/>'),
    # category selector — a dropdown box with a value + chevron
    "el_category_selector": _stroke(
        '<rect x="3.5" y="7.5" width="17" height="9" rx="2"/>'
        '<line x1="6" y1="12" x2="11" y2="12"/>'
        '<polyline points="13.6 11 15.8 13.2 18 11"/>'),
    # filter — a funnel (definition-query builder)
    "el_filter": _stroke(
        '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>'),
    # legend — stacked swatch + label rows (a map legend)
    "el_legend": _stroke(
        '<rect x="4" y="6" width="3" height="3" rx="0.6"/>'
        '<line x1="9.5" y1="7.5" x2="19" y2="7.5"/>'
        '<rect x="4" y="11" width="3" height="3" rx="0.6"/>'
        '<line x1="9.5" y1="12.5" x2="19" y2="12.5"/>'
        '<rect x="4" y="16" width="3" height="3" rx="0.6"/>'
        '<line x1="9.5" y1="17.5" x2="19" y2="17.5"/>'),
    # text / heading — a serif "T"
    "el_text": _stroke(
        '<path d="M6 6.5V5h12v1.5"/>'
        '<line x1="12" y1="5" x2="12" y2="19"/>'
        '<line x1="9.2" y1="19" x2="14.8" y2="19"/>'),
    # image — a framed picture (sun + mountains)
    "el_image": _stroke(
        '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
        '<circle cx="8.6" cy="10" r="1.5"/>'
        '<path d="M4 17.5l4.8-4.6 3.2 3.1 3.4-3.3 5 5"/>'),
    # header — a brand banner: a logo square + title line in a top band
    "el_header": _stroke(
        '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
        '<line x1="3.5" y1="10.5" x2="20.5" y2="10.5"/>'
        '<rect x="6" y="6.7" width="2.4" height="2.4" rx="0.5"/>'
        '<line x1="9.6" y1="7.9" x2="15.5" y2="7.9"/>'),
}


# --- the gradient app logo (pastel blue / orange / green branding) ---------
#
# Three ascending parallelogram "bars", each a soft pastel: blue (bottom),
# orange (middle), green (top) — the analytics palette ui-ux-pro-max returns
# for a dashboard (blue data + amber highlight + green categorical).
#
# The source art is drawn in a y-up space and flipped with ``matrix(1,0,0,-1)``;
# we keep the flip on an inner <g> and shift the viewBox to
# ``0 -492.481 … 492.481`` so the flipped geometry lands inside the rendered
# area while the userSpace gradients stay correct. (Transforms on the root
# <svg> are unreliable across renderers.)
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 -492.481 492.481 492.481">'
    '<linearGradient id="dl1" gradientUnits="userSpaceOnUse" '
    'x1="-36.6002" y1="621.3422" x2="-17.2782" y2="547.7642" '
    'gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)">'
    '<stop offset="0" style="stop-color:#A7D2F5"/>'
    '<stop offset="1" style="stop-color:#5E97D0"/></linearGradient>'
    '<linearGradient id="dl2" gradientUnits="userSpaceOnUse" '
    'x1="-27.0735" y1="620.7541" x2="-11.7045" y2="560.3241" '
    'gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)">'
    '<stop offset="0" style="stop-color:#F8CDA6"/>'
    '<stop offset="1" style="stop-color:#E89A5C"/></linearGradient>'
    '<linearGradient id="dl3" gradientUnits="userSpaceOnUse" '
    'x1="14.0324" y1="554.688" x2="-10.4176" y2="584.028" '
    'gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)">'
    '<stop offset="0" style="stop-color:#A9DCC2"/>'
    '<stop offset="1" style="stop-color:#6FB890"/></linearGradient>'
    '<g transform="matrix(1,0,0,-1,0,0)">'
    '<polygon style="fill:url(#dl1);" '
    'points="25.687,297.141 135.735,0 271.455,0 161.398,297.141"/>'
    '<polygon style="fill:url(#dl2);" '
    'points="123.337,394.807 233.409,97.674 369.144,97.674 259.072,394.807"/>'
    '<polygon style="fill:url(#dl3);" '
    'points="221.026,492.481 331.083,195.348 466.794,195.348 356.746,492.481"/>'
    '</g></svg>')


# --- rendering -------------------------------------------------------------

def _render_px(svg_text, logical_size, tint=None, supersample=1):
    """Render *svg_text* into a transparent pixmap, crisp on hiDPI screens.

    The pixmap is drawn at ``logical_size × supersample`` physical pixels and
    tagged with that device-pixel-ratio, so it reports ``logical_size`` to
    layouts but carries enough resolution for Qt to downscale sharply. When
    *tint* is given every opaque pixel is recolored to it (monochrome rail
    glyphs); otherwise the artwork's own colors are kept (the logo).
    """
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
            renderer.render(
                painter,
                QRectF(
                    (size - w) / 2.0,
                    (size - h) / 2.0,
                    w,
                    h))
        else:
            renderer.render(painter)
        if tint is not None:
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(px.rect(), QColor(tint))
        painter.end()
    if supersample != 1:
        px.setDevicePixelRatio(float(supersample))
    return px


def monochrome_icon(name, color, size=22):
    """A crisp single-color :class:`QIcon` for one rail glyph."""
    if not _HAS_SVG:
        return QIcon()
    svg = ICONS.get(name)
    if not svg:
        return QIcon()
    return QIcon(_render_px(svg, size, tint=color, supersample=_SS))


def icon_pixmap(name, color, size=22):
    """A crisp single-color :class:`QPixmap` for one glyph (no :class:`QIcon`).

    Like :func:`monochrome_icon` but returns the pixmap directly, rendered at
    *size* logical px so large glyphs stay sharp instead of being upscaled.
    """
    svg = ICONS.get(name)
    if not _HAS_SVG or not svg:
        return QPixmap()
    return _render_px(svg, size, tint=color, supersample=_SS)


def logo_pixmap(size=64):
    """The gradient logo as a crisp ``QPixmap`` (for the rail header label)."""
    return _render_px(LOGO_SVG, size, tint=None, supersample=_SS)


def logo_icon(sizes=(16, 24, 32, 48, 64, 128, 256)):
    """The gradient logo as a multi-resolution :class:`QIcon`.

    Returns an empty icon when ``QtSvg`` is unavailable so callers can fall
    back (``QIcon.isNull()`` is reliable in that case). Pixmaps are rendered at
    their exact native sizes — the window system picks the best one — so the
    title-bar / taskbar icon stays sharp.
    """
    if not _HAS_SVG:
        return QIcon()
    icon = QIcon()
    for s in sizes:
        icon.addPixmap(_render_px(LOGO_SVG, s, tint=None, supersample=1))
    return icon
