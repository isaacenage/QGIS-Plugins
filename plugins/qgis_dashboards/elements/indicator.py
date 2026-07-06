# -*- coding: utf-8 -*-
"""Indicator element.

Mirrors the ArcGIS indicator: a big value, optional reference value, and a
trend/delta. ArcGIS divides the visualization into top/middle/bottom text
areas; we expose the same three slots. The value comes from a QgsExpression
aggregate (e.g. sum("pop")), so it reacts to the dashboard filter.

Beyond the data binding the tile is configurable like a real dashboard card:

* an optional **icon** (PNG / JPG / SVG) placed left / right / above the value,
* an explicit **value text size**, and
* a value **animation** (odometer / rolling / typewriter / fade) played whenever
  the number changes — see :mod:`indicator_anim`.
"""

from qgis.PyQt.QtWidgets import QLabel, QWidget, QGridLayout
from qgis.PyQt.QtCore import Qt
from .base import DashboardElement
from .media import icon_pixmap
from .indicator_anim import IndicatorValue


class IndicatorElement(DashboardElement):
    type_name = "indicator"

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self.top = QLabel("")
        self.bottom = QLabel("")
        for lbl, name in ((self.top, "indTop"), (self.bottom, "indBottom")):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setObjectName(name)

        # icon + animated value share a small grid so the icon can sit left,
        # right or above the value without rebuilding layouts.
        self.icon = QLabel()
        self.icon.setObjectName("indIcon")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value = IndicatorValue()
        self._value_host = QWidget()
        self._vgrid = QGridLayout(self._value_host)
        self._vgrid.setContentsMargins(0, 0, 0, 0)
        self._vgrid.setHorizontalSpacing(10)
        self._vgrid.setVerticalSpacing(6)

        self.body.addStretch(1)
        self.body.addWidget(self.top)
        self.body.addWidget(self._value_host)
        self.body.addWidget(self.bottom)
        self.body.addStretch(1)

        self._delta_sign = 0   # last reference delta sign, for trend coloring
        self.apply_theme()
        self.refresh()

    # ---- formatting ----

    def _fmt(self, v):
        if v is None:
            return self.config.get("no_value_text", "No data")
        if isinstance(v, float):
            dp = int(self.config.get("decimals", 0) or 0)
            v = round(v, dp)
            if dp == 0:
                v = int(v)
        prefix = self.config.get("prefix", "")
        suffix = self.config.get("suffix", "")
        if isinstance(v, (int, float)):
            return "{}{:,}{}".format(prefix, v, suffix)
        return "{}{}{}".format(prefix, v, suffix)

    # ---- appearance ----

    def _restyle(self):
        th = self.effective_theme()
        # value role
        size = int(self.style_get("value_px", th.value_size))
        color = self.style_get("value_color", th.accent)
        family = self.style_get("value_font", th.heading_family())
        weight = int(self.style_get("value_weight", 700))
        italic = bool(self.style_get("value_italic", False))
        self.value.apply_style(color, size, family, weight, italic)
        # top label role
        self.apply_text_role(self.top, "top", color=th.text_muted,
                             font=th.font_family, size=th.font_size, weight=400)
        # reference / trend role — trend colors win when there is a delta
        if self._delta_sign > 0:
            force = self.style_get("trend_up_color", "#13a10e")
        elif self._delta_sign < 0:
            force = self.style_get("trend_down_color", "#d13438")
        else:
            force = None
        self.apply_text_role(self.bottom, "ref", color=th.text_muted,
                             font=th.font_family, size=th.font_size, weight=400,
                             force_color=force)

    def _rebuild_value_host(self, position, has_icon, gap):
        """Lay out the icon + value, honoring the configured *gap* (px).

        The grid columns must not stretch, or the two cells split the whole
        tile width and drift far apart (``<icon>        <value>``). We keep the
        icon/value pair adjacent — the gap between them is exactly the grid
        spacing — and center the pair with stretchable spacer columns.
        """
        af = Qt.AlignmentFlag
        self._vgrid.removeWidget(self.icon)
        self._vgrid.removeWidget(self.value)
        # clear any spacer stretch a previous position left behind
        for c in range(4):
            self._vgrid.setColumnStretch(c, 0)
        self._vgrid.setHorizontalSpacing(gap)
        self._vgrid.setVerticalSpacing(gap)
        if not has_icon:
            self.icon.hide()
            self._vgrid.addWidget(self.value, 0, 0, af.AlignCenter)
            return
        self.icon.show()
        if position == "top":
            # single column stretches -> AlignHCenter centers each; the gap is
            # the vertical spacing between the two rows.
            self._vgrid.addWidget(self.icon, 0, 0, af.AlignHCenter | af.AlignBottom)
            self._vgrid.addWidget(self.value, 1, 0, af.AlignHCenter | af.AlignTop)
            return
        # side-by-side: spacer columns 0 and 3 absorb the extra width so the
        # icon/value pair stays together and centered.
        self._vgrid.setColumnStretch(0, 1)
        self._vgrid.setColumnStretch(3, 1)
        if position == "right":
            self._vgrid.addWidget(self.value, 0, 1, af.AlignRight | af.AlignVCenter)
            self._vgrid.addWidget(self.icon, 0, 2, af.AlignLeft | af.AlignVCenter)
        else:   # left (default)
            self._vgrid.addWidget(self.icon, 0, 1, af.AlignRight | af.AlignVCenter)
            self._vgrid.addWidget(self.value, 0, 2, af.AlignLeft | af.AlignVCenter)

    # ---- data ----

    def refresh(self):
        value = self.evaluate(self.config.get("value_expression", "count(1)"))
        text = self._fmt(value)

        # optional icon (icon image is content; size/position are style)
        path = self.config.get("icon_path")
        icon_size = int(self.style_get("icon_size", 48))
        pixmap = icon_pixmap(path, icon_size) if path else None
        has_icon = pixmap is not None
        if has_icon:
            self.icon.setPixmap(pixmap)
        gap = int(self.config.get("icon_gap", 10) or 0)
        self._rebuild_value_host(
            self.style_get("icon_position", "left"), has_icon, gap)

        # animated value (animation type + duration are style)
        self.value.set_options(
            self.style_get("animation", ""),
            int(self.style_get("animation_duration_ms", 900)),
            self._fmt)
        self.value.set_value(value if isinstance(value, (int, float)) else None, text)

        # reference value + delta, like ArcGIS reference/trend
        self._delta_sign = 0
        ref_expr = self.config.get("reference_expression")
        if ref_expr and value is not None:
            ref = self.evaluate(ref_expr)
            if ref is not None and isinstance(value, (int, float)):
                delta = value - ref
                self._delta_sign = 1 if delta > 0 else (-1 if delta < 0 else 0)
                arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
                self.bottom.setText("{} {} vs ref".format(arrow, self._fmt(abs(delta))))
        self.top.setText(self.config.get("top_text", ""))
        self.top.setVisible(bool(self.config.get("top_text")))
        self.bottom.setVisible(bool(ref_expr))

        # restyle last so the value/labels reflect the new delta sign + theme
        self._restyle()
