# -*- coding: utf-8 -*-
"""The *Publish to public* dialog.

Collects the author + an optional description (the title comes from the QGIS
project), runs the large-data guard, then publishes the current dashboard
straight to the gallery's Supabase storage via :mod:`publisher`. Publishing is
**instant** — the success screen shows the live link, no review wait.

No account, token or sign-in is needed: contributors just fill in their name
and click Publish. The author name is remembered locally for convenience.
"""

from qgis.PyQt.QtCore import Qt, QSettings, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QDialogButtonBox,
    QMessageBox, QProgressDialog, QApplication,
)

from .submit_client import PublishError, GALLERY_URL
from .publisher import publish_dashboard, oversize_referenced_layers

SCOPE = "qgis_dashboards/publish"


class PublishDialog(QDialog):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setWindowTitle("Publish to public")
        self.setMinimumWidth(460)

        settings = QSettings()
        author = settings.value(SCOPE + "/author", "", type=str)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        intro = QLabel(
            "Share this dashboard in the public gallery. The plugin exports the "
            "interactive HTML, renders a thumbnail and publishes both — your "
            "dashboard goes live in the gallery immediately.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._author_edit = QLineEdit(author)
        self._author_edit.setPlaceholderText("Your name (shown on the card)")
        form.addRow("Author", self._author_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Optional one-line summary")
        form.addRow("Description", self._desc_edit)
        root.addLayout(form)

        hint = QLabel(
            "No account or sign-in needed. The title comes from your QGIS "
            "project name; dashboards up to 50 MB are accepted.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#55606d; font-size:11px;")
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._publish_btn = buttons.addButton(
            "Publish", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        self._publish_btn.clicked.connect(self._publish)
        root.addWidget(buttons)

    # ---- actions --------------------------------------------------------

    def _publish(self):
        author = self._author_edit.text().strip()
        description = self._desc_edit.text().strip() or None

        skip_layers = self._resolve_large_data()
        if skip_layers is False:        # user cancelled at the guard
            return

        # remember the author name for next time
        QSettings().setValue(SCOPE + "/author", author)

        progress = QProgressDialog("Submitting…", None, 0, 100, self)
        progress.setWindowTitle("Publish to public")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setCancelButton(None)
        progress.setValue(0)

        def on_progress(step, frac):
            progress.setLabelText(step)
            progress.setValue(int(frac * 100))
            QApplication.processEvents()

        try:
            result = publish_dashboard(
                self._window, author, description=description,
                skip_layers=skip_layers, progress=on_progress)
        except PublishError as exc:
            progress.close()
            QMessageBox.critical(self, "Submission failed", str(exc))
            return
        except Exception as exc:        # never half-report a silent failure
            progress.close()
            QMessageBox.critical(
                self, "Submission failed",
                "Something went wrong while submitting:\n{}".format(exc))
            return
        finally:
            progress.close()

        self._show_success(result)
        self.accept()

    def _resolve_large_data(self):
        """Return a set of layer ids to skip, an empty set, or ``False`` to cancel."""
        big = oversize_referenced_layers(self._window)
        if not big:
            return set()
        lines = ["These bound layers are large to embed in a single HTML file:\n"]
        for _lid, name, count, est in big:
            lines.append("  • {}: {:,} features (~{:.0f} MB)".format(
                name, count, est / (1024.0 * 1024.0)))
        lines.append("\nPublishing them may make the dashboard slow to open.")
        box = QMessageBox(self)
        box.setWindowTitle("Large data")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("\n".join(lines))
        box.addButton("Publish anyway", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton(
            "Skip these layers",
            QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel:
            return False
        if clicked is skip:
            return {lid for lid, _n, _c, _e in big}
        return set()

    def _show_success(self, result):
        view_url = result.get("view_url") or GALLERY_URL
        box = QMessageBox(self)
        box.setWindowTitle("Published")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "Your dashboard is live!\n\n{}\n\nAnyone can open it there — "
            "cross-filtering, charts and the map all work in the "
            "browser.".format(view_url))
        open_btn = box.addButton(
            "Open dashboard", QMessageBox.ButtonRole.AcceptRole)
        gallery_btn = box.addButton(
            "Open gallery", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_btn:
            QDesktopServices.openUrl(QUrl(view_url))
        elif clicked is gallery_btn:
            QDesktopServices.openUrl(QUrl(GALLERY_URL))
