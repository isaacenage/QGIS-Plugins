# -*- coding: utf-8 -*-
"""Bundled UI font registration.

The dashboard ships the **Inter** family (SIL Open Font License) so its
"modern analytics" look is identical on every machine, independent of whatever
fonts QGIS happens to have installed. The four weights live under
``resources/fonts/Inter/`` and are registered with Qt's application font
database the first time :func:`ensure_fonts_registered` is called.

Registration is **idempotent and resilient**: it runs once, caches the result,
and never raises — if a file is missing or the font engine refuses it, callers
simply fall back to the platform default sans-serif (the QSS font stack ends in
``sans-serif``), so the plugin never fails to load over a font.
"""

import os

from qgis.PyQt.QtGui import QFontDatabase

_FONT_DIR = os.path.join(os.path.dirname(__file__), "resources", "fonts", "Inter")
_FONT_FILES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
)

# Preferred UI family; the QSS always appends fallbacks after it.
UI_FONT_FAMILY = "Inter"
UI_FONT_STACK = '"Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif'

_registered = None   # None = not yet attempted; list = registered families


def ensure_fonts_registered():
    """Register the bundled Inter weights once; return the family names found.

    Safe to call repeatedly and before/after a theme change. Returns an empty
    list when QtGui has no application-font support or the files are absent.
    """
    global _registered
    if _registered is not None:
        return list(_registered)

    families = []
    for filename in _FONT_FILES:
        path = os.path.join(_FONT_DIR, filename)
        if not os.path.exists(path):
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(path)
        except Exception:                 # pragma: no cover - defensive
            continue
        if font_id == -1:
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family and family not in families:
                families.append(family)

    _registered = families
    return list(_registered)


def ui_font_family(default=UI_FONT_FAMILY):
    """The registered UI family ("Inter") or *default* if registration failed."""
    families = ensure_fonts_registered()
    return families[0] if families else default
