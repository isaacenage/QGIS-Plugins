# -*- coding: utf-8 -*-
"""Image element.

A presentational tile that displays an image file — PNG / JPG / SVG / GIF /
BMP / WEBP — scaled to fill the tile. Animated GIFs play via ``QMovie``; SVGs
render crisply at any size via ``QSvgRenderer``; everything else loads through
``QPixmap``. The image is referenced by **file path** (stored verbatim in the
tile config), mirroring how QGIS references layer data sources: the project
file stays tiny, but the image must remain reachable on disk.

Like the live map it is ``full_bleed`` (no title/description chrome, fills the
tile edge-to-edge) and takes no part in cross-filtering.
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QMovie, QImage, QPainter
from qgis.PyQt.QtWidgets import QLabel
from .base import DashboardElement, _ALIGN

try:
    from qgis.PyQt.QtSvg import QSvgRenderer
except ImportError:          # QtSvg is optional on some builds
    QSvgRenderer = None


class ImageElement(DashboardElement):
    type_name = "image"
    is_filter_source = False
    accepts_filter = False
    full_bleed = True

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self._pixmap = None      # QPixmap source (raster)
        self._svg = None         # QSvgRenderer source (vector)
        self._movie = None       # QMovie source (animated gif)

        self._label = QLabel("")
        self._label.setObjectName("imageTile")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(1, 1)
        self.body.addWidget(self._label, 1)

        self.apply_theme()
        self.refresh()

    # ---- loading ----

    def refresh(self):
        path = (self.config.get("path") or "").strip()
        self._clear_sources()
        if not path:
            self._show_placeholder(
                "No image — edit this tile to choose a file")
            return
        if not os.path.isfile(path):
            self._show_placeholder("Image not found:\n{}".format(path))
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".gif":
            self._load_movie(path)
        elif ext == ".svg" and QSvgRenderer is not None:
            self._load_svg(path)
        else:
            self._load_pixmap(path)
        self._render()

    # ---- appearance ----

    def _restyle(self):
        th = self.effective_theme()
        align = self.style_get("img_align", "center")
        self._label.setAlignment(
            _ALIGN.get(
                align,
                Qt.AlignmentFlag.AlignCenter))
        self._label.setStyleSheet(
            "color:{}; background:transparent;".format(th.text_muted))
        self._render()

    def _clear_sources(self):
        if self._movie is not None:
            self._movie.stop()
        self._pixmap = self._svg = self._movie = None
        self._label.setMovie(None)

    def _load_pixmap(self, path):
        pm = QPixmap(path)
        if pm.isNull():
            self._show_placeholder("Unsupported or corrupt image")
        else:
            self._pixmap = pm

    def _load_svg(self, path):
        renderer = QSvgRenderer(path)
        if renderer.isValid():
            self._svg = renderer
        else:
            self._show_placeholder("Unsupported or corrupt SVG")

    def _load_movie(self, path):
        movie = QMovie(path)
        if movie.isValid():
            self._movie = movie
            self._label.setText("")
            self._label.setMovie(movie)
            movie.start()
        else:
            self._show_placeholder("Unsupported or corrupt GIF")

    def _show_placeholder(self, message):
        self._label.setMovie(None)
        self._label.setText(message)

    # ---- scaling ----

    def _target_size(self):
        return self._label.size()

    def _render(self):
        size = self._target_size()
        if size.width() <= 0 or size.height() <= 0:
            return
        stretch = self.style_get("fit", "contain") == "stretch"
        mode = Qt.AspectRatioMode.IgnoreAspectRatio if stretch else Qt.AspectRatioMode.KeepAspectRatio
        if self._pixmap is not None:
            self._label.setPixmap(self._pixmap.scaled(
                size, mode, Qt.TransformationMode.SmoothTransformation))
        elif self._svg is not None:
            self._label.setPixmap(self._render_svg(size, stretch))
        elif self._movie is not None:
            self._movie.setScaledSize(self._scaled_movie_size(size, stretch))

    def _render_svg(self, size, stretch):
        if stretch:
            target = size
        else:
            intrinsic = self._svg.defaultSize()    # QSize, the SVG's own size
            target = (intrinsic.scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
                      if intrinsic.width() and intrinsic.height() else size)
        img = QImage(max(target.width(), 1), max(target.height(), 1),
                     QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        self._svg.render(painter)
        painter.end()
        return QPixmap.fromImage(img)

    def _scaled_movie_size(self, size, stretch):
        frame = self._movie.currentImage().size()
        if stretch or not frame.width() or not frame.height():
            return size
        return frame.scaled(size, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def teardown(self):
        if self._movie is not None:
            self._movie.stop()
