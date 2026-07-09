# -*- coding: utf-8 -*-
"""Dialog for reporting a tie point coordinate correction to the developer.

Reports are sent over the internet into the plugin's hosted database
(insert-only for plugin users), where the developer reviews them before
updating the master tie point table. Requires an internet connection.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .. import theme
from ..tiepoint_data import correction_payload, parse_coordinate
from ..tiepoint_service import plugin_version, submit_correction


class ReportCorrectionDialog(QDialog):
    """Prefilled with the tie point being reported; the user supplies the
    corrected northing/easting and/or remarks, plus an optional contact."""

    def __init__(self, tiepoint, parent=None):
        super().__init__(parent)
        self.tiepoint = tiepoint
        self.setWindowTitle("Report Tie Point Correction")
        self.setMinimumWidth(460)
        self._build_ui()
        theme.apply(self)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        current_n = self.tiepoint.get("northing")
        current_e = self.tiepoint.get("easting")
        summary = QLabel(
            "<b>{}</b><br>{}<br>{}, {}<br>"
            "Current Northing: <b>{}</b> &nbsp;|&nbsp; Current Easting: <b>{}</b>".format(
                self.tiepoint.get("name") or "",
                self.tiepoint.get("description") or "",
                self.tiepoint.get("municipality") or "",
                self.tiepoint.get("province") or "",
                "—" if current_n is None else current_n,
                "—" if current_e is None else current_e,
            )
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(summary)

        form = QFormLayout()
        self.northingInput = QLineEdit()
        self.northingInput.setPlaceholderText("Leave blank if unchanged")
        self.eastingInput = QLineEdit()
        self.eastingInput.setPlaceholderText("Leave blank if unchanged")
        self.remarksInput = QPlainTextEdit()
        self.remarksInput.setPlaceholderText(
            "Source of the correct coordinates (e.g. certified DENR/LMB "
            "records, field observation), or any other detail that helps "
            "verify the correction.")
        self.remarksInput.setFixedHeight(90)
        self.nameInput = QLineEdit()
        self.nameInput.setPlaceholderText(
            "Use your real name - approved corrections credit their "
            "contributor for everyone to see!")
        self.nameInput.setToolTip(
            "Required. A codename works too, but real names get the "
            "bragging rights when your correction is approved.")
        self.contactInput = QLineEdit()
        self.contactInput.setPlaceholderText("Optional - email for follow-up")
        form.addRow("Correct Northing:", self.northingInput)
        form.addRow("Correct Easting:", self.eastingInput)
        form.addRow("Remarks:", self.remarksInput)
        form.addRow("Your Name:", self.nameInput)
        form.addRow("Contact:", self.contactInput)
        layout.addLayout(form)

        note = QLabel("Sending a report requires an internet connection.")
        note.setStyleSheet("color: #666666; font-size: 8pt;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.submitButton = QPushButton("Send Report")
        self.cancelButton = QPushButton("Cancel")
        buttons.addWidget(self.submitButton)
        buttons.addWidget(self.cancelButton)
        layout.addLayout(buttons)

        self.submitButton.clicked.connect(self._on_submit)
        self.cancelButton.clicked.connect(self.reject)

    def _on_submit(self):
        northing, northing_ok = parse_coordinate(self.northingInput.text())
        easting, easting_ok = parse_coordinate(self.eastingInput.text())
        if not northing_ok or not easting_ok:
            QMessageBox.warning(
                self, "Invalid Coordinates",
                "Northing and Easting must be numeric (e.g. 1691760.514).")
            return
        remarks = self.remarksInput.toPlainText()
        if northing is None and easting is None and not remarks.strip():
            QMessageBox.warning(
                self, "Nothing to Report",
                "Enter a corrected Northing/Easting or describe the problem "
                "in Remarks before sending.")
            return
        reporter_name = self.nameInput.text().strip()
        if not reporter_name:
            QMessageBox.warning(
                self, "Name Required",
                "Please enter your name. A codename is fine, but your real "
                "name gets the public credit once the correction is "
                "approved.")
            return

        payload = correction_payload(
            self.tiepoint,
            proposed_northing=northing,
            proposed_easting=easting,
            remarks=remarks,
            reporter_name=reporter_name,
            contact=self.contactInput.text(),
            plugin_version=plugin_version(),
        )
        ok, error = submit_correction(payload)
        if ok:
            QMessageBox.information(
                self, "Report Sent",
                "Thank you! Your correction report was sent to the developer "
                "for review.")
            self.accept()
        else:
            QMessageBox.warning(
                self, "Could Not Send Report",
                "The report could not be sent. Please check your internet "
                "connection and try again.\n\nDetails: {}".format(error))
