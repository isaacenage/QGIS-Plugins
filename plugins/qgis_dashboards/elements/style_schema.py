# -*- coding: utf-8 -*-
"""Declarative per-element style schema.

The per-tile **Tile Appearance** editor is built dynamically from this registry,
exactly as the Configure form is built per type and charts are driven by
``chart_specs``. Each element type maps to an ordered list of
:class:`StyleSection`\\s, each holding :class:`StyleField`\\s that describe one
styleable property of one *role* (the indicator value, a table header, the tile
title, …).

This module is **pure** (no Qt / QGIS imports) so it is unit-testable on its
own; :mod:`tile_style_form` turns the schema into widgets and
:class:`~elements.base.DashboardElement` reads the resulting keys at paint time.

Field values are stored flat in ``config["style"]`` next to the few theme-shaped
override keys (``surface_bg``/``border``/``chart_bg``/``series``) that
``Theme.merged_with`` consumes for the baseline tile look. The role keys defined
here are deliberately namespaced *away* from ``theme.OVERRIDE_KEYS`` (e.g.
``value_px`` not ``value_size``, ``title_px`` not ``title_size``) so the theme
merge never misreads a per-role key as a global override.
"""

# ---- field kinds -----------------------------------------------------------
COLOR = "color"
FONT = "font"           # font family
SIZE = "size"           # integer px / count spinner
WEIGHT = "weight"       # font weight (400/500/600/700)
ITALIC = "italic"       # bool
ALIGN = "align"         # left / center / right
BOOL = "bool"
CHOICE = "choice"       # opts["choices"] = [(label, data), ...]
PALETTE = "palette"     # list of colors (the chart series)
TILE_SIZE = "tile_size"  # special: edits tile geometry, not config["style"]

# The synthetic key used for the geometry (tile size) field; excluded from the
# style override dict (it writes the tile's pixel size instead).
SIZE_KEY = "__size__"

WEIGHTS = [("Normal", 400), ("Medium", 500), ("Semibold", 600), ("Bold", 700)]
ALIGNS = [("Left", "left"), ("Center", "center"), ("Right", "right")]


class StyleField(object):
    """One styleable property.

    ``default`` is the literal fallback; ``theme_key`` (when set) names the
    :class:`~theme.Theme` attribute the field's default tracks (so an untouched
    control reflects the live theme). ``theme_key="heading_family"`` is resolved
    via ``Theme.heading_family()``.
    """

    __slots__ = ("key", "label", "kind", "default", "theme_key", "opts")

    def __init__(self, key, label, kind, default=None, theme_key=None, **opts):
        self.key = key
        self.label = label
        self.kind = kind
        self.default = default
        self.theme_key = theme_key
        self.opts = opts


class StyleSection(object):
    """A titled group of :class:`StyleField`\\s."""

    __slots__ = ("title", "fields")

    def __init__(self, title, fields):
        self.title = title
        self.fields = list(fields)


# ---- reusable section builders --------------------------------------------

def _tile_section(background=True, border_label="Tile border"):
    fields = [StyleField(SIZE_KEY, "Tile size", TILE_SIZE)]
    if background:
        fields.append(StyleField("surface_bg", "Tile background", COLOR,
                                 theme_key="surface_bg"))
    fields.append(
        StyleField(
            "border",
            border_label,
            COLOR,
            theme_key="border"))
    return StyleSection("Tile", fields)


def _text_role(prefix, title, *, color_tk="text", color_default=None,
               font_tk="font_family", size_tk="font_size", size_default=None,
               weight=400, align=None, lo=6, hi=200):
    """A full text-role section: color, font, size, weight, italic (+ align)."""
    fields = [
        StyleField(prefix + "_color", "Color", COLOR,
                   default=color_default, theme_key=color_tk),
        StyleField(prefix + "_font", "Font", FONT, theme_key=font_tk),
        StyleField(prefix + "_px", "Size (px)", SIZE,
                   default=size_default, theme_key=size_tk, lo=lo, hi=hi),
        StyleField(prefix + "_weight", "Weight", WEIGHT, default=weight),
        StyleField(prefix + "_italic", "Italic", ITALIC, default=False),
    ]
    if align is not None:
        fields.append(StyleField(prefix + "_align", "Alignment", ALIGN,
                                 default=align))
    return StyleSection(title, fields)


def _title_section():
    return _text_role("title", "Title", color_tk="text",
                      font_tk="heading_family", size_tk="title_size",
                      weight=600, align="left", lo=8, hi=48)


def _table_fields(rows_default, *, selection=True):
    fields = [
        StyleField("header_bg", "Header background", COLOR, theme_key="zebra"),
        StyleField("header_color", "Header text", COLOR, theme_key="text"),
        StyleField(
            "header_font",
            "Header font",
            FONT,
            theme_key="font_family"),
        StyleField("header_px", "Header size (px)", SIZE,
                   theme_key="font_size", lo=6, hi=48),
        StyleField("header_weight", "Header weight", WEIGHT, default=600),
        StyleField("row_color", "Row text", COLOR, theme_key="text"),
        StyleField("row_font", "Row font", FONT, theme_key="font_family"),
        StyleField("row_px", "Row size (px)", SIZE,
                   theme_key="font_size", lo=6, hi=48),
        StyleField("zebra_color", "Alternating row", COLOR, theme_key="zebra"),
        StyleField("grid_color", "Gridline", COLOR, theme_key="border"),
    ]
    if selection:
        fields.append(StyleField("sel_color", "Selected row", COLOR,
                                 theme_key="selection"))
    fields.append(StyleField("rows_shown", "Rows shown", SIZE,
                             default=rows_default, lo=1, hi=5000))
    return fields


# ---- the registry ----------------------------------------------------------

_ICON_POS = [("Left of value", "left"), ("Right of value", "right"),
             ("Above value", "top")]
_ANIM = [("None", "none"), ("Odometer count-up", "odometer"),
         ("Rolling digits", "rolling"), ("Typewriter", "typewriter"),
         ("Fade / flash", "fade")]
_FIT = [("Fit (keep aspect)", "contain"), ("Stretch to fill", "stretch")]
_LOGO_SLOT = [("Left of title", "left"), ("Right of title", "right"),
              ("Above title", "above"), ("Below title", "below")]


def _indicator_schema():
    return [
        _tile_section(),
        _text_role("value", "Value", color_tk="accent",
                   font_tk="heading_family", size_tk="value_size", weight=700),
        _text_role("top", "Top label", color_tk="text_muted", weight=400),
        StyleSection("Reference / trend", _text_role(
            "ref", "Reference / trend", color_tk="text_muted",
            weight=400).fields + [
            StyleField("trend_up_color", "Trend up color", COLOR,
                       default="#13a10e"),
            StyleField("trend_down_color", "Trend down color", COLOR,
                       default="#d13438"),
        ]),
        StyleSection("Icon", [
            StyleField("icon_size", "Icon size (px)", SIZE, default=48,
                       lo=12, hi=256),
            StyleField("icon_position", "Icon position", CHOICE,
                       default="left", choices=_ICON_POS),
        ]),
        StyleSection("Value animation", [
            StyleField("animation", "Animation", CHOICE, default="none",
                       choices=_ANIM),
            StyleField("animation_duration_ms", "Duration (ms)", SIZE,
                       default=900, lo=100, hi=5000, step=50),
        ]),
        _title_section(),
    ]


def _chart_schema():
    return [
        _tile_section(),
        StyleSection("Plot", [
            StyleField("chart_bg", "Chart background", COLOR,
                       theme_key="chart_bg"),
            StyleField("series", "Series colors", PALETTE, theme_key="series"),
            StyleField("axis_color", "Axis & label color", COLOR,
                       theme_key="text_muted"),
            StyleField(
                "axis_font",
                "Label font",
                FONT,
                theme_key="font_family"),
            StyleField("axis_px", "Label size (px)", SIZE,
                       theme_key="font_size", lo=6, hi=48),
            StyleField("show_value_labels", "Show value labels", BOOL,
                       default=True),
            StyleField("max_categories", "Max categories", SIZE, default=12,
                       lo=1, hi=50),
        ]),
        _title_section(),
    ]


def _list_schema():
    return [
        _tile_section(),
        StyleSection("Table", _table_fields(200, selection=True)),
        _title_section(),
    ]


def _pivot_schema():
    return [
        _tile_section(),
        StyleSection("Table", _table_fields(50, selection=False) + [
            StyleField("cols_shown", "Columns shown", SIZE, default=20,
                       lo=1, hi=500),
        ]),
        StyleSection("Totals", [
            StyleField("total_color", "Totals color", COLOR, theme_key="text"),
            StyleField("total_weight", "Totals weight", WEIGHT, default=700),
        ]),
        _title_section(),
    ]


def _map_schema():
    return [
        _tile_section(background=False, border_label="Border & popup outline"),
        StyleSection("Map", [
            StyleField(
                "map_bg",
                "Map background",
                COLOR,
                theme_key="surface_bg"),
        ]),
        StyleSection("Identify popup", [
            StyleField("surface_bg", "Popup background", COLOR,
                       theme_key="surface_bg"),
            StyleField("text", "Popup text", COLOR, theme_key="text"),
        ]),
    ]


def _category_selector_schema():
    return [
        _tile_section(),
        StyleSection("Dropdown", [
            StyleField("combo_bg", "Control background", COLOR,
                       theme_key="surface_bg"),
            StyleField("combo_color", "Text color", COLOR, theme_key="text"),
            StyleField("combo_font", "Font", FONT, theme_key="font_family"),
            StyleField("combo_px", "Size (px)", SIZE, theme_key="font_size",
                       lo=6, hi=48),
            StyleField("combo_border", "Border", COLOR, theme_key="border"),
            StyleField("combo_accent", "Highlight", COLOR, theme_key="accent"),
        ]),
        _title_section(),
    ]


def _text_schema():
    return [
        _tile_section(),
        StyleSection("Text", [
            StyleField("text_font", "Font", FONT, theme_key="font_family"),
            StyleField("text_px", "Size (px)", SIZE, theme_key="font_size",
                       lo=6, hi=200),
            StyleField("text_color", "Color", COLOR, theme_key="text"),
            StyleField("text_weight", "Weight", WEIGHT, default=400),
            StyleField("text_italic", "Italic", ITALIC, default=False),
            StyleField("text_align", "Alignment", ALIGN, default="left"),
        ]),
    ]


def _image_schema():
    return [
        _tile_section(),
        StyleSection("Image", [
            StyleField("fit", "Scaling", CHOICE, default="contain",
                       choices=_FIT),
            StyleField("img_align", "Alignment", ALIGN, default="center"),
        ]),
    ]


def _header_schema():
    return [
        _tile_section(),
        StyleSection("Title", [
            StyleField("title_color", "Color", COLOR, theme_key="text"),
            StyleField("title_font", "Font", FONT, theme_key="font_family"),
            StyleField(
                "title_px",
                "Size (px)",
                SIZE,
                default=22,
                lo=8,
                hi=200),
            StyleField("title_weight", "Weight", WEIGHT, default=700),
            StyleField("title_italic", "Italic", ITALIC, default=False),
            StyleField("title_align", "Alignment", ALIGN, default="left"),
        ]),
        StyleSection("Logo", [
            StyleField("logo_size", "Logo size (px)", SIZE, default=40,
                       lo=12, hi=400),
            StyleField("logo_slot", "Logo position", CHOICE, default="left",
                       choices=_LOGO_SLOT),
        ]),
    ]


STYLE_SCHEMAS = {
    "indicator": _indicator_schema(),
    "chart": _chart_schema(),
    "list": _list_schema(),
    "pivot": _pivot_schema(),
    "map": _map_schema(),
    "category_selector": _category_selector_schema(),
    "text": _text_schema(),
    "image": _image_schema(),
    "header": _header_schema(),
}


# ---- pure helpers ----------------------------------------------------------

def sections_for(type_name):
    """The ordered sections for *type_name* (empty list if unknown)."""
    return STYLE_SCHEMAS.get(type_name, [])


def fields_for(type_name):
    """Every :class:`StyleField` for *type_name*, flattened across sections."""
    out = []
    for section in sections_for(type_name):
        out.extend(section.fields)
    return out


def style_keys(type_name):
    """The config-style keys a type owns (excludes the geometry field)."""
    return [f.key for f in fields_for(type_name) if f.kind != TILE_SIZE]


def default_for(field, theme):
    """Resolve a field's default value against *theme*.

    A ``theme_key`` wins (so untouched controls track the live theme);
    ``"heading_family"`` resolves via the method, everything else via attribute.
    Falls back to the field's literal ``default``.
    """
    tk = field.theme_key
    if tk:
        if tk == "heading_family":
            return theme.heading_family()
        return getattr(theme, tk, field.default)
    return field.default
