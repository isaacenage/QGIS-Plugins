# -*- coding: utf-8 -*-
"""QPainter chart painters.

Each painter is a ``QWidget`` that draws one chart type from uniform
``[(category, value)]`` data and emits :pyattr:`categoryClicked` when the user
clicks a bar / point / slice. They share a base that holds theme colors and the
data contract so :class:`~..chart.ChartElement` can swap painters by key.

Charts are drawn with plain QPainter rather than QtChart, because the QtChart
Qt module is optional and is not shipped with every QGIS/PyQt build.
"""

import math

from qgis.PyQt.QtCore import Qt, pyqtSignal, QRectF, QPointF
from qgis.PyQt.QtGui import QPainter, QColor, QPen, QPolygonF, QPainterPath
from qgis.PyQt.QtWidgets import QWidget, QSizePolicy

from ...theme import DEFAULT_SERIES
from .. import chart_data

EXPLODE_PX = 10.0


def fmt_num(v):
    if isinstance(v, float):
        if v == int(v):
            v = int(v)
        else:
            return "{:,.2f}".format(v)
    if isinstance(v, int):
        return "{:,}".format(v)
    return str(v)


class _ChartPainter(QWidget):
    """Base for all chart painters; holds data + theme, emits category clicks."""

    categoryClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []            # list of (category, value)
        self._selected = None
        self._inner = 0.0          # pie/donut inner-radius fraction
        self._bg = QColor("#ffffff")
        self._palette = list(DEFAULT_SERIES)
        self._bar = QColor("#0f6cbd")
        self._bar_sel = QColor("#9aa7b4")
        self._text = QColor("#1b2733")
        self._muted = QColor("#6b7682")
        self._grid = QColor("#e3e8ee")
        self._show_values = True   # draw value labels (Plot appearance role)
        # The painter draws into ``self.rect()`` every paintEvent, so it tracks
        # the tile size automatically — but only if the widget is actually
        # allowed to take the tile's size. A hard minimum height would pin the
        # chart once a tile shrank below it (the chart would overflow/clip and
        # stop following the resize), so allow it to shrink to nothing and let
        # it expand to fill the body in both directions (mirrors the
        # ``setMinimumSize(1, 1)`` fill pattern used by image/text tiles).
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_theme(self, theme):
        # chart background honors the element opacity so a translucent tile shows
        # the canvas through the chart (the chart widget composites over the
        # tile).
        bg = QColor(theme.chart_bg)
        try:
            bg.setAlphaF(theme.tile_alpha())
        except AttributeError:      # older theme without opacity support
            pass
        self._bg = bg
        self._palette = list(theme.series or DEFAULT_SERIES)
        self._bar = QColor(theme.series_color(0))
        self._bar_sel = QColor(theme.text_muted)
        self._text = QColor(theme.text)
        self._muted = QColor(theme.text_muted)
        self._grid = QColor(getattr(theme, "grid_line", "#e3e8ee"))
        self.update()

    def set_style(self, style):
        """Apply per-tile Plot-role overrides (axis/label color, font, value
        labels). Called after :meth:`set_theme`; absent keys keep theme values.
        """
        ac = style.get("axis_color")
        if ac:
            self._muted = QColor(ac)
        fam = style.get("axis_font")
        px = style.get("axis_px")
        if fam or px:
            f = self.font()
            if fam:
                f.setFamily(str(fam))
            if px:
                f.setPixelSize(int(px))
            self.setFont(f)
        self._show_values = bool(style.get("show_value_labels", True))
        self.update()

    def set_data(self, data, selected=None, inner=0.0):
        # The series shapes (grouped/stacked) pass a {categories, series,
        # matrix} dict; everything else passes a list of tuples. ``list(dict)``
        # would silently yield the dict's KEYS, so a series painter would then
        # call ``.get`` on a list and raise inside paintEvent — which, with a
        # live QPainter, hard-crashes QGIS. Keep dicts intact.
        self._data = data if isinstance(data, dict) else list(data)
        self._selected = selected
        self._inner = inner
        self.update()

    def _color(self, i):
        return QColor(self._palette[i % len(self._palette)])

    def _no_data(self, p, rect):
        p.setPen(self._muted)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
        p.end()


class BarPainter(_ChartPainter):
    """Vertical bars with clickable columns and value labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (left, slot_w, n)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        top_pad = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + top_pad
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = rect.width() / float(n)
        bar_w = slot_w * 0.6
        self._geom = (rect.left(), slot_w, n)

        for i, (cat, v) in enumerate(self._data):
            slot_left = rect.left() + i * slot_w
            h = plot_h * (float(v) / max_v)
            y = plot_bottom - h
            color = self._bar_sel if cat == self._selected else self._color(i)
            p.fillRect(
                QRectF(slot_left + (slot_w - bar_w) / 2, y, bar_w, h), color)
            if self._show_values:
                p.setPen(self._text)
                p.drawText(
                    QRectF(
                        slot_left,
                        y - top_pad,
                        slot_w,
                        top_pad),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                    fmt_num(v))
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    slot_left,
                    plot_bottom + 2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        left, slot_w, n = self._geom
        idx = int((e.pos().x() - left) / slot_w)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class BarHPainter(_ChartPainter):
    """Horizontal bars; category labels at the left."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (top, slot_h, n, label_w)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_w = min(int(rect.width() * 0.32), 140)
        val_w = 52
        plot_left = rect.left() + label_w
        plot_w = max(rect.width() - label_w - val_w, 1)
        slot_h = rect.height() / float(n)
        bar_h = min(slot_h * 0.6, 26)
        self._geom = (rect.top(), slot_h, n, label_w)

        for i, (cat, v) in enumerate(self._data):
            slot_top = rect.top() + i * slot_h
            w = plot_w * (float(v) / max_v)
            y = slot_top + (slot_h - bar_h) / 2
            color = self._bar_sel if cat == self._selected else self._color(i)
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, label_w - 6)
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    rect.left(),
                    slot_top,
                    label_w - 6,
                    slot_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cat_txt)
            p.fillRect(QRectF(plot_left, y, w, bar_h), color)
            if self._show_values:
                p.setPen(self._text)
                p.drawText(
                    QRectF(
                        plot_left + w + 4,
                        slot_top,
                        val_w - 6,
                        slot_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    fmt_num(v))
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        top, slot_h, n, _label_w = self._geom
        idx = int((e.pos().y() - top) / slot_h)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class LinePainter(_ChartPainter):
    """Line connecting per-category values; markers are clickable."""

    fill = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []   # [(x, y, category)]

    def _line_path(self, pts):
        """Build the connecting path; subclasses override for step/spline."""
        path = QPainterPath()
        if pts:
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
        return path

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._points = []
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        top_pad = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + top_pad
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = rect.width() / float(n)

        pts = []
        for i, (cat, v) in enumerate(self._data):
            x = rect.left() + slot_w * (i + 0.5)
            y = plot_bottom - plot_h * (float(v) / max_v)
            pts.append(QPointF(x, y))
            self._points.append((x, y, str(cat)))

        path = self._line_path(pts)
        if self.fill and pts:
            fill_path = QPainterPath(path)
            fill_path.lineTo(pts[-1].x(), plot_bottom)
            fill_path.lineTo(pts[0].x(), plot_bottom)
            fill_path.closeSubpath()
            fill_c = QColor(self._color(0))
            fill_c.setAlpha(60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill_c)
            p.drawPath(fill_path)

        p.setPen(QPen(self._color(0), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        for i, (cat, v) in enumerate(self._data):
            x, y, _c = self._points[i]
            sel = (cat == self._selected)
            r = 5 if sel else 3
            p.setBrush(self._bar_sel if sel else self._color(0))
            p.setPen(QPen(self._bg, 1))
            p.drawEllipse(QPointF(x, y), r, r)
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    x - slot_w / 2,
                    plot_bottom + 2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        p.end()

    def mousePressEvent(self, e):
        if not self._points:
            return
        px = e.pos().x()
        best, best_dx = None, None
        for x, _y, cat in self._points:
            dx = abs(px - x)
            if best_dx is None or dx < best_dx:
                best, best_dx = cat, dx
        if best is not None:
            self.categoryClicked.emit(best)


class AreaPainter(LinePainter):
    """Line chart with the area below the curve filled."""

    fill = True


class PiePainter(_ChartPainter):
    """Pie/donut with clickable slices and a legend (inner>0 == donut)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hit = None   # (cx, cy, radius, inner_r, [(label, start, span)])

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._hit = None
        total = sum(float(v) for _, v in self._data)
        if total <= 0:
            return self._no_data(p, rect)

        legend_w = 0
        if rect.width() > 260:
            legend_w = min(int(rect.width() * 0.4), 180)
        pie_area = rect.adjusted(0, 0, -legend_w, 0)
        diameter = max(min(pie_area.width(), pie_area.height()) - 4, 10)
        cx = pie_area.left() + pie_area.width() / 2.0
        cy = pie_area.top() + pie_area.height() / 2.0
        radius = diameter / 2.0
        inner_r = radius * self._inner if self._inner else 0.0

        slices = []
        start = 90.0
        for i, (label, value) in enumerate(self._data):
            span = 360.0 * float(value) / total
            ox, oy = 0.0, 0.0
            if label == self._selected:
                mid = math.radians(start + span / 2.0)
                ox = math.cos(mid) * EXPLODE_PX
                oy = -math.sin(mid) * EXPLODE_PX
            box = QRectF(
                cx - radius + ox,
                cy - radius + oy,
                diameter,
                diameter)
            p.setBrush(self._color(i))
            p.setPen(QColor("#ffffff"))
            p.drawPie(box, int(round(start * 16)), int(round(span * 16)))
            slices.append((label, start, span))
            start += span

        if inner_r > 0:
            p.setBrush(self._bg)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        self._hit = (cx, cy, radius, inner_r, slices)

        if legend_w:
            self._paint_legend(p, QRectF(rect.right() - legend_w, rect.top(),
                                         legend_w, rect.height()))
        p.end()

    def _paint_legend(self, p, area):
        fm = p.fontMetrics()
        row_h = fm.height() + 6
        y = area.top()
        for i, (label, value) in enumerate(self._data):
            if y + row_h > area.bottom():
                break
            p.setBrush(self._color(i))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(area.left(), y + 3, 11, 11))
            p.setPen(self._text)
            txt = fm.elidedText(
                "{} ({})".format(
                    label, fmt_num(value)), Qt.TextElideMode.ElideRight, int(
                    area.width() - 18))
            p.drawText(
                QRectF(
                    area.left() +
                    18,
                    y,
                    area.width() -
                    18,
                    row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                txt)
            y += row_h

    def mousePressEvent(self, e):
        if not self._hit:
            return
        cx, cy, radius, inner_r, slices = self._hit
        dx = e.pos().x() - cx
        dy = e.pos().y() - cy
        dist = math.hypot(dx, dy)
        if dist > radius or (inner_r and dist < inner_r):
            return
        angle = math.degrees(math.atan2(-dy, dx)) % 360.0
        for label, start, span in slices:
            rel = (angle - (start % 360.0)) % 360.0
            if rel < span:
                self.categoryClicked.emit(str(label))
                return


class StepPainter(LinePainter):
    """Line that holds each value then steps to the next (no diagonal)."""

    def _line_path(self, pts):
        path = QPainterPath()
        if pts:
            path.moveTo(pts[0])
            for a, b in zip(pts, pts[1:]):
                midx = (a.x() + b.x()) / 2.0
                path.lineTo(midx, a.y())
                path.lineTo(midx, b.y())
                path.lineTo(b)
        return path


class SplinePainter(LinePainter):
    """Line smoothed with a Catmull-Rom-style cubic through the points."""

    def _line_path(self, pts):
        path = QPainterPath()
        if not pts:
            return path
        path.moveTo(pts[0])
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < n else p2
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                         p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                         p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path


class LollipopPainter(BarPainter):
    """Vertical lollipops: a thin stem with a circle marker at the value."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        top_pad = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + top_pad
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = rect.width() / float(n)
        self._geom = (rect.left(), slot_w, n)

        for i, (cat, v) in enumerate(self._data):
            cx = rect.left() + slot_w * (i + 0.5)
            h = plot_h * (float(v) / max_v)
            y = plot_bottom - h
            color = self._bar_sel if cat == self._selected else self._color(i)
            r = 6 if cat == self._selected else 5
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(cx, plot_bottom), QPointF(cx, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, y), r, r)
            p.setPen(self._text)
            p.drawText(
                QRectF(
                    cx - slot_w / 2,
                    y - top_pad,
                    slot_w,
                    top_pad),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                fmt_num(v))
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    cx - slot_w / 2,
                    plot_bottom + 2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        p.end()


class LollipopHPainter(BarHPainter):
    """Horizontal lollipops: a stem from the axis with a marker at the value."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_w = min(int(rect.width() * 0.32), 140)
        val_w = 52
        plot_left = rect.left() + label_w
        plot_w = max(rect.width() - label_w - val_w, 1)
        slot_h = rect.height() / float(n)
        self._geom = (rect.top(), slot_h, n, label_w)

        for i, (cat, v) in enumerate(self._data):
            slot_top = rect.top() + i * slot_h
            cy = slot_top + slot_h / 2.0
            w = plot_w * (float(v) / max_v)
            color = self._bar_sel if cat == self._selected else self._color(i)
            r = 6 if cat == self._selected else 5
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, label_w - 6)
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    rect.left(),
                    slot_top,
                    label_w - 6,
                    slot_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cat_txt)
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(plot_left, cy), QPointF(plot_left + w, cy))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(plot_left + w, cy), r, r)
            p.setPen(self._text)
            p.drawText(
                QRectF(
                    plot_left + w + 8,
                    slot_top,
                    val_w - 6,
                    slot_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fmt_num(v))
        p.end()


class DotPainter(BarHPainter):
    """Cleveland dot plot: a single marker per category on a faint baseline."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_w = min(int(rect.width() * 0.32), 140)
        val_w = 52
        plot_left = rect.left() + label_w
        plot_w = max(rect.width() - label_w - val_w, 1)
        slot_h = rect.height() / float(n)
        self._geom = (rect.top(), slot_h, n, label_w)

        for i, (cat, v) in enumerate(self._data):
            slot_top = rect.top() + i * slot_h
            cy = slot_top + slot_h / 2.0
            x = plot_left + plot_w * (float(v) / max_v)
            color = self._bar_sel if cat == self._selected else self._color(i)
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, label_w - 6)
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    rect.left(),
                    slot_top,
                    label_w - 6,
                    slot_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cat_txt)
            p.setPen(QPen(self._grid, 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(plot_left, cy), QPointF(x, cy))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            r = 7 if cat == self._selected else 5
            p.drawEllipse(QPointF(x, cy), r, r)
            p.setPen(self._text)
            p.drawText(
                QRectF(
                    x + 8,
                    slot_top,
                    val_w - 6,
                    slot_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fmt_num(v))
        p.end()


class _PolarPainter(_ChartPainter):
    """Shared geometry for charts drawn on a center+radius polar layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._polar = None   # (cx, cy, radius)

    def _center(self, rect):
        diameter = max(min(rect.width(), rect.height()) - 4, 10)
        cx = rect.left() + rect.width() / 2.0
        cy = rect.top() + rect.height() / 2.0
        return cx, cy, diameter / 2.0


class RosePainter(_PolarPainter):
    """Nightingale rose: equal angular slices, radius proportional to value."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._polar = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        cx, cy, radius = self._center(rect)
        self._polar = (cx, cy, radius)
        span = 360.0 / n
        for i, (cat, v) in enumerate(self._data):
            r = radius * math.sqrt(float(v) / max_v)   # area-true radius
            start = 90.0 - (i + 1) * span
            box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            color = self._bar_sel if cat == self._selected else self._color(i)
            p.setBrush(color)
            p.setPen(QColor("#ffffff"))
            p.drawPie(box, int(round(start * 16)), int(round(span * 16)))
        p.end()

    def mousePressEvent(self, e):
        if not self._polar:
            return
        cx, cy, radius = self._polar
        dx, dy = e.pos().x() - cx, e.pos().y() - cy
        if math.hypot(dx, dy) > radius:
            return
        n = len(self._data)
        span = 360.0 / n
        angle = math.degrees(math.atan2(-dy, dx)) % 360.0
        idx = int(((90.0 - angle) % 360.0) / span)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class RadialBarPainter(_PolarPainter):
    """Circular bar chart: each category is a ring track; arc sweep == value."""

    SWEEP = 270.0

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._polar = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        cx, cy, radius = self._center(rect)
        inner = radius * (self._inner or 0.25)
        track_gap = (radius - inner) / float(n)
        thick = max(track_gap * 0.6, 3.0)
        self._polar = (cx, cy, radius, inner, track_gap, max_v)
        fm = p.fontMetrics()

        for i, (cat, v) in enumerate(self._data):
            r = radius - (i + 0.5) * track_gap
            box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            color = self._bar_sel if cat == self._selected else self._color(i)
            p.setPen(QPen(QColor(self._grid), thick, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(box, int(round(90 * 16)), int(round(-self.SWEEP * 16)))
            sweep = self.SWEEP * (float(v) / max_v)
            p.setPen(QPen(color, thick, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(box, int(round(90 * 16)), int(round(-sweep * 16)))
            label = fm.elidedText("{} ({})".format(cat, fmt_num(v)),
                                  Qt.TextElideMode.ElideRight, int(r))
            p.setPen(self._muted)
            p.drawText(QPointF(cx + 3, cy - r + fm.ascent() / 2.0), label)
        p.end()

    def mousePressEvent(self, e):
        if not self._polar:
            return
        cx, cy, radius, inner, track_gap, _max = self._polar
        dist = math.hypot(e.pos().x() - cx, e.pos().y() - cy)
        if dist > radius or dist < inner:
            return
        idx = int((radius - dist) / track_gap)
        if 0 <= idx < len(self._data):
            self.categoryClicked.emit(str(self._data[idx][0]))


class RadarPainter(_PolarPainter):
    """Single-series radar/spider: one axis per category, value as distance."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._polar = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        cx, cy, radius = self._center(rect)
        radius *= 0.78          # leave room for axis labels
        self._polar = (cx, cy, radius, max_v)
        fm = p.fontMetrics()

        # concentric grid rings
        p.setPen(QPen(self._grid, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(1, 4):
            rr = radius * k / 3.0
            p.drawEllipse(QPointF(cx, cy), rr, rr)

        pts = []
        for i in range(n):
            ang = math.radians(90.0 - i * 360.0 / n)
            ax = cx + math.cos(ang) * radius
            ay = cy - math.sin(ang) * radius
            p.setPen(QPen(self._grid, 1))
            p.drawLine(QPointF(cx, cy), QPointF(ax, ay))
            cat, v = self._data[i]
            r = radius * (float(v) / max_v)
            pts.append(QPointF(cx + math.cos(ang) * r, cy - math.sin(ang) * r))
            lx = cx + math.cos(ang) * (radius + 12)
            ly = cy - math.sin(ang) * (radius + 12)
            txt = fm.elidedText(str(cat), Qt.TextElideMode.ElideRight, 70)
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    lx - 36,
                    ly - fm.height() / 2.0,
                    72,
                    fm.height()),
                Qt.AlignmentFlag.AlignCenter,
                txt)

        if pts:
            fill = QColor(self._color(0))
            fill.setAlpha(70)
            p.setPen(QPen(self._color(0), 2))
            p.setBrush(fill)
            p.drawPolygon(QPolygonF(pts + [pts[0]]))
            p.setBrush(self._color(0))
            p.setPen(Qt.PenStyle.NoPen)
            for i, pt in enumerate(pts):
                cat = self._data[i][0]
                p.setBrush(self._bar_sel if cat ==
                           self._selected else self._color(0))
                p.drawEllipse(pt, 4, 4)
        p.end()

    def mousePressEvent(self, e):
        if not self._polar:
            return
        cx, cy, radius, _max = self._polar
        n = len(self._data)
        px, py = e.pos().x(), e.pos().y()
        ang = math.degrees(math.atan2(-(py - cy), px - cx)) % 360.0
        idx = int(round(((90.0 - ang) % 360.0) / (360.0 / n))) % n
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class FunnelPainter(_ChartPainter):
    """Stacked centered bars, each width proportional to its value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (top, slot_h, n)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_v = max((float(v) for _, v in self._data), default=0) or 1.0
        slot_h = rect.height() / float(n)
        bar_h = min(slot_h * 0.7, 46)
        cx = rect.left() + rect.width() / 2.0
        self._geom = (rect.top(), slot_h, n)

        for i, (cat, v) in enumerate(self._data):
            w = rect.width() * (float(v) / max_v)
            top = rect.top() + i * slot_h + (slot_h - bar_h) / 2.0
            color = self._bar_sel if cat == self._selected else self._color(i)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(cx - w / 2.0, top, w, bar_h), 3, 3)
            p.setPen(self._text)
            p.drawText(QRectF(rect.left(), top, rect.width(), bar_h),
                       Qt.AlignmentFlag.AlignCenter,
                       "{}  {}".format(cat, fmt_num(v)))
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        top, slot_h, n = self._geom
        idx = int((e.pos().y() - top) / slot_h)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class WaterfallPainter(_ChartPainter):
    """Running-total bars: each floats from the prior cumulative to the next."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (left, slot_w, n)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        cum, lo, hi = 0.0, 0.0, 0.0
        steps = []
        for cat, v in self._data:
            start = cum
            cum += float(v)
            steps.append((cat, start, cum, float(v)))
            lo = min(lo, start, cum)
            hi = max(hi, start, cum)
        rng = (hi - lo) or 1.0

        fm = p.fontMetrics()
        label_h = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + fm.height() + 4
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = rect.width() / float(n)
        bar_w = slot_w * 0.6
        self._geom = (rect.left(), slot_w, n)

        def y_of(val):
            return plot_bottom - plot_h * ((val - lo) / rng)

        up = QColor(self._color(0))
        down = QColor(self._bar_sel)
        for i, (cat, start, end, delta) in enumerate(steps):
            slot_left = rect.left() + i * slot_w
            y0, y1 = y_of(start), y_of(end)
            top, h = min(y0, y1), abs(y1 - y0)
            sel = cat == self._selected
            color = self._muted if sel else (up if delta >= 0 else down)
            p.fillRect(QRectF(slot_left + (slot_w - bar_w) /
                       2, top, bar_w, max(h, 1)), color)
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    slot_left,
                    plot_bottom + 2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        left, slot_w, n = self._geom
        idx = int((e.pos().x() - left) / slot_w)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class TreemapPainter(_ChartPainter):
    """Squarified treemap; rectangle area is proportional to value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rects = []   # [(category, QRectF)]

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._rects = []
        if not self._data or sum(float(v) for _, v in self._data) <= 0:
            return self._no_data(p, rect)

        values = [max(float(v), 0.0) for _, v in self._data]
        layout = chart_data.squarify(values, rect.left(), rect.top(),
                                     rect.width(), rect.height())
        fm = p.fontMetrics()
        for idx, rx, ry, rw, rh in layout:
            cat, v = self._data[idx]
            r = QRectF(rx, ry, rw, rh)
            self._rects.append((str(cat), r))
            sel = str(cat) == self._selected
            color = self._bar_sel if sel else self._color(idx)
            p.setPen(QColor("#ffffff"))
            p.setBrush(color)
            p.drawRect(r)
            if rw > 38 and rh > fm.height():
                p.setPen(self._on_color_text(color))
                txt = fm.elidedText("{} ({})".format(cat, fmt_num(v)),
                                    Qt.TextElideMode.ElideRight, int(rw - 6))
                p.drawText(
                    r.adjusted(
                        4, 3, -4, -3), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, txt)
        p.end()

    def _on_color_text(self, color):
        # readable label color: dark on light fills, white on dark fills
        luma = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        return QColor("#1b2733") if luma > 150 else QColor("#ffffff")

    def mousePressEvent(self, e):
        for cat, r in self._rects:
            if r.contains(QPointF(e.pos())):
                self.categoryClicked.emit(cat)
                return


class _SeriesPainter(_ChartPainter):
    """Base for series-shaped charts; draws a shared swatch legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (left, slot_w, categories)

    def _legend_rows(self, series):
        return series

    def _paint_legend(self, p, area, series):
        fm = p.fontMetrics()
        row_h = fm.height() + 6
        y = area.top()
        for j, name in enumerate(series):
            if y + row_h > area.bottom():
                break
            p.setBrush(self._color(j))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(area.left(), y + 3, 11, 11))
            p.setPen(self._text)
            txt = fm.elidedText(str(name), Qt.TextElideMode.ElideRight,
                                int(area.width() - 18))
            p.drawText(
                QRectF(
                    area.left() +
                    18,
                    y,
                    area.width() -
                    18,
                    row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                txt)
            y += row_h

    def _payload(self):
        """Series payload as a dict, tolerating any unexpected type."""
        return self._data if isinstance(self._data, dict) else {}

    def _plot_rect(self, rect):
        legend_w = 0
        series = self._payload().get("series", [])
        if rect.width() > 280 and series:
            legend_w = min(int(rect.width() * 0.32), 160)
        return rect.adjusted(0, 0, -legend_w, 0), legend_w

    def mousePressEvent(self, e):
        if not self._geom:
            return
        left, slot_w, cats = self._geom
        idx = int((e.pos().x() - left) / slot_w)
        if 0 <= idx < len(cats):
            self.categoryClicked.emit(str(cats[idx]))


class GroupedBarPainter(_SeriesPainter):
    """Clustered bars: one bar per series within each category slot."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        data = self._payload()
        cats, series, matrix = (data.get("categories", []),
                                data.get("series", []), data.get("matrix", []))
        if not cats or not series:
            return self._no_data(p, rect)

        plot, legend_w = self._plot_rect(rect)
        max_v = max(
            (max(row) if row else 0 for row in matrix),
            default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        plot_bottom = plot.bottom() - label_h
        plot_top = plot.top() + 4
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = plot.width() / float(len(cats))
        group_w = slot_w * 0.8
        bar_w = group_w / float(len(series))
        self._geom = (plot.left(), slot_w, cats)

        for i, cat in enumerate(cats):
            slot_left = plot.left() + i * slot_w + (slot_w - group_w) / 2.0
            sel = str(cat) == self._selected
            for j in range(len(series)):
                v = matrix[i][j] if j < len(matrix[i]) else 0
                h = plot_h * (float(v) / max_v)
                x = slot_left + j * bar_w
                color = self._color(j)
                if sel:
                    color = QColor(color)
                    color.setAlpha(150)
                p.fillRect(QRectF(x, plot_bottom - h, bar_w * 0.9, h), color)
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    plot.left() +
                    i *
                    slot_w,
                    plot_bottom +
                    2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        if legend_w:
            self._paint_legend(p, QRectF(rect.right() - legend_w, rect.top(),
                                         legend_w, rect.height()), series)
        p.end()


class StackedBarPainter(_SeriesPainter):
    """Stacked bars: series stack within each category column."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        data = self._payload()
        cats, series, matrix = (data.get("categories", []),
                                data.get("series", []), data.get("matrix", []))
        if not cats or not series:
            return self._no_data(p, rect)

        plot, legend_w = self._plot_rect(rect)
        totals = [sum(row) for row in matrix]
        max_v = max(totals, default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        plot_bottom = plot.bottom() - label_h
        plot_top = plot.top() + 4
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = plot.width() / float(len(cats))
        bar_w = slot_w * 0.6
        self._geom = (plot.left(), slot_w, cats)

        for i, cat in enumerate(cats):
            slot_left = plot.left() + i * slot_w
            x = slot_left + (slot_w - bar_w) / 2.0
            y = plot_bottom
            sel = str(cat) == self._selected
            for j in range(len(series)):
                v = matrix[i][j] if j < len(matrix[i]) else 0
                h = plot_h * (float(v) / max_v)
                color = self._color(j)
                if sel:
                    color = QColor(color)
                    color.setAlpha(150)
                p.fillRect(QRectF(x, y - h, bar_w, h), color)
                y -= h
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    slot_left,
                    plot_bottom + 2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        if legend_w:
            self._paint_legend(p, QRectF(rect.right() - legend_w, rect.top(),
                                         legend_w, rect.height()), series)
        p.end()


class _AxesPainter(_ChartPainter):
    """Base for x/y plots; draws axes and maps data coords to pixels."""

    def _bounds(self, xs, ys):
        xlo, xhi = min(xs), max(xs)
        ylo, yhi = min(ys), max(ys)
        if xhi == xlo:
            xhi += 1
        if yhi == ylo:
            yhi += 1
        return xlo, xhi, ylo, yhi

    def _axes(self, p, rect):
        plot = rect.adjusted(34, 6, -6, -24)
        p.setPen(QPen(self._grid, 1))
        p.drawLine(
            QPointF(
                plot.left(), plot.top()), QPointF(
                plot.left(), plot.bottom()))
        p.drawLine(
            QPointF(
                plot.left(), plot.bottom()), QPointF(
                plot.right(), plot.bottom()))
        return plot


class ScatterPainter(_AxesPainter):
    """Point cloud of (x, y) features. Display-only (no cross-filter)."""

    RADIUS = 4

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        if not self._data:
            return self._no_data(p, rect)

        xs = [d[0] for d in self._data]
        ys = [d[1] for d in self._data]
        xlo, xhi, ylo, yhi = self._bounds(xs, ys)
        plot = self._axes(p, rect)

        def px(x):
            return plot.left() + (x - xlo) / (xhi - xlo) * plot.width()

        def py(y):
            return plot.bottom() - (y - ylo) / (yhi - ylo) * plot.height()

        fill = QColor(self._color(0))
        fill.setAlpha(170)
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(fill)
        for d in self._data:
            self._draw_point(p, px(d[0]), py(d[1]), d)
        self._draw_ticks(p, plot, xlo, xhi, ylo, yhi)
        p.end()

    def _draw_point(self, p, x, y, _d):
        p.drawEllipse(QPointF(x, y), self.RADIUS, self.RADIUS)

    def _draw_ticks(self, p, plot, xlo, xhi, ylo, yhi):
        fm = p.fontMetrics()
        p.setPen(self._muted)
        p.drawText(QRectF(plot.left(), plot.bottom() + 4, 60, fm.height()),
                   Qt.AlignmentFlag.AlignLeft, fmt_num(xlo))
        p.drawText(
            QRectF(
                plot.right() - 60,
                plot.bottom() + 4,
                60,
                fm.height()),
            Qt.AlignmentFlag.AlignRight,
            fmt_num(xhi))
        p.drawText(QRectF(0, plot.top() - 2, 30, fm.height()),
                   Qt.AlignmentFlag.AlignRight, fmt_num(yhi))
        p.drawText(QRectF(0, plot.bottom() - fm.height(), 30, fm.height()),
                   Qt.AlignmentFlag.AlignRight, fmt_num(ylo))


class BubblePainter(ScatterPainter):
    """Scatter where marker radius encodes a third (size) field."""

    def paintEvent(self, _e):
        sizes = [d[2] for d in self._data] if self._data else []
        self._smax = max(sizes) if sizes else 1.0
        super().paintEvent(_e)

    def _draw_point(self, p, x, y, d):
        smax = getattr(self, "_smax", 1.0) or 1.0
        r = 4 + 18 * math.sqrt(max(d[2], 0) / smax)
        p.drawEllipse(QPointF(x, y), r, r)


class HistogramPainter(_ChartPainter):
    """Adjacent (gap-free) bars over numeric bins; click pushes a range."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (left, bar_w, n)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        max_c = max((float(d[1]) for d in self._data), default=0) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + fm.height() + 4
        plot_h = max(plot_bottom - plot_top, 1)
        bar_w = rect.width() / float(n)
        self._geom = (rect.left(), bar_w, n)

        for i, (label, count, _lo, _hi) in enumerate(self._data):
            x = rect.left() + i * bar_w
            h = plot_h * (float(count) / max_c)
            sel = label == self._selected
            color = self._bar_sel if sel else self._color(0)
            p.fillRect(QRectF(x, plot_bottom - h, bar_w, h), color)
            p.setPen(QColor("#ffffff"))
            p.drawRect(QRectF(x, plot_bottom - h, bar_w, h))
            if bar_w > 26:
                p.setPen(self._muted)
                edge = fm.elidedText(
                    str(label), Qt.TextElideMode.ElideRight, int(bar_w))
                p.drawText(
                    QRectF(
                        x,
                        plot_bottom +
                        2,
                        bar_w,
                        label_h),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    edge)
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        left, bar_w, n = self._geom
        idx = int((e.pos().x() - left) / bar_w)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


class CandlestickPainter(_ChartPainter):
    """OHLC candles: high-low wick + open-close body, colored up/down."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom = None   # (left, slot_w, n)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg)
        rect = self.rect().adjusted(8, 8, -8, -8)
        self._geom = None
        if not self._data:
            return self._no_data(p, rect)

        n = len(self._data)
        highs = [d[2] for d in self._data]
        lows = [d[3] for d in self._data]
        hi, lo = max(highs), min(lows)
        rng = (hi - lo) or 1.0
        fm = p.fontMetrics()
        label_h = fm.height() + 4
        plot_bottom = rect.bottom() - label_h
        plot_top = rect.top() + 4
        plot_h = max(plot_bottom - plot_top, 1)
        slot_w = rect.width() / float(n)
        body_w = slot_w * 0.6
        self._geom = (rect.left(), slot_w, n)

        def y_of(val):
            return plot_bottom - plot_h * ((val - lo) / rng)

        up = QColor(self._color(0))
        down = QColor(self._bar_sel)
        for i, (cat, o, h, l, c) in enumerate(self._data):
            cx = rect.left() + slot_w * (i + 0.5)
            sel = str(cat) == self._selected
            color = self._muted if sel else (up if c >= o else down)
            p.setPen(QPen(color, 1))
            p.drawLine(QPointF(cx, y_of(h)), QPointF(cx, y_of(l)))
            yo, yc = y_of(o), y_of(c)
            top, bh = min(yo, yc), max(abs(yc - yo), 1)
            p.setBrush(color)
            p.setPen(QColor("#ffffff"))
            p.drawRect(QRectF(cx - body_w / 2, top, body_w, bh))
            cat_txt = fm.elidedText(
                str(cat), Qt.TextElideMode.ElideRight, int(slot_w))
            p.setPen(self._muted)
            p.drawText(
                QRectF(
                    rect.left() +
                    i *
                    slot_w,
                    plot_bottom +
                    2,
                    slot_w,
                    label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                cat_txt)
        p.end()

    def mousePressEvent(self, e):
        if not self._geom:
            return
        left, slot_w, n = self._geom
        idx = int((e.pos().x() - left) / slot_w)
        if 0 <= idx < n:
            self.categoryClicked.emit(str(self._data[idx][0]))


PAINTERS = {
    "bar": BarPainter,
    "barh": BarHPainter,
    "lollipop": LollipopPainter,
    "lollipop_h": LollipopHPainter,
    "dot": DotPainter,
    "line": LinePainter,
    "step": StepPainter,
    "spline": SplinePainter,
    "area": AreaPainter,
    "waterfall": WaterfallPainter,
    "pie": PiePainter,
    "rose": RosePainter,
    "radial_bar": RadialBarPainter,
    "radar": RadarPainter,
    "funnel": FunnelPainter,
    "treemap": TreemapPainter,
    "grouped_bar": GroupedBarPainter,
    "stacked_bar": StackedBarPainter,
    "scatter": ScatterPainter,
    "bubble": BubblePainter,
    "histogram": HistogramPainter,
    "candlestick": CandlestickPainter,
}
