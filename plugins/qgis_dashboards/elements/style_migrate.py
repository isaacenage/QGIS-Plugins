# -*- coding: utf-8 -*-
"""Legacy-config → per-tile-style migration (pure, no Qt / QGIS).

The clean Configure⇄Appearance split moved every *visual* setting out of the
element config and into ``config["style"]`` (read by each element's
``_restyle``). Dashboards saved before the split keep those settings as
top-level config keys, so this helper relocates them into ``config["style"]``
when an element is constructed/loaded. It is idempotent (a second pass finds the
legacy keys already gone) and never clobbers a value the user already set in
``style``.
"""

# Per type: (legacy top-level key, target style key). Keys whose name is
# unchanged still move *namespace* (top-level config -> config["style"]) because
# the element now reads them via ``style_get``.
_MOVES = {
    "text": [("align", "text_align")],
    "header": [
        ("font_family", "title_font"),
        ("font_size", "title_px"),
        ("align", "title_align"),
        ("logo_slot", "logo_slot"),
        ("logo_size", "logo_size"),
    ],
    "indicator": [
        ("value_size", "value_px"),
        ("icon_size", "icon_size"),
        ("icon_position", "icon_position"),
        ("animation", "animation"),
        ("animation_duration_ms", "animation_duration_ms"),
    ],
    "image": [("fit", "fit")],
    "list": [("max_rows", "rows_shown")],
    "pivot": [("max_rows", "rows_shown"), ("max_cols", "cols_shown")],
    "chart": [("max_categories", "max_categories")],
}


def migrate_element_style(config, type_name, theme=None):
    """Move legacy top-level visual keys in *config* into ``config["style"]``.

    Mutates and returns *config* (the codebase mutates element configs in
    place). When *theme* is given, a legacy ``heading=True`` text tile is mapped
    to an explicit bold + enlarged size that reproduces the old heading look.
    """
    if not isinstance(config, dict):
        return config
    style = config.get("style")
    if not isinstance(style, dict):
        style = {}

    for legacy, target in _MOVES.get(type_name, []):
        if legacy in config:
            val = config.pop(legacy)
            style.setdefault(target, val)

    if type_name == "text" and "heading" in config:
        if config.pop("heading"):
            style.setdefault("text_weight", 700)
            px = int(round(theme.title_size * 1.7)
                     ) if theme is not None else 22
            style.setdefault("text_px", px)

    if style:
        config["style"] = style
    return config
