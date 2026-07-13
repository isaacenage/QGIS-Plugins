# -*- coding: utf-8 -*-
"""Static image exports — the dashboard canvas to PNG and PDF.

Unlike the interactive HTML export (which reproduces live cross-filtering in a
browser), these write a *snapshot* of the dashboard as it is currently laid
out, mirroring the Summarizer plugin's approach: grab the canvas into a
high-resolution pixmap (``PageView.export_pixmap`` — the canvas *plus* its
docked header banner) and either save it straight to PNG or lay it onto an A4
page via :class:`QPdfWriter`.

When the dashboard has more than one (non-empty) page the user is first asked
— via :class:`ExportScopeDialog` — whether to export **all pages** or **one
named page**. PNG writes one file per page (into a chosen folder) when
exporting several; PDF writes one A4 page per dashboard page into a single
document.

These functions own the file-picker and the success/error messaging; the
window just delegates to them from the Settings hub.
"""

import os
import re

from qgis.PyQt.QtCore import QRectF
from qgis.PyQt.QtGui import QPdfWriter, QPageSize, QPageLayout, QPainter
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QComboBox,
    QDialogButtonBox, QFileDialog, QMessageBox,
)

EXPORT_SCALE = 2.0   # device-pixel multiplier for crisp output


# ---- helpers ----------------------------------------------------------------

def _default_basename(window):
    """A sensible default file stem — the project title/name, else 'dashboard'."""
    name = ""
    try:
        from qgis.core import QgsProject
        project = QgsProject.instance()
        name = project.title() or ""
        if not name and project.fileName():
            name = os.path.splitext(os.path.basename(project.fileName()))[0]
    except Exception:
        name = ""
    return name or "dashboard"


def _start_path(window, stem, ext):
    return os.path.join(os.path.expanduser("~"), "{}.{}".format(stem, ext))


def _ensure_ext(path, ext):
    return path if path.lower().endswith("." + ext) else path + "." + ext


def _safe_filename(name, fallback):
    """Sanitize a page title into a filesystem-safe stem."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_",
                  (name or "").strip()).strip(". ")
    return name or fallback


def _non_empty_pages(window):
    return [p for p in window.pages() if p.canvas.tiles()]


# ---- scope chooser ----------------------------------------------------------

class ExportScopeDialog(QDialog):
    """Ask whether to export all pages or a single (named) page.

    *pages* is the list of exportable (non-empty) page objects; *current* is
    pre-selected in the single-page combo when given.
    """

    def __init__(self, pages, fmt_label, parent=None, current=None):
        super().__init__(parent)
        self.setWindowTitle("Export to {}".format(fmt_label))
        self.setMinimumWidth(360)
        self._pages = list(pages)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(10)

        root.addWidget(QLabel("Which pages do you want to export?"))

        self._all_radio = QRadioButton(
            "All pages ({})".format(len(self._pages)))
        self._all_radio.setChecked(True)
        root.addWidget(self._all_radio)

        row = QHBoxLayout()
        self._one_radio = QRadioButton("A single page:")
        row.addWidget(self._one_radio)
        self._combo = QComboBox()
        for i, page in enumerate(self._pages):
            self._combo.addItem(page.title or "Page {}".format(i + 1), i)
        self._combo.setEnabled(False)
        row.addWidget(self._combo, 1)
        root.addLayout(row)

        if current is not None and current in self._pages:
            self._combo.setCurrentIndex(self._pages.index(current))

        self._one_radio.toggled.connect(self._combo.setEnabled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def result_pages(self):
        """The chosen page list: every exportable page, or just the one picked."""
        if self._one_radio.isChecked():
            idx = self._combo.currentData()
            return [self._pages[idx]]
        return list(self._pages)


def _choose_pages(window, fmt_label, parent):
    """Resolve which pages to export, prompting only when it's ambiguous.

    Returns a list of page objects, or ``None`` if there's nothing to export
    or the user cancelled.
    """
    pages = _non_empty_pages(window)
    if not pages:
        QMessageBox.information(
            parent, "Export to {}".format(fmt_label),
            "There is nothing to export.")
        return None
    if len(pages) == 1:
        return pages   # no choice to make
    dlg = ExportScopeDialog(pages, fmt_label, parent,
                            current=window.current_page())
    if not dlg.exec():
        return None
    return dlg.result_pages()


# ---- PNG --------------------------------------------------------------------

def export_png(window, parent=None):
    """Save the dashboard to PNG — one file, or one-per-page into a folder."""
    pages = _choose_pages(window, "PNG", parent)
    if not pages:
        return

    if len(pages) == 1:
        page = pages[0]
        stem = _safe_filename(page.title, "dashboard")
        path, _ = QFileDialog.getSaveFileName(
            parent, "Export dashboard to PNG",
            _start_path(window, stem, "png"), "PNG image (*.png)")
        if not path:
            return
        path = _ensure_ext(path, "png")
        pixmap = page.view.export_pixmap(scale=EXPORT_SCALE)
        if pixmap.isNull() or not pixmap.save(path, "PNG"):
            QMessageBox.critical(
                parent, "Export to PNG", "Could not write the PNG file.")
            return
        QMessageBox.information(parent, "Export to PNG", "Saved:\n" + path)
        return

    # multiple pages -> one PNG each, into a chosen folder
    directory = QFileDialog.getExistingDirectory(
        parent, "Choose a folder for the page PNGs", os.path.expanduser("~"),
        QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
    if not directory:
        return

    saved, used = [], set()
    for i, page in enumerate(pages):
        stem = _safe_filename(page.title, "page_{}".format(i + 1))
        candidate, n = stem, 2
        while candidate in used:
            candidate = "{}_{}".format(stem, n)
            n += 1
        used.add(candidate)
        path = os.path.join(directory, candidate + ".png")
        pixmap = page.view.export_pixmap(scale=EXPORT_SCALE)
        if pixmap.isNull() or not pixmap.save(path, "PNG"):
            QMessageBox.critical(
                parent, "Export to PNG",
                "Could not write:\n" + path)
            return
        saved.append(path)

    QMessageBox.information(
        parent, "Export to PNG",
        "Saved {} file(s):\n".format(len(saved)) + "\n".join(saved))


# ---- PDF --------------------------------------------------------------------

def _write_pdf(pages, path):
    """Render *pages* to *path* as a multi-page PDF (one A4 page each)."""
    pixmaps = [p.view.export_pixmap(scale=EXPORT_SCALE) for p in pages]
    pixmaps = [pm for pm in pixmaps if not pm.isNull()]
    if not pixmaps:
        return False

    first = pixmaps[0]
    landscape = first.width() >= first.height()

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait)
    writer.setResolution(300)

    painter = QPainter(writer)
    try:
        for index, pixmap in enumerate(pixmaps):
            if index > 0:
                writer.newPage()
            page_w, page_h = writer.width(), writer.height()
            margin = int(min(page_w, page_h) * 0.04)
            avail_w = max(page_w - 2 * margin, 1)
            avail_h = max(page_h - 2 * margin, 1)
            pw = max(pixmap.width(), 1)
            ph = max(pixmap.height(), 1)
            fit = min(avail_w / float(pw), avail_h / float(ph))
            target_w, target_h = pw * fit, ph * fit
            tx = margin + (avail_w - target_w) / 2.0
            ty = margin + (avail_h - target_h) / 2.0
            painter.drawPixmap(
                QRectF(tx, ty, target_w, target_h), pixmap,
                QRectF(pixmap.rect()))
    finally:
        painter.end()
    return True


def export_pdf(window, parent=None):
    """Save the dashboard to a PDF — all pages, or a single named page."""
    pages = _choose_pages(window, "PDF", parent)
    if not pages:
        return

    if len(pages) == 1:
        stem = _safe_filename(pages[0].title, "dashboard")
    else:
        stem = _default_basename(window)

    path, _ = QFileDialog.getSaveFileName(
        parent, "Export dashboard to PDF",
        _start_path(window, stem, "pdf"), "PDF document (*.pdf)")
    if not path:
        return
    path = _ensure_ext(path, "pdf")

    if not _write_pdf(pages, path):
        QMessageBox.critical(
            parent,
            "Export to PDF",
            "Could not render the pages.")
        return
    QMessageBox.information(parent, "Export to PDF", "Saved:\n" + path)
