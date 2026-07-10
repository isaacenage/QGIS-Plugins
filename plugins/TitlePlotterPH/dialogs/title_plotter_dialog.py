from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
                                 QWidget, QSizePolicy, QMessageBox, QLabel,
                                 QFrame, QTabWidget, QScrollArea, QApplication,
                                 QFileDialog)
from qgis.PyQt.QtGui import (QPolygonF, QPen, QColor, QPainter, QIntValidator,
                             QRegularExpressionValidator,
                             QFont, QPixmap, QCursor, QPdfWriter, QPageSize, QPageLayout, QFontMetrics, QBrush,
                             QImage)
from qgis.PyQt.QtCore import (Qt, QPointF, pyqtSignal, QMetaType,
                              QRegularExpression, QVariant,
                              QTimer, QPoint, QRectF, QMarginsF, QDate, QUrl)
from qgis.PyQt.QtGui import QDesktopServices
from .. import theme, icons
import os
import math
import json
from qgis.core import (
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsVectorLayer,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsField,
    QgsRectangle,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsLineSymbol,
    QgsTextFormat,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsAnnotationLayer,
    QgsAnnotationPointTextItem
)
from qgis.gui import QgsMapCanvas, QgsProjectionSelectionDialog

# Attempt to import TiePointSelectorDialog, handle potential ImportError later if the file is missing
try:
    from .tie_point_selector_dialog import TiePointSelectorDialog
except ImportError:
    TiePointSelectorDialog = None
    print("Warning: tie_point_selector_dialog.py not found. Tie point selection functionality will be disabled.")

# Make sure shapely is installed in your QGIS environment
# You might need to install it using QGIS's Python terminal or OSGeo4W shell:
# pip install shapely
try:
    from shapely.geometry import Polygon
except ImportError:
    Polygon = None
    print("Warning: shapely library not found. WKT generation functionality will be disabled.")

# Import LLM OCR dialog
try:
    from .llm_ocr_dialog import LLMOCRDialog
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'forms', 'title_plotter_dialog_base.ui'))


# Grouped Input Style (for inputs inside grouped frame)
GROUPED_INPUT_STYLE = """
QLineEdit {
    background-color: transparent;
    border: none;
    border-radius: 0px;
    padding: 4px 6px;
    color: #252b33;
    font-size: 8pt;
    font-weight: bold;
}
QLineEdit:focus {
    background-color: rgba(20, 87, 91, 0.1);
}
"""

# Error Input Style (for standalone inputs)
ERROR_INPUT_STYLE = """
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #d97d85;
    border-radius: 6px;
    padding: 4px 6px;
    color: #9b4a52;
    font-size: 8pt;
    font-weight: bold;
}
"""

# Error Input Style (for grouped inputs)
GROUPED_ERROR_INPUT_STYLE = """
QLineEdit {
    background-color: rgba(217, 125, 133, 0.1);
    border: none;
    border-radius: 0px;
    padding: 4px 6px;
    color: #9b4a52;
    font-size: 8pt;
    font-weight: bold;
}
"""

# Drag Handle Style
DRAG_HANDLE_STYLE = """
QLabel {
    color: #14575b;
    font-size: 12pt;
    font-weight: bold;
    background-color: transparent;
    padding: 0px 2px;
}
QLabel:hover {
    color: #55606d;
}
"""

# Drop Indicator Style
DROP_INDICATOR_STYLE = """
QFrame {
    background-color: #14575b;
    border: none;
    border-radius: 2px;
}
"""


def bearing_to_azimuth(direction_ns, degrees, minutes, direction_ew):
    """Convert bearing to azimuth in degrees using Excel's method."""
    angle = int(degrees) + int(minutes) / 60
    if direction_ns == "N" and direction_ew == "E":
        return angle
    elif direction_ns == "S" and direction_ew == "E":
        return 180 - angle
    elif direction_ns == "S" and direction_ew == "W":
        return 180 + angle
    elif direction_ns == "N" and direction_ew == "W":
        return 360 - angle
    else:
        raise ValueError("Invalid bearing direction combination.")


def calculate_deltas(ns, deg, minute, ew, distance):
    """Calculate latitude and departure deltas for a single bearing line with correct signs."""
    angle_degrees = deg + (minute / 60)
    angle_radians = math.radians(angle_degrees)

    delta_lat = distance * math.cos(angle_radians)
    delta_dep = distance * math.sin(angle_radians)

    # Apply sign based on direction
    if ns.upper() == 'S':
        delta_lat *= -1
    if ew.upper() == 'W':
        delta_dep *= -1

    return round(delta_lat, 3), round(delta_dep, 3)  # Round to 3 decimal places


def generate_coordinates(tie_easting, tie_northing, bearing_rows):
    """Generate coordinates using Excel's cumulative delta method."""
    coords = []

    current_e = tie_easting
    current_n = tie_northing

    for i, row in enumerate(bearing_rows):
        try:
            ns = row.directionInput.text().strip().upper()
            deg = int(row.degreesInput.text().strip())
            min_ = int(row.minutesInput.text().strip())
            ew = row.quadrantInput.text().strip().upper()
            dist = float(row.distanceInput.text().strip().replace(",", "."))

            # Validate degrees and minutes
            if deg < 0 or deg > 90:
                raise ValueError(f"Degrees must be between 0 and 90 (got {deg})")
            if min_ < 0 or min_ > 59:
                raise ValueError(f"Minutes must be between 0 and 59 (got {min_})")

        except Exception as e:
            raise ValueError(f"Bearing row {i + 1} has invalid input: {e}")

        # Use the new calculate_deltas function
        delta_lat, delta_dep = calculate_deltas(ns, deg, min_, ew, dist)

        current_n += delta_lat
        current_e += delta_dep

        coords.append((current_e, current_n))

    return coords


def calculate_misclosure(tie_easting, tie_northing, final_easting, final_northing):
    """Calculate the misclosure (distance between starting and ending points).

    In a perfectly closed traverse, the misclosure would be 0.
    This is the linear error of closure.
    """
    delta_e = final_easting - tie_easting
    delta_n = final_northing - tie_northing
    return math.sqrt(delta_e**2 + delta_n**2)


def calculate_polygon_area(coords):
    """Calculate the area of a polygon using the Shoelace formula.

    Args:
        coords: List of (easting, northing) tuples forming a closed polygon

    Returns:
        Area in square meters (absolute value)
    """
    if len(coords) < 3:
        return 0.0

    # Use Shapely if available for more robust calculation
    if Polygon is not None:
        try:
            polygon = Polygon(coords)
            return abs(polygon.area)
        except Exception:
            pass

    # Fallback to Shoelace formula
    n = len(coords)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    return abs(area) / 2.0


class DropIndicatorWidget(QFrame):
    """Visual indicator for drop position during drag-and-drop."""

    def __init__(self, parent=None):
        super(DropIndicatorWidget, self).__init__(parent)
        self.setStyleSheet(DROP_INDICATOR_STYLE)
        self.setFixedHeight(4)
        self.hide()


class DraggableLineLabel(QLabel):
    """Interactive line label that supports click selection and drag-and-drop."""

    clicked = pyqtSignal()  # Emitted when label is clicked
    dragStarted = pyqtSignal(QPoint)  # Emitted when drag begins

    def __init__(self, parent=None):
        super(DraggableLineLabel, self).__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.clicked.emit()
        super(DraggableLineLabel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        # Drag started
        self.dragStarted.emit(event.pos())
        self.drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super(DraggableLineLabel, self).mouseReleaseEvent(event)


class BearingRowWidget(QWidget):
    """Widget for a single bearing input row with delta calculations."""

    def __init__(self, parent=None, is_first_row=False, dialog=None):
        super(BearingRowWidget, self).__init__(parent)
        self.is_first_row = is_first_row
        self.dialog = dialog  # Store reference to dialog for arrow button callbacks
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Add Line Label with modern styling
        self.lineLabel = QLabel("")
        self.lineLabel.setFixedWidth(50)
        self.lineLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
                padding: 3px;
            }
        """)
        layout.addWidget(self.lineLabel)

        # Add up/down arrow buttons for reordering
        arrow_container = QWidget()
        arrow_container.setStyleSheet("background-color: transparent;")
        arrow_layout = QVBoxLayout(arrow_container)
        arrow_layout.setContentsMargins(0, 0, 0, 0)
        arrow_layout.setSpacing(1)

        self.up_btn = QPushButton("▲")
        self.down_btn = QPushButton("▼")

        arrow_btn_style = """
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 3px;
                color: #ffffff;
                font-size: 7pt;
                font-weight: bold;
                min-width: 18px;
                min-height: 10px;
                max-width: 18px;
                max-height: 10px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
            QPushButton:disabled {
                background-color: #e2e6ec;
                color: #55606d;
            }
        """

        self.up_btn.setStyleSheet(arrow_btn_style)
        self.down_btn.setStyleSheet(arrow_btn_style)
        self.up_btn.setFixedSize(18, 10)
        self.down_btn.setFixedSize(18, 10)

        arrow_layout.addWidget(self.up_btn)
        arrow_layout.addWidget(self.down_btn)
        layout.addWidget(arrow_container)

        # Connect arrow button signals
        self.up_btn.clicked.connect(self.on_move_up)
        self.down_btn.clicked.connect(self.on_move_down)

        # Create input fields
        self.directionInput = QLineEdit()
        self.degreesInput = QLineEdit()
        self.minutesInput = QLineEdit()
        self.quadrantInput = QLineEdit()
        self.distanceInput = QLineEdit()

        # Set properties
        self.directionInput.setMaxLength(1)
        self.degreesInput.setMaxLength(3)
        self.minutesInput.setMaxLength(2)
        self.quadrantInput.setMaxLength(1)

        # Set fixed widths
        self.directionInput.setFixedWidth(40)
        self.degreesInput.setFixedWidth(50)
        self.minutesInput.setFixedWidth(50)
        self.quadrantInput.setFixedWidth(40)
        self.distanceInput.setFixedWidth(90)

        # Set placeholders
        self.directionInput.setPlaceholderText("N/S")
        self.degreesInput.setPlaceholderText("Deg")
        self.minutesInput.setPlaceholderText("Min")
        self.quadrantInput.setPlaceholderText("E/W")
        self.distanceInput.setPlaceholderText("Distance")

        # Center align text in direction and quadrant inputs
        self.directionInput.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.degreesInput.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minutesInput.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quadrantInput.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add Validators
        self.directionInput.setValidator(QRegularExpressionValidator(QRegularExpression("^[NSns]$")))
        self.degreesInput.setValidator(QIntValidator(0, 90, self))
        self.minutesInput.setValidator(QIntValidator(0, 59, self))
        self.quadrantInput.setValidator(QRegularExpressionValidator(QRegularExpression("^[EWew]$")))

        # Create delta labels with modern styling
        self.deltaLatLabel = QLabel("ΔLat: 0.000")
        self.deltaDepLabel = QLabel("ΔDep: 0.000")
        self.deltaLatLabel.setFixedWidth(90)
        self.deltaDepLabel.setFixedWidth(90)

        delta_label_style = """
            QLabel {
                color: #55606d;
                font-size: 7pt;
                font-family: 'Consolas', 'Monaco', monospace;
                background-color: transparent;
                padding: 2px 4px;
            }
        """
        self.deltaLatLabel.setStyleSheet(delta_label_style)
        self.deltaDepLabel.setStyleSheet(delta_label_style)

        # Create modern styled buttons (smaller to match input height)
        self.add_btn = QPushButton("+")
        self.remove_btn = QPushButton("−")  # Using proper minus sign

        # Modern button styling - smaller size to match input boxes
        add_btn_style = """
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 4px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
                min-width: 22px;
                min-height: 22px;
                max-width: 22px;
                max-height: 22px;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """

        remove_btn_style = """
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 4px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
                min-width: 22px;
                min-height: 22px;
                max-width: 22px;
                max-height: 22px;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
            QPushButton:disabled {
                background-color: #e2e6ec;
                color: #55606d;
            }
        """

        self.add_btn.setStyleSheet(add_btn_style)
        self.remove_btn.setStyleSheet(remove_btn_style)
        self.add_btn.setFixedSize(22, 22)
        self.remove_btn.setFixedSize(22, 22)

        # Create a grouped input container with vertical dividers
        input_group = QFrame()
        input_group.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 8px;
            }
        """)
        input_group_layout = QHBoxLayout(input_group)
        input_group_layout.setContentsMargins(0, 0, 0, 0)
        input_group_layout.setSpacing(0)

        # Apply grouped style to all inputs
        for input_field in [self.directionInput, self.degreesInput, self.minutesInput,
                            self.quadrantInput, self.distanceInput]:
            input_field.setStyleSheet(GROUPED_INPUT_STYLE)
            input_field.setFixedHeight(22)

        # Create vertical dividers
        def create_divider():
            divider = QFrame()
            divider.setFixedWidth(1)
            divider.setStyleSheet("background-color: #e2e6ec;")
            return divider

        # Add inputs with dividers to the group
        input_group_layout.addWidget(self.directionInput)
        input_group_layout.addWidget(create_divider())
        input_group_layout.addWidget(self.degreesInput)
        input_group_layout.addWidget(create_divider())
        input_group_layout.addWidget(self.minutesInput)
        input_group_layout.addWidget(create_divider())
        input_group_layout.addWidget(self.quadrantInput)
        input_group_layout.addWidget(create_divider())
        input_group_layout.addWidget(self.distanceInput)

        # Add widgets to main layout
        layout.addWidget(input_group)
        layout.addWidget(self.add_btn)
        layout.addWidget(self.remove_btn)

        # Delta labels are hidden but still functional for calculations
        # They are not added to the layout to save UI space
        self.deltaLatLabel.setVisible(False)
        self.deltaDepLabel.setVisible(False)

        layout.addStretch()

        # Connect signals
        self.distanceInput.textChanged.connect(self.update_deltas)
        self.directionInput.textChanged.connect(self.update_deltas)  # Also update deltas on direction change
        self.degreesInput.textChanged.connect(self.update_deltas)  # Also update deltas on degrees change
        self.minutesInput.textChanged.connect(self.update_deltas)  # Also update deltas on minutes change
        self.quadrantInput.textChanged.connect(self.update_deltas)  # Also update deltas on quadrant change

        # Add validation signals
        self.degreesInput.textChanged.connect(self.validate_degrees)
        self.minutesInput.textChanged.connect(self.validate_minutes)
        self.directionInput.textChanged.connect(self.auto_capitalize_direction)
        self.quadrantInput.textChanged.connect(self.auto_capitalize_quadrant)

        # Connect add button using the stored dialog reference
        if self.dialog is not None:
            self.add_btn.clicked.connect(lambda: self.dialog.add_bearing_row(self))

        # Only connect remove button if not first row
        if not self.is_first_row:
            # Use the stored dialog reference
            if self.dialog is not None:
                self.remove_btn.clicked.connect(lambda _, row=self: self.dialog.remove_bearing_row(row))
        else:
            self.remove_btn.setEnabled(False)

        # Connect text changed signals to trigger WKT generation
        if self.dialog is not None:
            for input_field in [self.directionInput, self.degreesInput, self.minutesInput,
                                self.quadrantInput, self.distanceInput]:
                input_field.textChanged.connect(self.dialog.generate_wkt)

    def validate_degrees(self):
        """Validate degrees input and update UI accordingly."""
        try:
            value = int(self.degreesInput.text())
            if value > 90:
                self.degreesInput.setStyleSheet(GROUPED_ERROR_INPUT_STYLE)
                self.add_btn.setEnabled(False)
            else:
                self.degreesInput.setStyleSheet(GROUPED_INPUT_STYLE)
                self.add_btn.setEnabled(True)
        except ValueError:
            self.degreesInput.setStyleSheet(GROUPED_INPUT_STYLE)
            self.add_btn.setEnabled(True)

    def validate_minutes(self):
        """Validate minutes input and update UI accordingly."""
        try:
            value = int(self.minutesInput.text())
            if value > 59:
                self.minutesInput.setStyleSheet(GROUPED_ERROR_INPUT_STYLE)
                self.add_btn.setEnabled(False)
            else:
                self.minutesInput.setStyleSheet(GROUPED_INPUT_STYLE)
                self.add_btn.setEnabled(True)
        except ValueError:
            self.minutesInput.setStyleSheet(GROUPED_INPUT_STYLE)
            self.add_btn.setEnabled(True)

    def auto_capitalize_direction(self):
        """Auto-capitalize N/S input."""
        text = self.directionInput.text().upper()
        if text != self.directionInput.text():
            self.directionInput.setText(text)

    def auto_capitalize_quadrant(self):
        """Auto-capitalize E/W input."""
        text = self.quadrantInput.text().upper()
        if text != self.quadrantInput.text():
            self.quadrantInput.setText(text)

    def reset_values(self):
        """Reset all input values to empty and clear styles."""
        self.directionInput.setText("")
        self.degreesInput.setText("")
        self.minutesInput.setText("")
        self.quadrantInput.setText("")
        self.distanceInput.setText("")
        # Reset to grouped input styling
        for input_field in [self.directionInput, self.degreesInput, self.minutesInput,
                            self.quadrantInput, self.distanceInput]:
            input_field.setStyleSheet(GROUPED_INPUT_STYLE)
        self.deltaLatLabel.setText("ΔLat: 0.000")
        self.deltaDepLabel.setText("ΔDep: 0.000")
        self.add_btn.setEnabled(True)

    def update_deltas(self):
        """Update delta values when all fields are filled."""
        try:
            # Check if all fields have values
            if not all([
                self.directionInput.text().strip(),
                self.degreesInput.text().strip(),
                self.minutesInput.text().strip(),
                self.quadrantInput.text().strip(),
                self.distanceInput.text().strip()
            ]):
                return

            # Get values
            ns = self.directionInput.text().strip().upper()
            deg = int(self.degreesInput.text().strip())
            min_ = int(self.minutesInput.text().strip())
            ew = self.quadrantInput.text().strip().upper()
            dist = float(self.distanceInput.text().strip().replace(",", "."))

            # Additional validation for degrees and minutes
            if deg < 0 or deg > 90:
                self.degreesInput.setText("0")  # Reset to 0 if out of range
                deg = 0
            if min_ < 0 or min_ > 59:
                self.minutesInput.setText("0")  # Reset to 0 if out of range
                min_ = 0

            # Calculate deltas using the updated function
            delta_lat, delta_dep = calculate_deltas(ns, deg, min_, ew, dist)

            # Update labels
            self.deltaLatLabel.setText(f"ΔLat: {delta_lat:.3f}")
            self.deltaDepLabel.setText(f"ΔDep: {delta_dep:.3f}")

        except ValueError:
            # Clear labels if calculation fails
            self.deltaLatLabel.setText("ΔLat: 0.000")
            self.deltaDepLabel.setText("ΔDep: 0.000")

    def on_move_up(self):
        """Handle up arrow button click."""
        if self.dialog is not None:
            self.dialog.move_row_up(self)

    def on_move_down(self):
        """Handle down arrow button click."""
        if self.dialog is not None:
            self.dialog.move_row_down(self)


class TitlePlotterPhilippineLandTitlesDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(TitlePlotterPhilippineLandTitlesDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        # Enable maximize button on the dialog window
        self.setWindowFlags(
            self.windowFlags() |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )

        # Apply the shared Title Plotter theme (neutral chrome + teal accent)
        theme.apply(self)

        # Set minimum size for proper layout (wider for two-column layout)
        self.setMinimumSize(950, 900)

        # Set modern style for the WKT preview label
        self.labelWKT.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                color: #252b33;
                padding: 8px 10px;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 7pt;
                border: 1px solid #e2e6ec;
            }
        """)
        self.labelWKT.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Style the tie point input labels
        self.label.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
            }
        """)
        self.label_2.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
            }
        """)

        # Style the Technical Description label
        self.technicalDescriptionLabel.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 9pt;
                font-weight: bold;
                background-color: transparent;
                padding: 6px 0px;
            }
        """)

        # Style the Select Tie Point button
        self.openTiePointDialogButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.openTiePointDialogButton.setText("Select Tie Point")

        # Style the Plot button with prominent styling
        self.plotButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.plotButton.setText("Plot on Map")

        # Initialize bearing rows list
        self.bearing_rows = []

        # Connect signals
        self.openTiePointDialogButton.clicked.connect(self.open_tiepoint_selector)
        self.plotButton.clicked.connect(self.plot_on_map)

        # --- Rearrange Layout ---
        # Get references to widgets loaded from UI
        horizontalLayout_tiepoints = self.horizontalLayout
        technicalDescriptionLabel = self.technicalDescriptionLabel
        scrollArea_bearings = self.scrollArea
        plotButton = self.plotButton

        # Improve tie point layout spacing
        horizontalLayout_tiepoints.setSpacing(12)

        # Remove widgets from the original layout structure loaded by setupUi
        self.verticalLayout.removeWidget(technicalDescriptionLabel)
        self.verticalLayout.removeWidget(scrollArea_bearings)
        self.verticalLayout.removeWidget(plotButton)
        self.verticalLayout.removeWidget(self.labelWKT)
        self.verticalLayout.removeItem(horizontalLayout_tiepoints)

        # Create the OCR button (if available) with modern styling
        if OCR_AVAILABLE:
            self.ocrButton = QPushButton("Upload TCT Image")
            self.ocrButton.setToolTip("Extract bearing data from TCT images using Gemini AI")
            self.ocrButton.clicked.connect(self.open_ocr_dialog)
        else:
            self.ocrButton = QPushButton("Upload TCT Image")
            self.ocrButton.setEnabled(False)
            self.ocrButton.setToolTip("Gemini OCR dialog module could not be loaded.")

        # Style the OCR button with accent color
        self.ocrButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                color: #ffffff;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
            QPushButton:disabled {
                background-color: #e2e6ec;
                color: #55606d;
            }
        """)

        # Create a styled container frame for the preview canvas section
        preview_container = QFrame()
        preview_container.setFrameShape(QFrame.Shape.StyledPanel)
        preview_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 12px;
            }
        """)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)

        # Header label for the preview section
        preview_header = QLabel("Lot Preview")
        preview_header.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)
        preview_layout.addWidget(preview_header)

        # Initialize QgsMapCanvas for the visual preview with modern styling
        self.previewCanvas = QgsMapCanvas(preview_container)
        self.previewCanvas.setCanvasColor(QColor("#ffffff"))
        self.previewCanvas.enableAntiAliasing(True)
        self.previewCanvas.setWheelFactor(1.2)
        self.previewCanvas.setEnabled(True)
        self.previewCanvas.setMinimumHeight(150)
        self.previewCanvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.previewCanvas.setStyleSheet("""
            QgsMapCanvas {
                border: 1px solid #e2e6ec;
                border-radius: 8px;
            }
        """)
        preview_layout.addWidget(self.previewCanvas, 1)  # stretch factor 1 to expand

        # Create a horizontal layout for the zoom and new buttons (inside the container)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addStretch()

        # Modern styled zoom button
        self.zoomToLayerBtn = QPushButton("Zoom to Fit")
        self.zoomToLayerBtn.setFixedHeight(26)
        self.zoomToLayerBtn.setMinimumWidth(100)
        self.zoomToLayerBtn.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 6px;
                padding: 3px 10px;
                color: #ffffff;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.zoomToLayerBtn.clicked.connect(self.zoom_preview_to_layer)
        button_layout.addWidget(self.zoomToLayerBtn)

        # Modern styled New button
        self.newButton = QPushButton("New Plot")
        self.newButton.setFixedHeight(26)
        self.newButton.setMinimumWidth(70)
        self.newButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 6px;
                padding: 3px 10px;
                color: #ffffff;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.newButton.clicked.connect(self.reset_plotter)
        button_layout.addWidget(self.newButton)

        # Add the button layout to the preview layout (inside the container)
        preview_layout.addLayout(button_layout)

        # --- Create Info Panel for Area and Misclosure ---
        info_panel = QFrame()
        info_panel.setFrameShape(QFrame.Shape.StyledPanel)
        info_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 12px;
                padding: 4px;
            }
        """)
        info_layout = QHBoxLayout(info_panel)
        info_layout.setContentsMargins(20, 12, 20, 12)
        info_layout.setSpacing(20)

        # Area section with icon
        area_container = QWidget()
        area_container.setStyleSheet("background-color: transparent; border: none;")
        area_layout = QHBoxLayout(area_container)
        area_layout.setContentsMargins(0, 0, 0, 0)
        area_layout.setSpacing(10)

        area_icon = QLabel()
        area_icon.setPixmap(icons.icon_pixmap("area", theme.PALETTE["accent"], 24))
        area_icon.setStyleSheet("background-color: transparent;")

        area_text_container = QWidget()
        area_text_container.setStyleSheet("background-color: transparent; border: none;")
        area_text_layout = QVBoxLayout(area_text_container)
        area_text_layout.setContentsMargins(0, 0, 0, 0)
        area_text_layout.setSpacing(2)

        area_title = QLabel("AREA")
        area_title.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 7pt;
                font-weight: bold;
                letter-spacing: 1px;
                background-color: transparent;
                border: none;
            }
        """)
        self.areaValueLabel = QLabel("-- sq.m.")
        self.areaValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        area_text_layout.addWidget(area_title)
        area_text_layout.addWidget(self.areaValueLabel)

        area_layout.addWidget(area_icon)
        area_layout.addWidget(area_text_container)

        # Separator line (between AREA and VARIANCE)
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setStyleSheet("""
            QFrame {
                background-color: #e2e6ec;
                border: none;
                max-width: 1px;
                min-width: 1px;
            }
        """)

        # Variance section with icon
        variance_container = QWidget()
        variance_container.setStyleSheet("background-color: transparent; border: none;")
        variance_layout = QHBoxLayout(variance_container)
        variance_layout.setContentsMargins(0, 0, 0, 0)
        variance_layout.setSpacing(10)

        variance_icon = QLabel()
        variance_icon.setPixmap(icons.icon_pixmap("variance", theme.PALETTE["accent"], 24))
        variance_icon.setStyleSheet("background-color: transparent;")

        variance_text_container = QWidget()
        variance_text_container.setStyleSheet("background-color: transparent; border: none;")
        variance_text_layout = QVBoxLayout(variance_text_container)
        variance_text_layout.setContentsMargins(0, 0, 0, 0)
        variance_text_layout.setSpacing(2)

        variance_title = QLabel("VARIANCE")
        variance_title.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 7pt;
                font-weight: bold;
                letter-spacing: 1px;
                background-color: transparent;
                border: none;
            }
        """)
        self.varianceValueLabel = QLabel("N/A")
        self.varianceValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        variance_text_layout.addWidget(variance_title)
        variance_text_layout.addWidget(self.varianceValueLabel)

        variance_layout.addWidget(variance_icon)
        variance_layout.addWidget(variance_text_container)

        # Separator line (between VARIANCE and MISCLOSURE)
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setStyleSheet("""
            QFrame {
                background-color: #e2e6ec;
                border: none;
                max-width: 1px;
                min-width: 1px;
            }
        """)

        # Misclosure section with icon
        misclosure_container = QWidget()
        misclosure_container.setStyleSheet("background-color: transparent; border: none;")
        misclosure_layout = QHBoxLayout(misclosure_container)
        misclosure_layout.setContentsMargins(0, 0, 0, 0)
        misclosure_layout.setSpacing(10)

        misclosure_icon = QLabel()
        misclosure_icon.setPixmap(icons.icon_pixmap("misclosure", theme.PALETTE["accent"], 24))
        misclosure_icon.setStyleSheet("background-color: transparent;")

        misclosure_text_container = QWidget()
        misclosure_text_container.setStyleSheet("background-color: transparent; border: none;")
        misclosure_text_layout = QVBoxLayout(misclosure_text_container)
        misclosure_text_layout.setContentsMargins(0, 0, 0, 0)
        misclosure_text_layout.setSpacing(2)

        misclosure_title = QLabel("MISCLOSURE")
        misclosure_title.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 7pt;
                font-weight: bold;
                letter-spacing: 1px;
                background-color: transparent;
                border: none;
            }
        """)
        self.misclosureValueLabel = QLabel("-- m")
        self.misclosureValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        misclosure_text_layout.addWidget(misclosure_title)
        misclosure_text_layout.addWidget(self.misclosureValueLabel)

        misclosure_layout.addWidget(misclosure_icon)
        misclosure_layout.addWidget(misclosure_text_container)

        # Add to info panel layout
        info_layout.addWidget(area_container)
        info_layout.addStretch()
        info_layout.addWidget(separator1)
        info_layout.addStretch()
        info_layout.addWidget(variance_container)
        info_layout.addStretch()
        info_layout.addWidget(separator2)
        info_layout.addStretch()
        info_layout.addWidget(misclosure_container)
        # --- End Info Panel ---

        # Set size policy for scroll area responsiveness
        scrollArea_bearings.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Configure main layout spacing
        self.verticalLayout.setSpacing(12)
        self.verticalLayout.setContentsMargins(16, 16, 16, 16)

        # --- Create Two-Column Layout for Technical Description and Lot Preview ---
        # Create a horizontal layout to hold both columns side by side
        main_content_layout = QHBoxLayout()
        main_content_layout.setSpacing(12)

        # Create a styled container frame for the Technical Description section
        tech_desc_container = QFrame()
        tech_desc_container.setFrameShape(QFrame.Shape.StyledPanel)
        tech_desc_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tech_desc_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 12px;
            }
        """)
        tech_desc_layout = QVBoxLayout(tech_desc_container)
        tech_desc_layout.setContentsMargins(12, 12, 12, 12)
        tech_desc_layout.setSpacing(10)

        # Update the Technical Description label style to match Lot Preview header
        technicalDescriptionLabel.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

        # Update scroll area style to remove its own border (container provides the border)
        scrollArea_bearings.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #ffffff;
            }
        """)

        # Add label and scroll area to the container
        tech_desc_layout.addWidget(technicalDescriptionLabel)
        tech_desc_layout.addWidget(scrollArea_bearings, 1)  # stretch factor 1 to expand

        # Add columns to horizontal layout with stretch factors (3:2 ratio for wider left column)
        main_content_layout.addWidget(tech_desc_container, 3)
        main_content_layout.addWidget(preview_container, 2)

        # --- End Two-Column Layout ---

        # --- Create Tab Widget ---
        # Tab styling is inherited from the shared theme (accent underline on the
        # selected tab) so it stays consistent with the rest of the plugin.
        self.tabWidget = QTabWidget()

        # --- Create Plot Tab ---
        plot_tab = QWidget()
        plot_tab_layout = QVBoxLayout(plot_tab)
        plot_tab_layout.setContentsMargins(12, 12, 12, 12)
        plot_tab_layout.setSpacing(12)

        # Add widgets/layouts to the Plot tab layout
        plot_tab_layout.addLayout(horizontalLayout_tiepoints)
        plot_tab_layout.addWidget(self.ocrButton)
        plot_tab_layout.addLayout(main_content_layout, 1)  # stretch factor 1 to expand

        # --- Create Property Information Panel ---
        property_info_panel = QFrame()
        property_info_panel.setFrameShape(QFrame.Shape.StyledPanel)
        property_info_panel.setToolTip("Optional — not required for plotting technical descriptions")
        property_info_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 12px;
                padding: 4px;
            }
        """)
        property_info_layout = QVBoxLayout(property_info_panel)
        property_info_layout.setContentsMargins(16, 12, 16, 12)
        property_info_layout.setSpacing(10)

        # Property Info Header - Make it clickable
        property_info_header_container = QWidget()
        property_info_header_container.setStyleSheet("background-color: transparent; border: none;")
        property_info_header_container.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        property_info_header_layout = QHBoxLayout(property_info_header_container)
        property_info_header_layout.setContentsMargins(0, 0, 0, 0)
        property_info_header_layout.setSpacing(8)

        # Toggle arrow indicator (▼ = collapsed, ▲ = expanded)
        self.property_info_toggle_arrow = QLabel("▼")
        self.property_info_toggle_arrow.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 11pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        self.property_info_toggle_arrow.setFixedWidth(20)

        property_info_header = QLabel("Property Information")
        property_info_header.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 9pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)

        property_info_header_layout.addWidget(self.property_info_toggle_arrow)
        property_info_header_layout.addWidget(property_info_header)
        property_info_header_layout.addStretch()

        # Make the header clickable
        property_info_header_container.mousePressEvent = lambda event: self.toggle_property_info()

        property_info_layout.addWidget(property_info_header_container)

        # Input field style for property info
        property_input_style = """
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 6px;
                padding: 6px 10px;
                color: #252b33;
                font-size: 8pt;
            }
            QLineEdit:focus {
                border: 1px solid #14575b;
            }
            QLineEdit:hover {
                border: 1px solid #14575b;
            }
        """

        property_label_style = """
            QLabel {
                color: #252b33;
                font-size: 8pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """

        # Create a container widget for all property info fields (to be collapsed/expanded)
        self.property_info_content = QWidget()
        self.property_info_content.setStyleSheet("background-color: transparent; border: none;")
        property_info_content_layout = QVBoxLayout(self.property_info_content)
        property_info_content_layout.setContentsMargins(0, 0, 0, 0)
        property_info_content_layout.setSpacing(10)

        # Row 1: Registered Owner (full width)
        owner_row = QHBoxLayout()
        owner_row.setSpacing(10)
        owner_label = QLabel("Registered Owner:")
        owner_label.setStyleSheet(property_label_style)
        owner_label.setFixedWidth(120)
        self.registeredOwnerInput = QLineEdit()
        self.registeredOwnerInput.setPlaceholderText("Enter registered owner name")
        self.registeredOwnerInput.setStyleSheet(property_input_style)
        owner_row.addWidget(owner_label)
        owner_row.addWidget(self.registeredOwnerInput, 1)
        property_info_content_layout.addLayout(owner_row)

        # Row 2: Location - Barangay, Municipality, Province
        location_row = QHBoxLayout()
        location_row.setSpacing(10)

        # Barangay
        barangay_container = QVBoxLayout()
        barangay_container.setSpacing(2)
        barangay_label = QLabel("Barangay:")
        barangay_label.setStyleSheet(property_label_style)
        self.barangayInput = QLineEdit()
        self.barangayInput.setPlaceholderText("Barangay")
        self.barangayInput.setStyleSheet(property_input_style)
        barangay_container.addWidget(barangay_label)
        barangay_container.addWidget(self.barangayInput)
        location_row.addLayout(barangay_container, 1)

        # Municipality
        municipality_container = QVBoxLayout()
        municipality_container.setSpacing(2)
        municipality_label = QLabel("Municipality:")
        municipality_label.setStyleSheet(property_label_style)
        self.municipalityInput = QLineEdit()
        self.municipalityInput.setPlaceholderText("Municipality/City")
        self.municipalityInput.setStyleSheet(property_input_style)
        municipality_container.addWidget(municipality_label)
        municipality_container.addWidget(self.municipalityInput)
        location_row.addLayout(municipality_container, 1)

        # Province
        province_container = QVBoxLayout()
        province_container.setSpacing(2)
        province_label = QLabel("Province:")
        province_label.setStyleSheet(property_label_style)
        self.provinceInput = QLineEdit()
        self.provinceInput.setPlaceholderText("Province")
        self.provinceInput.setStyleSheet(property_input_style)
        province_container.addWidget(province_label)
        province_container.addWidget(self.provinceInput)
        location_row.addLayout(province_container, 1)

        property_info_content_layout.addLayout(location_row)

        # Row 3: Lot Number, Survey Number, Area
        details_row = QHBoxLayout()
        details_row.setSpacing(10)

        # Lot Number
        lot_container = QVBoxLayout()
        lot_container.setSpacing(2)
        lot_label = QLabel("Lot Number:")
        lot_label.setStyleSheet(property_label_style)
        self.lotNumberInput = QLineEdit()
        self.lotNumberInput.setPlaceholderText("e.g., Lot 1234")
        self.lotNumberInput.setStyleSheet(property_input_style)
        lot_container.addWidget(lot_label)
        lot_container.addWidget(self.lotNumberInput)
        details_row.addLayout(lot_container, 1)

        # Survey Number
        survey_container = QVBoxLayout()
        survey_container.setSpacing(2)
        survey_label = QLabel("Survey Number:")
        survey_label.setStyleSheet(property_label_style)
        self.surveyNumberInput = QLineEdit()
        self.surveyNumberInput.setPlaceholderText("e.g., Psd-12345")
        self.surveyNumberInput.setStyleSheet(property_input_style)
        survey_container.addWidget(survey_label)
        survey_container.addWidget(self.surveyNumberInput)
        details_row.addLayout(survey_container, 1)

        # Area of Property
        area_container = QVBoxLayout()
        area_container.setSpacing(2)
        area_label = QLabel("Title Area:")
        area_label.setStyleSheet(property_label_style)
        self.titleAreaInput = QLineEdit()
        self.titleAreaInput.setPlaceholderText("e.g., 500 sq.m.")
        self.titleAreaInput.setStyleSheet(property_input_style)
        area_container.addWidget(area_label)
        area_container.addWidget(self.titleAreaInput)
        details_row.addLayout(area_container, 1)

        property_info_content_layout.addLayout(details_row)

        # Add the content container to the main property info layout
        property_info_layout.addWidget(self.property_info_content)

        # Set default state to collapsed
        self.property_info_content.setVisible(False)
        # --- End Property Information Panel ---

        plot_tab_layout.addWidget(property_info_panel)
        plot_tab_layout.addWidget(info_panel)
        # Hide the WKT label to save UI space (still functional in background)
        self.labelWKT.setVisible(False)
        plot_tab_layout.addWidget(self.labelWKT)

        # Create horizontal layout for Plot on Map and Print Report buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(plotButton)

        # Create Print Report button (disabled by default)
        self.printReportButton = QPushButton("Print Report")
        self.printReportButton.setEnabled(False)
        self.printReportButton.setToolTip("Export a PDF technical report (fill all fields to enable)")
        self.printReportButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
            QPushButton:disabled {
                background-color: #e2e6ec;
                color: #55606d;
            }
        """)
        self.printReportButton.clicked.connect(self.print_report)
        buttons_layout.addWidget(self.printReportButton)

        # Create Export button
        self.exportButton = QPushButton("Export")
        self.exportButton.setToolTip("Export all data to a JSON file for later use")
        self.exportButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.exportButton.clicked.connect(self.export_data)
        buttons_layout.addWidget(self.exportButton)

        # Create Import button
        self.importButton = QPushButton("Import")
        self.importButton.setToolTip("Import data from a previously exported JSON file")
        self.importButton.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                color: #ffffff;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)
        self.importButton.clicked.connect(self.import_data)
        buttons_layout.addWidget(self.importButton)

        buttons_layout.addStretch()

        plot_tab_layout.addLayout(buttons_layout)

        self.tabWidget.addTab(plot_tab, "Plot")

        # --- Create How to Use Tab ---
        how_to_use_tab = self._create_how_to_use_tab()
        self.tabWidget.addTab(how_to_use_tab, "Usage")

        # --- Create About Tab ---
        about_tab = self._create_about_tab()
        self.tabWidget.addTab(about_tab, "About")

        # Add the tab widget to the main vertical layout
        self.verticalLayout.addWidget(self.tabWidget)
        # --- End Tab Widget and Rearrange Layout ---

        # Ensure bearingListLayout exists and is a QVBoxLayout (inside scrollArea_bearings)
        # This is already handled by setupUi, but re-checking doesn't hurt
        self.bearingListLayout = self.scrollAreaWidgetContents.layout()
        if not isinstance(self.bearingListLayout, QVBoxLayout):
            # This case should ideally not happen if UI is correctly set up
            self.bearingListLayout = QVBoxLayout(self.scrollAreaWidgetContents)
            self.bearingListLayout.setAlignment(Qt.AlignmentFlag.AlignTop)  # Ensure alignment
            self.bearingListLayout.setContentsMargins(0, 0, 0, 0)  # Ensure margins
            self.bearingListLayout.setSpacing(2)  # Ensure spacing

        # Set minimum height for the scroll area
        # This is set in UI, but can be enforced here if needed
        # self.scrollArea.setMinimumHeight(300)

        # Set up initial row (this adds to bearingListLayout, which is inside scrollArea)
        self.setup_initial_row()

        # Initialize tie point
        self.tie_point = None

        # Store the last generated WKT
        self.last_wkt = None

        # Initialize preview layers (for the QgsMapCanvas)
        self.preview_layer = None
        self.preview_points_layer = None
        self.preview_annotation_layer = None

        # Connect signals for Print Report button state
        self._connect_print_report_signals()

        # Remove the old WKT output widget and Generate WKT button
        # These were removed in a previous step, keeping this check for safety
        if hasattr(self, 'wktOutput'):
            self.wktOutput.setParent(None)
            self.wktOutput.deleteLater()
        if hasattr(self, 'generateWKTButton'):
            self.generateWKTButton.setParent(None)
            self.generateWKTButton.deleteLater()

    def _create_how_to_use_tab(self):
        """Create the How to Use tab with step-by-step instructions."""
        how_to_use_tab = QWidget()
        how_to_use_layout = QVBoxLayout(how_to_use_tab)
        how_to_use_layout.setContentsMargins(20, 20, 20, 20)
        how_to_use_layout.setSpacing(0)

        # Create a scroll area for the content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #ffffff;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #f6f8fb;
                width: 12px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #14575b;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #114a4e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Content widget inside scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(20)

        # --- Header ---
        header_label = QLabel("How to Use Title Plotter PH")
        header_label.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 16pt;
                font-weight: bold;
                background-color: transparent;
            }
        """)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(header_label)

        # --- Step 1: Tie Points Section ---
        tie_point_section = self._create_about_section(
            "Step 1: Set Your Tie Point",
            "The tie point is the starting reference point for plotting your lot. It connects your technical "
            "description to a real-world location.\n\n"
            "OPTION A - Select from Database:\n"
            "1. Click the \"Select Tie Point\" button\n"
            "2. Use the search box to find your tie point by name or monument number\n"
            "3. Browse through regions, provinces, and municipalities to narrow down results\n"
            "4. Click on a tie point row to select it\n"
            "5. Click \"Select\" to confirm - the coordinates will auto-fill\n\n"
            "OPTION B - Manual Entry:\n"
            "1. If you have verified coordinates from a licensed surveyor, enter them directly\n"
            "2. Type the Northing value in the \"Northing\" field\n"
            "3. Type the Easting value in the \"Easting\" field\n"
            "4. Coordinates should be in the local coordinate system (PRS92 or similar)\n\n"
            "TIP: If your title mentions a specific BLLM (Bureau of Lands Location Monument) or MBM "
            "(Municipal Boundary Monument), search for that reference in the tie point selector."
        )
        content_layout.addWidget(tie_point_section)

        # --- Step 2: Upload TCT Image Section ---
        upload_section = self._create_about_section(
            "Step 2: Upload TCT Image (Optional - AI-Powered)",
            "This feature uses AI (Gemini, OpenAI, or DeepSeek) to automatically extract bearing and distance "
            "data plus property information from images of your Transfer Certificate of Title (TCT).\n\n"
            "HOW TO USE:\n"
            "1. Click the \"Upload TCT Image\" button\n"
            "2. Select your preferred AI provider from the dropdown (Gemini, OpenAI, or DeepSeek)\n"
            "3. Enter your API key (first time only - it will be saved locally)\n"
            "   • Click \"Get API Key\" for instructions on obtaining a free API key\n"
            "4. Upload an image by clicking \"Browse\" or paste from clipboard\n"
            "5. Supported formats: JPG, PNG, GIF, WebP, BMP, TIFF\n"
            "6. Click \"Parse\" and wait for the AI to extract the data\n"
            "7. Review the extracted data:\n"
            "   • Property Information (owner, lot number, survey number, location, area)\n"
            "   • Tie Point information (if visible in the image)\n"
            "   • Technical Description (bearing and distance lines)\n"
            "8. Click \"Done\" to automatically fill in all extracted data\n\n"
            "WHAT GETS AUTO-FILLED:\n"
            "• Property Information fields (Registered Owner, Lot Number, Survey Number, etc.)\n"
            "• Tie Point coordinates (if found in the database)\n"
            "• Technical Description (all bearing and distance lines)\n\n"
            "TIPS FOR BEST RESULTS:\n"
            "• Take a clear, well-lit photo of the entire title page\n"
            "• Ensure all text is legible and not blurry\n"
            "• Include both the property info section and technical description\n"
            "• If results are incorrect, you can manually edit the values after applying\n\n"
            "NOTE: Your API key is stored locally and never shared. Images are sent directly to "
            "the selected AI provider for processing."
        )
        content_layout.addWidget(upload_section)

        # --- Step 2B: Property Information Section ---
        property_info_section = self._create_about_section(
            "Property Information (Optional)",
            "The Property Information section contains metadata about the land title. This data is collapsible "
            "and can be auto-filled using the AI OCR feature.\n\n"
            "FIELDS INCLUDED:\n"
            "• Registered Owner - Full name of the property owner\n"
            "• Location - Barangay, Municipality/City, Province\n"
            "• Lot Number - e.g., \"Lot 1234\"\n"
            "• Survey Number - e.g., \"Psd-04-123456\"\n"
            "• Title Area - Total area in square meters\n\n"
            "WHEN TO FILL THIS:\n"
            "• NOT REQUIRED for plotting lots on the map\n"
            "• REQUIRED for generating PDF reports (\"Print Report\" button)\n"
            "• The PDF report includes all property information in a professional format\n\n"
            "HOW TO FILL:\n"
            "OPTION A - AI Auto-Fill:\n"
            "1. Use the \"Upload TCT Image\" feature\n"
            "2. AI will extract property information from the title image\n"
            "3. Click \"Done\" to apply the extracted data\n\n"
            "OPTION B - Manual Entry:\n"
            "1. Click the \"Property Information\" header to expand the section\n"
            "2. Fill in the fields manually\n"
            "3. All fields are optional but recommended for PDF reports\n\n"
            "NOTE: The \"Print Report\" button will only be enabled when all property information fields "
            "are filled in."
        )
        content_layout.addWidget(property_info_section)

        # --- Step 2C: Import/Export JSON Section ---
        import_export_section = self._create_about_section(
            "Save & Load Progress (Import/Export JSON)",
            "You can save your plotting progress to a JSON file and reload it later. This is useful for:\n"
            "• Saving work-in-progress plots\n"
            "• Sharing plot data with others\n"
            "• Creating backups before making changes\n"
            "• Working on multiple plots across sessions\n\n"
            "EXPORT DATA (Save Progress):\n"
            "1. Enter your tie point, property information, and technical description\n"
            "2. Click the \"Export\" button (📤 icon) at the bottom of the dialog\n"
            "3. Choose a location and filename for the JSON file\n"
            "4. The file will contain all your current data:\n"
            "   • Tie point coordinates\n"
            "   • Property information (owner, lot number, location, etc.)\n"
            "   • All bearing rows (technical description)\n\n"
            "IMPORT DATA (Load Progress):\n"
            "1. Click the \"Import\" button (📥 icon) at the bottom of the dialog\n"
            "2. Select a previously exported JSON file\n"
            "3. If you have existing data, you'll be asked to confirm replacement\n"
            "4. All data from the file will be loaded into the dialog\n"
            "5. Review the data and click \"Plot on Map\" when ready\n\n"
            "FILE FORMAT:\n"
            "• Files are saved in standard JSON format\n"
            "• Default filename: [Lot_Number]_data.json\n"
            "• You can edit the JSON file manually if needed (advanced users)\n\n"
            "TIPS:\n"
            "• Export your data before trying different tie points\n"
            "• Create a library of commonly plotted lots\n"
            "• Share JSON files with colleagues working on the same properties"
        )
        content_layout.addWidget(import_export_section)

        # --- Step 3: Technical Description Section ---
        tech_desc_section = self._create_about_section(
            "Step 3: Enter Technical Description",
            "The Technical Description area is where you input the bearing and distance data that defines "
            "your lot's boundaries.\n\n"
            "UNDERSTANDING THE INPUT FIELDS:\n"
            "Each row represents one boundary line with these components:\n"
            "• N/S: Direction from North or South (type N or S)\n"
            "• Deg: Degrees of the angle (0-90)\n"
            "• Min: Minutes of the angle (0-59)\n"
            "• E/W: Direction to East or West (type E or W)\n"
            "• Distance: Length of the line in meters\n\n"
            "HOW TO ENTER DATA:\n"
            "1. Start with Line 1 (TP - 1), which goes from the Tie Point to Corner 1\n"
            "2. Enter the bearing: e.g., \"N 45° 30' E\" becomes N, 45, 30, E\n"
            "3. Enter the distance in meters\n"
            "4. Click the \"+\" button to add another line\n"
            "5. Continue until all boundary lines are entered\n"
            "6. The last line should return to Corner 1 (closing the polygon)\n\n"
            "READING YOUR TITLE:\n"
            "A typical technical description reads like:\n"
            "\"N. 45° 30' E., 25.50 m. to point 2...\"\n"
            "This translates to: N, 45, 30, E, 25.50\n\n"
            "LINE LABELS EXPLAINED:\n"
            "• TP - 1: From Tie Point to Corner 1\n"
            "• 1 - 2: From Corner 1 to Corner 2\n"
            "• 2 - 3: From Corner 2 to Corner 3\n"
            "• ... and so on until the last line returns to Corner 1\n\n"
            "PREVIEW:\n"
            "As you enter data, the \"Lot Preview\" panel shows a real-time visualization of your polygon. "
            "The Area and Misclosure values update automatically.\n\n"
            "MISCLOSURE:\n"
            "Misclosure indicates how accurately the polygon closes. A value close to 0 means the boundary "
            "lines form a proper closed loop. Higher values may indicate input errors or data from the title."
        )
        content_layout.addWidget(tech_desc_section)

        # --- Step 4: Plot on Map Section ---
        plot_section = self._create_about_section(
            "Step 4: Plot on Map",
            "Once your technical description is complete, you can plot the lot on the QGIS map canvas.\n\n"
            "IMPORTANT - PROJECTION REQUIREMENT:\n"
            "The map canvas MUST NOT be in WGS84 (EPSG:4326) projection. Title Plotter uses local "
            "coordinates, not latitude/longitude.\n\n"
            "HOW TO CHANGE YOUR MAP PROJECTION:\n"
            "1. Look at the bottom-right corner of QGIS for the current EPSG code\n"
            "2. Click on the EPSG code to open the Project Properties\n"
            "3. Search for a local Philippine coordinate system, such as:\n"
            "   • EPSG:3123 - PRS92 / Philippines Zone 3\n"
            "   • EPSG:3124 - PRS92 / Philippines Zone 4\n"
            "   • EPSG:3125 - PRS92 / Philippines Zone 5\n"
            "4. Select the appropriate zone for your location and click OK\n\n"

            "PLOTTING YOUR LOT:\n"
            "1. Ensure you have entered at least 3 bearing lines (for a valid polygon)\n"
            "2. Verify the preview looks correct in the Lot Preview panel\n"
            "3. Click \"Plot on Map\"\n"
            "4. A new layer called \"Title Plot Preview\" will appear on your map\n"
            "5. The map will automatically zoom to your plotted lot\n\n"
            "AFTER PLOTTING:\n"
            "• The plotted layer is a temporary memory layer\n"
            "• To save permanently, right-click the layer and select \"Export\" > \"Save Features As...\"\n"
            "• You can overlay the plot on satellite imagery or cadastral maps for verification\n"
            "• Use the \"New Plot\" button to clear and start a new plot"
        )
        content_layout.addWidget(plot_section)

        # --- Tips Section ---
        tips_section = self._create_about_section(
            "Additional Tips",
            "WORKFLOW RECOMMENDATION:\n"
            "1. First, set up your QGIS project with the correct projection\n"
            "2. Load any reference layers (satellite imagery, cadastral maps)\n"
            "3. Then open Title Plotter and enter your data\n"
            "4. Plot and compare with reference data\n\n"
            "COMMON ISSUES:\n"
            "• Plot appears in wrong location: Check tie point coordinates\n"
            "• Plot appears mirrored/rotated: Verify N/S and E/W directions\n"
            "• Large misclosure value: Double-check all bearing and distance entries\n"
            "• \"Invalid Projection\" error: Change map CRS from EPSG:4326\n\n"
            "ACCURACY NOTES:\n"
            "• Results depend on tie point accuracy from the database\n"
            "• For official boundary verification, consult a licensed geodetic engineer\n"
            "• This tool is for visualization purposes only"
        )
        content_layout.addWidget(tips_section)

        # Add stretch to push content to top
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        how_to_use_layout.addWidget(scroll_area)

        return how_to_use_tab

    def _create_about_tab(self):
        """Create the About tab with plugin information, disclaimers, and security notice."""
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_layout.setContentsMargins(20, 20, 20, 20)
        about_layout.setSpacing(0)

        # Create a scroll area for the about content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #ffffff;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #f6f8fb;
                width: 12px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #14575b;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #114a4e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Content widget inside scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(20)

        # --- Plugin Title and Version ---
        title_label = QLabel("Title Plotter PH")
        title_label.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 18pt;
                font-weight: bold;
                background-color: transparent;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(title_label)

        version_label = QLabel("Version 2.0.0")
        version_label.setStyleSheet("""
            QLabel {
                color: #55606d;
                font-size: 10pt;
                background-color: transparent;
            }
        """)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(version_label)

        # --- Description Section ---
        desc_frame = self._create_about_section(
            "About",
            "Title Plotter helps non-surveyors and professionals plot lots using bearing and distance, "
            "based on tie points. Designed to work with Philippine land titles. Requires no GIS background.\n\n"
            "This plugin simplifies the process of visualizing land parcels from technical descriptions "
            "commonly found in Transfer Certificates of Title (TCT) and other land title documents in the Philippines."
        )
        content_layout.addWidget(desc_frame)

        # --- Developer Section ---
        dev_frame = self._create_about_section(
            "Developer",
            "Author: Isaac Enage\n"
            "Email: isaacenagework@gmail.com\n\n"
            "Homepage: https://isaacenage.xyz/Tools/titleplotterph\n"
            "Repository: https://github.com/isaacenage/TitlePlotterPH\n\n"
            "License: GPL-3.0"
        )
        content_layout.addWidget(dev_frame)

        # --- Disclaimer Section ---
        disclaimer_frame = self._create_about_section(
            "Disclaimer",
            "IMPORTANT: This plugin is designed primarily for plotting Philippine land titles from "
            "technical descriptions. It is intended as a visualization tool and should NOT be used as "
            "the sole basis for legal, surveying, or property boundary decisions.\n\n"
            "KEY LIMITATIONS:\n\n"
            "• Tie Point Accuracy: The accuracy of plotted parcels depends heavily on the accuracy of "
            "monument tie line coordinates. The built-in tie point database is compiled from various sources "
            "and may contain inaccuracies or outdated information.\n\n"
            "• Not a Survey Tool: This plugin does not replace professional land surveying. For official "
            "boundary determinations, always consult a licensed geodetic engineer.\n\n"
            "• Coordinate System: Results are based on local coordinate systems. Discrepancies may occur "
            "when comparing with other coordinate systems or reference frames.\n\n"
            "CORRECTIONS AND CONTRIBUTIONS:\n\n"
            "If you have your own verified tie point coordinates and believe the ones in the database are "
            "incorrect, you may:\n"
            "• Manually input your corrected tie point coordinates using the input fields\n"
            "• Email corrections to isaacenagework@gmail.com for inclusion in future updates\n\n"
            "Your contributions help improve the accuracy of this tool for all users."
        )
        content_layout.addWidget(disclaimer_frame)

        # --- Security Notice Section ---
        security_frame = self._create_about_section(
            "Security & Privacy",
            "API KEY SECURITY:\n\n"
            "Your API keys (for Gemini, OpenAI, or DeepSeek OCR functionality) are stored locally on your "
            "computer using Qt's QSettings framework and are NEVER transmitted to any server other than the "
            "intended API provider.\n\n"
            "HOW API KEYS ARE STORED:\n\n"
            "• API keys are saved in your system's persistent storage using QSettings\n"
            "• Windows: Stored in Windows Registry at HKEY_CURRENT_USER\\Software\\TitlePlotterPH\\GeminiOCR\n"
            "• Linux: Stored in ~/.config/TitlePlotterPH/GeminiOCR.conf\n"
            "• macOS: Stored in ~/Library/Preferences/com.TitlePlotterPH.GeminiOCR.plist\n"
            "• Keys persist even after plugin reinstall for your convenience\n"
            "• Keys are stored in plain text locally (standard for QSettings)\n"
            "• You can manually delete keys from these locations if needed\n\n"
            "API KEY USAGE:\n\n"
            "• No API keys or credentials are sent to the plugin developer or any third party\n"
            "• API keys are used solely for direct communication between your computer and the API provider "
            "(Google Gemini, OpenAI, or DeepSeek for OCR processing)\n"
            "• You maintain full control over your API keys and can remove them at any time\n\n"
            "DATA PRIVACY:\n\n"
            "• All calculations and plotting are performed locally on your computer\n"
            "• No land title data, coordinates, or technical descriptions are transmitted externally\n"
            "• Image processing for OCR is sent directly to the selected AI provider API (if used) and is subject "
            "to their respective privacy policies\n\n"
            "For questions about security or privacy, contact: isaacenagework@gmail.com"
        )
        content_layout.addWidget(security_frame)

        # --- Support Section ---
        support_frame = QFrame()
        support_frame.setStyleSheet("""
            QFrame {
                background-color: #fff8e6;
                border: 1px solid #e6a800;
                border-radius: 10px;
            }
        """)
        support_layout = QVBoxLayout(support_frame)
        support_layout.setContentsMargins(16, 12, 16, 12)
        support_layout.setSpacing(12)

        support_title = QLabel("Support Development")
        support_title.setStyleSheet("""
            QLabel {
                color: #b38600;
                font-size: 11pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        support_layout.addWidget(support_title)

        support_text = QLabel(
            "I am currently developing several QGIS plugins to help the community. "
            "If you find this tool useful and would like to support my work, "
            "even a small contribution would mean a lot and keep me motivated!"
        )
        support_text.setWordWrap(True)
        support_text.setStyleSheet("""
            QLabel {
                color: #8a6900;
                font-size: 9pt;
                background-color: transparent;
                border: none;
            }
        """)
        support_layout.addWidget(support_text)

        # Buy me Coffee button
        donate_btn = QPushButton("Buy me Coffee ☕")
        donate_btn.setStyleSheet("""
            QPushButton {
                background-color: #e6a800;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #cc9600;
            }
            QPushButton:pressed {
                background-color: #b38600;
            }
        """)
        donate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        donate_btn.clicked.connect(self.show_donate_dialog)
        support_layout.addWidget(donate_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        support_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout.addWidget(support_frame)

        # Add stretch to push content to top
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        about_layout.addWidget(scroll_area)

        return about_tab

    def _create_about_section(self, title, content):
        """Create a styled section frame for the About tab."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e6ec;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Section title
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 11pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        layout.addWidget(title_label)

        # Section content
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setMinimumWidth(1)  # Allow label to shrink for proper word wrapping
        content_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_label.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 9pt;
                background-color: transparent;
                border: none;
                line-height: 1.4;
            }
        """)
        layout.addWidget(content_label)

        # Set frame size policy to expand horizontally
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        return frame

    def show_donate_dialog(self):
        """Show a dialog with GCash QR code for donations."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Support Development")
        dialog.setFixedSize(420, 580)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title_label = QLabel("Thank You for Your Support!")
        title_label.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 14pt;
                font-weight: bold;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "I am currently in the process of developing several QGIS plugins "
            "to help the GIS community in the Philippines and beyond.\n\n"
            "If you want to contribute to this journey, even 1 Peso would "
            "make me motivated to continue creating free and useful tools!\n\n"
            "Scan the QR code below with your GCash app:"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            QLabel {
                color: #252b33;
                font-size: 10pt;
                line-height: 1.4;
            }
        """)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)

        # QR Code Image
        qr_label = QLabel()
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qr_path = os.path.join(plugin_dir, "resources", "gcashqr.jpeg")

        if os.path.exists(qr_path):
            pixmap = QPixmap(qr_path)
            # Scale the image to fit nicely in the dialog
            scaled_pixmap = pixmap.scaled(
                300, 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            qr_label.setPixmap(scaled_pixmap)
        else:
            qr_label.setText("QR Code not found")
            qr_label.setStyleSheet("color: #cc0000;")

        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr_label)

        # Thank you message
        thanks_label = QLabel("Maraming salamat po!")
        thanks_label.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 11pt;
                font-style: italic;
            }
        """)
        thanks_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thanks_label)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #14575b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 30px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
        """)
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.exec()

    def setup_initial_row(self):
        """Set up the initial bearing row."""
        row = BearingRowWidget(self, is_first_row=True, dialog=self)
        self.bearingListLayout.addWidget(row)
        self.bearing_rows.append(row)
        self.update_line_labels()

    def toggle_property_info(self):
        """Toggle the visibility of the Property Information section."""
        is_visible = self.property_info_content.isVisible()
        self.property_info_content.setVisible(not is_visible)

        # Update arrow indicator
        if is_visible:
            self.property_info_toggle_arrow.setText("▼")  # Collapsed - arrow points down
        else:
            self.property_info_toggle_arrow.setText("▲")  # Expanded - arrow points up

        # Adjust dialog size to fit content
        QTimer.singleShot(0, self.adjustSize)

    def check_print_report_enabled(self):
        """Check if all required fields are filled to enable the Print Report button."""
        # Check if technical description has at least 3 valid bearing rows
        valid_bearing_rows = 0
        for row in self.bearing_rows:
            try:
                ns = row.directionInput.text().strip().upper()
                deg = row.degreesInput.text().strip()
                min_ = row.minutesInput.text().strip()
                ew = row.quadrantInput.text().strip().upper()
                dist = row.distanceInput.text().strip()

                if ns and deg and min_ and ew and dist:
                    valid_bearing_rows += 1
            except Exception:
                pass

        has_tech_desc = valid_bearing_rows >= 3

        # Check if Lot Preview has data (preview_layer exists and is valid)
        has_preview = self.preview_layer is not None and self.preview_layer.isValid()

        # Check Northing and Easting
        has_northing = bool(self.tiePointNorthingInput.text().strip())
        has_easting = bool(self.tiePointEastingInput.text().strip())

        # Check all Property Information fields
        has_owner = bool(self.registeredOwnerInput.text().strip())
        has_barangay = bool(self.barangayInput.text().strip())
        has_municipality = bool(self.municipalityInput.text().strip())
        has_province = bool(self.provinceInput.text().strip())
        has_lot_number = bool(self.lotNumberInput.text().strip())
        has_survey_number = bool(self.surveyNumberInput.text().strip())
        has_title_area = bool(self.titleAreaInput.text().strip())

        # Enable button only if all conditions are met
        all_filled = (
            has_tech_desc and
            has_preview and
            has_northing and
            has_easting and
            has_owner and
            has_barangay and
            has_municipality and
            has_province and
            has_lot_number and
            has_survey_number and
            has_title_area
        )

        self.printReportButton.setEnabled(all_filled)

        # Update tooltip based on state
        if all_filled:
            self.printReportButton.setToolTip("Export a PDF technical report")
        else:
            missing = []
            if not has_tech_desc:
                missing.append("Technical description (minimum 3 lines)")
            if not has_preview:
                missing.append("Valid lot preview")
            if not has_northing:
                missing.append("Northing")
            if not has_easting:
                missing.append("Easting")
            if not has_owner:
                missing.append("Registered Owner")
            if not has_barangay:
                missing.append("Barangay")
            if not has_municipality:
                missing.append("Municipality")
            if not has_province:
                missing.append("Province")
            if not has_lot_number:
                missing.append("Lot Number")
            if not has_survey_number:
                missing.append("Survey Number")
            if not has_title_area:
                missing.append("Title Area")

            self.printReportButton.setToolTip(f"Fill the following to enable: {', '.join(missing)}")

    def _connect_print_report_signals(self):
        """Connect all input fields to update the Print Report button state."""
        # Connect property information fields
        self.registeredOwnerInput.textChanged.connect(self.check_print_report_enabled)
        self.barangayInput.textChanged.connect(self.check_print_report_enabled)
        self.municipalityInput.textChanged.connect(self.check_print_report_enabled)
        self.provinceInput.textChanged.connect(self.check_print_report_enabled)
        self.lotNumberInput.textChanged.connect(self.check_print_report_enabled)
        self.surveyNumberInput.textChanged.connect(self.check_print_report_enabled)
        self.titleAreaInput.textChanged.connect(self.check_print_report_enabled)

        # Connect tie point fields
        self.tiePointNorthingInput.textChanged.connect(self.check_print_report_enabled)
        self.tiePointEastingInput.textChanged.connect(self.check_print_report_enabled)

    def add_bearing_row(self, after_row=None):
        """Add a new bearing input row after the specified row, or at the end if None."""
        row = BearingRowWidget(self, dialog=self)

        if after_row is None:
            # Add to the end (default behavior)
            self.bearingListLayout.addWidget(row)
            self.bearing_rows.append(row)
        else:
            # Insert after the specified row
            try:
                index = self.bearing_rows.index(after_row)
                # Insert into the list
                self.bearing_rows.insert(index + 1, row)
                # Insert into the layout
                self.bearingListLayout.insertWidget(index + 1, row)
            except ValueError:
                # Fallback: add to the end if row not found
                self.bearingListLayout.addWidget(row)
                self.bearing_rows.append(row)

        self.update_line_labels()

        # Trigger WKT regeneration to update the preview
        self.generate_wkt()

    def remove_bearing_row(self, row_widget):
        """Remove a bearing input row."""
        if len(self.bearing_rows) > 1:  # Keep at least one row
            self.bearingListLayout.removeWidget(row_widget)
            row_widget.deleteLater()
            self.bearing_rows.remove(row_widget)
            self.update_line_labels()

            # Trigger WKT regeneration to update the preview
            self.generate_wkt()

    def update_line_labels(self):
        """Update the line labels based on their index."""
        for i, row in enumerate(self.bearing_rows):
            if i == 0:
                row.lineLabel.setText("TP - 1")
            elif i == len(self.bearing_rows) - 1:
                row.lineLabel.setText(f"{i} - 1")
            else:
                row.lineLabel.setText(f"{i} - {i + 1}")
        # Update arrow button states
        self.update_arrow_buttons()

    def update_arrow_buttons(self):
        """Update the enabled state of arrow buttons based on row positions."""
        for i, row in enumerate(self.bearing_rows):
            # Disable both arrows for first row (TP-1) - it should never move
            if i == 0:
                row.up_btn.setEnabled(False)
                row.down_btn.setEnabled(False)
            # Disable up button for second row (can't swap with first row)
            elif i == 1:
                row.up_btn.setEnabled(False)
                row.down_btn.setEnabled(i < len(self.bearing_rows) - 1)
            # For all other rows
            else:
                row.up_btn.setEnabled(True)
                row.down_btn.setEnabled(i < len(self.bearing_rows) - 1)

    def swap_row_values(self, row1, row2):
        """Swap only the input field values between two rows, not the widgets themselves."""
        # Store row1 values
        temp_direction = row1.directionInput.text()
        temp_degrees = row1.degreesInput.text()
        temp_minutes = row1.minutesInput.text()
        temp_quadrant = row1.quadrantInput.text()
        temp_distance = row1.distanceInput.text()

        # Copy row2 values to row1
        row1.directionInput.setText(row2.directionInput.text())
        row1.degreesInput.setText(row2.degreesInput.text())
        row1.minutesInput.setText(row2.minutesInput.text())
        row1.quadrantInput.setText(row2.quadrantInput.text())
        row1.distanceInput.setText(row2.distanceInput.text())

        # Copy stored row1 values to row2
        row2.directionInput.setText(temp_direction)
        row2.degreesInput.setText(temp_degrees)
        row2.minutesInput.setText(temp_minutes)
        row2.quadrantInput.setText(temp_quadrant)
        row2.distanceInput.setText(temp_distance)

    def move_row_up(self, row_widget):
        """Move a row up (swap values with the row above)."""
        try:
            index = self.bearing_rows.index(row_widget)
            # Don't allow swapping if this would move the first row (index 0)
            # or if we're trying to move row at index 1 up (which would swap with first row)
            if index > 1:
                # Swap values with the row above
                self.swap_row_values(self.bearing_rows[index], self.bearing_rows[index - 1])

                # Regenerate WKT with new values
                self.generate_wkt()
        except ValueError:
            pass

    def move_row_down(self, row_widget):
        """Move a row down (swap values with the row below)."""
        try:
            index = self.bearing_rows.index(row_widget)
            # Don't allow swapping if this is the last row
            # Also don't allow moving the first row (index 0) down
            if index > 0 and index < len(self.bearing_rows) - 1:
                # Swap values with the row below
                self.swap_row_values(self.bearing_rows[index], self.bearing_rows[index + 1])

                # Regenerate WKT with new values
                self.generate_wkt()
        except ValueError:
            pass

    def rebuild_layout(self):
        """Rebuild the bearing list layout with current row order."""
        # Remove all widgets from layout
        while self.bearingListLayout.count():
            item = self.bearingListLayout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Re-add widgets in new order
        for row in self.bearing_rows:
            self.bearingListLayout.addWidget(row)

    def get_bearing_data(self):
        """Get all bearing data from the rows"""
        data = []
        for row in self.bearing_rows:
            row_layout = row.layout()
            direction = row_layout.itemAt(0).widget().text().strip().upper()
            degrees = row_layout.itemAt(1).widget().text().strip()
            minutes = row_layout.itemAt(2).widget().text().strip()
            quadrant = row_layout.itemAt(3).widget().text().strip().upper()
            distance = row_layout.itemAt(4).widget().text().strip()

            if all([direction, degrees, minutes, quadrant, distance]):
                try:
                    data.append({
                        'direction': direction,
                        'degrees': int(degrees),
                        'minutes': int(minutes),
                        'quadrant': quadrant,
                        'distance': float(distance)
                    })
                except ValueError:
                    continue
        return data

    def draw_preview(self, coords, tie_point_coords=None):
        """Draw the polygon preview on the QgsMapCanvas with vertices and labels."""
        if not coords or len(coords) < 2:
            return

        # === POLYGON LAYER (original working code) ===
        # Create a memory layer for the preview
        self.preview_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Preview Layer", "memory")
        provider = self.preview_layer.dataProvider()

        # Create polygon geometry (original method that was working)
        polygon = QPolygonF([QPointF(x, y) for x, y in coords])
        geometry = QgsGeometry.fromPolygonXY([[QgsPointXY(p.x(), p.y()) for p in polygon]])

        # Create and add feature
        feature = QgsFeature()
        feature.setGeometry(geometry)
        provider.addFeatures([feature])

        # Update layer extent
        self.preview_layer.updateExtents()

        # Set consistent style for the preview layer
        symbol = QgsFillSymbol.createSimple({
            'color': '0,0,0,0',  # Transparent fill
            'outline_color': 'red',
            'outline_width': '1'
        })
        self.preview_layer.renderer().setSymbol(symbol)
        self.preview_layer.triggerRepaint()

        # === POINTS LAYER (for vertices) ===
        try:
            self.preview_points_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Vertices Layer", "memory")

            if self.preview_points_layer.isValid():
                points_provider = self.preview_points_layer.dataProvider()
                point_features = []

                # Add tie point if provided
                if tie_point_coords:
                    tp_feature = QgsFeature()
                    tp_feature.setGeometry(QgsGeometry.fromPointXY(
                        QgsPointXY(tie_point_coords[0], tie_point_coords[1])))
                    point_features.append(tp_feature)

                # Add polygon vertices
                for i, (x, y) in enumerate(coords):
                    point_feature = QgsFeature()
                    point_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                    point_features.append(point_feature)

                points_provider.addFeatures(point_features)
                self.preview_points_layer.updateExtents()

                # Style the point markers (teal colored circles)
                marker_symbol = QgsMarkerSymbol.createSimple({
                    'name': 'circle',
                    'color': "#ff0000",
                    'outline_color': '#ffffff',
                    'outline_width': '0.2',
                    'size': '4'
                })
                self.preview_points_layer.renderer().setSymbol(marker_symbol)
                self.preview_points_layer.triggerRepaint()

                # === ANNOTATION LAYER (for labels) ===
                self.preview_annotation_layer = QgsAnnotationLayer(
                    "Labels Layer",
                    QgsAnnotationLayer.LayerOptions(QgsProject.instance().transformContext()))

                # Configure text format for labels
                text_format = QgsTextFormat()
                text_format.setFont(QFont('Arial', 8, QFont.Weight.Bold))
                text_format.setSize(8)
                text_format.setColor(QColor("#000000"))

                # Add white buffer for visibility
                buffer_settings = text_format.buffer()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(1)
                buffer_settings.setColor(QColor('#ffffff'))
                text_format.setBuffer(buffer_settings)

                # Calculate dynamic label offset based on polygon extent ONLY (not including tie point)
                # This ensures labels stay proportionally close to markers for both small and large lots
                min_x = min(coord[0] for coord in coords)
                max_x = max(coord[0] for coord in coords)
                min_y = min(coord[1] for coord in coords)
                max_y = max(coord[1] for coord in coords)

                extent_width = max_x - min_x
                extent_height = max_y - min_y

                # Calculate diagonal of polygon extent as reference scale
                extent_diagonal = math.sqrt(extent_width**2 + extent_height**2)

                # Use 1% of diagonal as offset - scales proportionally:
                # Small lot (200 sqm ≈ 14x14m): diagonal ≈ 20m → offset ≈ 0.2m
                # Large lot (1 ha ≈ 100x100m): diagonal ≈ 141m → offset ≈ 1.41m
                label_offset_x = extent_diagonal * 0.01
                label_offset_y = extent_diagonal * 0.01

                # Add tie point label if provided
                if tie_point_coords:
                    tp_text_item = QgsAnnotationPointTextItem(
                        "TP",
                        QgsPointXY(tie_point_coords[0] + label_offset_x,
                                   tie_point_coords[1] + label_offset_y))
                    tp_text_item.setFormat(text_format)
                    self.preview_annotation_layer.addItem(tp_text_item)

                # Add labels for polygon vertices (1, 2, 3, etc.)
                for i, (x, y) in enumerate(coords):
                    text_item = QgsAnnotationPointTextItem(
                        str(i + 1),
                        QgsPointXY(x + label_offset_x, y + label_offset_y))
                    text_item.setFormat(text_format)
                    self.preview_annotation_layer.addItem(text_item)

                # Set all layers to canvas (polygon at bottom, points middle, annotations on top)
                # Note: In setLayers(), first layer renders on TOP, so reverse order for correct z-order
                self.previewCanvas.setLayers(
                    [self.preview_annotation_layer, self.preview_points_layer,
                     self.preview_layer])
            else:
                # Points layer failed, just use polygon layer
                self.preview_points_layer = None
                self.preview_annotation_layer = None
                self.previewCanvas.setLayers([self.preview_layer])
        except Exception as e:
            # If points/annotation layer fails, fall back to just polygon layer
            print(f"Points/annotation layer error: {e}")
            self.preview_points_layer = None
            self.preview_annotation_layer = None
            self.previewCanvas.setLayers([self.preview_layer])

        self.zoom_preview_to_layer()
        self.previewCanvas.refresh()

    def generate_wkt(self):
        """Generate WKT using Excel's coordinate calculation method."""
        try:
            # Get tie point coordinates
            tie_n = float(self.tiePointNorthingInput.text().strip().replace(",", "."))
            tie_e = float(self.tiePointEastingInput.text().strip().replace(",", "."))

            # Initialize coordinates list and current position
            coords = []
            current_n = tie_n
            current_e = tie_e

            # Track the final position after ALL bearing rows (for misclosure)
            final_n = tie_n
            final_e = tie_e

            # Process all bearing rows except the last one (for polygon vertices)
            for row in self.bearing_rows[:-1]:
                try:
                    # Get values from the row
                    ns = row.directionInput.text().strip().upper()
                    deg = int(row.degreesInput.text().strip())
                    min_ = int(row.minutesInput.text().strip())
                    ew = row.quadrantInput.text().strip().upper()
                    dist = float(row.distanceInput.text().strip().replace(",", "."))

                    # Calculate deltas
                    delta_lat, delta_dep = calculate_deltas(ns, deg, min_, ew, dist)

                    # Update current position
                    current_n += delta_lat
                    current_e += delta_dep

                    # Add to coordinates list
                    coords.append((current_e, current_n))

                except (ValueError, AttributeError):
                    self._clear_info_panel()
                    return

            # Process ALL bearing rows to calculate final position for misclosure
            for row in self.bearing_rows:
                try:
                    ns = row.directionInput.text().strip().upper()
                    deg = int(row.degreesInput.text().strip())
                    min_ = int(row.minutesInput.text().strip())
                    ew = row.quadrantInput.text().strip().upper()
                    dist = float(row.distanceInput.text().strip().replace(",", "."))

                    delta_lat, delta_dep = calculate_deltas(ns, deg, min_, ew, dist)
                    final_n += delta_lat
                    final_e += delta_dep
                except (ValueError, AttributeError):
                    pass  # Skip incomplete rows for misclosure calculation

            # Check if we have enough points for a polygon
            if len(coords) < 3:
                self.labelWKT.setText("Insufficient points for a polygon (minimum 3)")
                self._clear_info_panel()
                # Clear the preview layers as it's not a valid polygon
                if self.preview_layer and self.preview_layer.isValid():
                    QgsProject.instance().removeMapLayer(self.preview_layer)
                    self.preview_layer = None
                if self.preview_points_layer and self.preview_points_layer.isValid():
                    QgsProject.instance().removeMapLayer(self.preview_points_layer)
                    self.preview_points_layer = None
                if self.preview_annotation_layer:
                    self.preview_annotation_layer = None
                self.previewCanvas.setLayers([])
                self.previewCanvas.refresh()
                self.check_print_report_enabled()
                return

            # Create polygon and generate WKT
            # Ensure coordinates are in (Easting, Northing) format for WKT
            wkt_coords = ', '.join([f'{x} {y}' for x, y in coords])
            # Add the starting point to close the polygon
            if coords:
                wkt_coords += f', {coords[0][0]} {coords[0][1]}'

            self.last_wkt = f"POLYGON (({wkt_coords}))"

            # Update the WKT preview label
            self.labelWKT.setText(self.last_wkt)

            # Update visual preview (draw the polygon on the map canvas with tie point)
            self.draw_preview(coords, tie_point_coords=(tie_e, tie_n))

            # Calculate and display area
            area = calculate_polygon_area(coords)
            self._update_area_display(area)

            # Calculate and display variance (Title Area - Actual Area)
            self._update_variance_display(area)

            # Calculate and display misclosure
            misclosure = calculate_misclosure(tie_e, tie_n, final_e, final_n)
            self._update_misclosure_display(misclosure)

            # Update Print Report button state
            self.check_print_report_enabled()

        except ValueError:
            self.labelWKT.setText("Error: Invalid numeric input")
            self._clear_info_panel()
            self.check_print_report_enabled()
        except Exception as e:
            self.labelWKT.setText(f"An unexpected error occurred: {str(e)}")
            self._clear_info_panel()
            self.check_print_report_enabled()

    def _update_area_display(self, area):
        """Update the area display label with formatted value."""
        if area >= 10000:
            hectares = area / 10000
            self.areaValueLabel.setText(f"{hectares:,.4f} ha")
        else:
            self.areaValueLabel.setText(f"{area:,.2f} sq.m.")

        # Teal styling for area value
        self.areaValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)

    def _update_variance_display(self, actual_area):
        """Update the variance display label with calculated value (Title Area - Actual Area)."""
        import re

        title_area_text = self.titleAreaInput.text().strip()

        # If title area is empty, show N/A
        if not title_area_text:
            self.varianceValueLabel.setText("N/A")
            self.varianceValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)
            return

        # Extract numeric value from title area input (handles "500 sq.m.", "500", "500.5", etc.)
        numeric_match = re.search(r'[\d,]+\.?\d*', title_area_text.replace(',', ''))
        if not numeric_match:
            self.varianceValueLabel.setText("N/A")
            self.varianceValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)
            return

        try:
            title_area = float(numeric_match.group().replace(',', ''))
            variance = title_area - actual_area

            # Format the variance value with sign
            if variance >= 0:
                self.varianceValueLabel.setText(f"+{variance:,.2f} sq.m.")
            else:
                self.varianceValueLabel.setText(f"{variance:,.2f} sq.m.")

            # Teal styling for variance value
            self.varianceValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)
        except ValueError:
            self.varianceValueLabel.setText("N/A")
            self.varianceValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)

    def _update_misclosure_display(self, misclosure):
        """Update the misclosure display label with formatted value and color coding."""
        # Format the misclosure value
        if misclosure < 0.01:
            self.misclosureValueLabel.setText(f"{misclosure:.4f} m")
            # Teal for excellent closure
            self.misclosureValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)
        elif misclosure < 0.1:
            self.misclosureValueLabel.setText(f"{misclosure:.3f} m")
            # Teal for acceptable closure
            self.misclosureValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)
        else:
            self.misclosureValueLabel.setText(f"{misclosure:.2f} m")
            # Teal for poor closure
            self.misclosureValueLabel.setStyleSheet("""
                QLabel {
                    color: #14575b;
                    font-size: 13pt;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                }
            """)

    def _clear_info_panel(self):
        """Clear the area, variance, and misclosure display labels."""
        self.areaValueLabel.setText("-- sq.m.")
        self.areaValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        self.varianceValueLabel.setText("N/A")
        self.varianceValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        self.misclosureValueLabel.setText("-- m")
        self.misclosureValueLabel.setStyleSheet("""
            QLabel {
                color: #14575b;
                font-size: 13pt;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)

    def open_tiepoint_selector(self):
        """Opens the tie point selection dialog."""
        if TiePointSelectorDialog is None:
            QtWidgets.QMessageBox.warning(
                self, "Dependency Missing",
                "The tie point selector dialog file (tie_point_selector_dialog.py) was not found.")
            return

        dialog = TiePointSelectorDialog(self)
        if dialog.exec():  # exec_() returns QDialog.Accepted or QDialog.Rejected
            selected_row = dialog.get_selected_row()
            if selected_row:
                self.tie_point = selected_row
                self.tiePointNorthingInput.setText(str(selected_row.get('northing', '')))
                self.tiePointEastingInput.setText(str(selected_row.get('easting', '')))
                # Update preview after selecting a tie point
                self.generate_wkt()

    def parse_bearing(self, direction, degrees, minutes, quadrant):
        """Parse bearing components into azimuth."""
        try:
            # Convert to integers and validate
            deg = int(degrees)
            min_ = int(minutes)

            # Validate degrees and minutes
            if deg < 0 or deg > 90:
                raise ValueError(f"Degrees must be between 0 and 90 (got {deg})")
            if min_ < 0 or min_ > 59:
                raise ValueError(f"Minutes must be between 0 and 59 (got {min_})")

            # Calculate azimuth
            angle = deg + (min_ / 60)

            if direction.upper() == "N" and quadrant.upper() == "E":
                return angle
            elif direction.upper() == "S" and quadrant.upper() == "E":
                return 180 - angle
            elif direction.upper() == "S" and quadrant.upper() == "W":
                return 180 + angle
            elif direction.upper() == "N" and quadrant.upper() == "W":
                return 360 - angle
            else:
                raise ValueError(f"Invalid bearing direction combination: {direction}{quadrant}")
        except ValueError as e:
            raise ValueError(f"Invalid bearing: {e}")

    def calculate_point(self, start_point, bearing_azimuth, distance):
        """Calculates the next point based on a starting point, azimuth, and distance.
        Bearing azimuth should be in degrees.
        Returns a tuple (x, y) or None if inputs are invalid.
        """
        try:
            # Normalize decimal separator in distance
            distance = float(str(distance).replace(",", "."))
            if bearing_azimuth is None or distance < 0:
                return None

            # Convert azimuth from degrees to radians for trigonometric functions
            azimuth_rad = math.radians(bearing_azimuth)

            # Calculate displacements (Easting is X, Northing is Y)
            dx = distance * math.sin(azimuth_rad)
            dy = distance * math.cos(azimuth_rad)

            next_x = start_point[0] + dx
            next_y = start_point[1] + dy

            return (next_x, next_y)

        except ValueError:
            # Handle cases where distance conversion fails
            print(f"Invalid distance value: {distance}")
            return None
        except Exception as e:
            print(f"Error calculating point: {e}")
            return None

    def calculate_coordinates(self):
        """Parses bearing/distance inputs from all rows and calculates the polygon coordinates.
        Returns a list of (x, y) tuples or an empty list if inputs are invalid.
        """
        coords = []
        try:
            # Get starting tie point coordinates (Easting, Northing)
            easting_text = self.tiePointEastingInput.text().strip().replace(",", ".")
            northing_text = self.tiePointNorthingInput.text().strip().replace(",", ".")

            if not easting_text or not northing_text:
                self.wktOutput.setPlainText("Error: Tie point coordinates are required.")
                return []

            start_easting = float(easting_text)
            start_northing = float(northing_text)
            current_point = (start_easting, start_northing)
            coords.append(current_point)

            # Iterate through bearing input rows
            layout = self.bearingListLayout
            if layout is None:
                print("Error: bearingListLayout is not initialized.")
                return []

            for i in range(layout.count()):
                row_item = layout.itemAt(i)
                if row_item and row_item.widget():
                    row_widget = row_item.widget()
                    row_layout = row_widget.layout()

                    if row_layout and row_layout.count() >= 5:
                        # Get values from the QLineEdit widgets in the row
                        direction = row_layout.itemAt(0).widget().text()
                        degrees = row_layout.itemAt(1).widget().text()
                        minutes = row_layout.itemAt(2).widget().text()
                        quadrant = row_layout.itemAt(3).widget().text()
                        # Normalize decimal separator in distance
                        distance = row_layout.itemAt(4).widget().text().strip().replace(",", ".")

                        # Check if essential fields are filled for this row
                        if not any([direction, degrees, minutes, quadrant, distance]):
                            continue

                        if not all([direction, degrees, minutes, quadrant, distance]):
                            self.wktOutput.setPlainText(f"Error: Incomplete bearing input in row {i + 1}.")
                            return []

                        # Parse bearing and calculate the next point
                        bearing_azimuth = self.parse_bearing(direction, degrees, minutes, quadrant)

                        if bearing_azimuth is None:
                            self.wktOutput.setPlainText(f"Error: Invalid bearing format in row {i + 1}.")
                            return []

                        next_point = self.calculate_point(current_point, bearing_azimuth, distance)

                        if next_point:
                            coords.append(next_point)
                            current_point = next_point
                        else:
                            self.wktOutput.setPlainText(f"Error: Invalid distance value in row {i + 1}.")
                            return []

            return coords

        except ValueError:
            self.wktOutput.setPlainText("Error: Invalid numeric input found.")
            return []
        except Exception as e:
            self.wktOutput.setPlainText(f"An unexpected error occurred during coordinate calculation: {e}")
            return []

    def zoom_preview_to_layer(self):
        """Zoom the preview canvas to fit the entire polygon with padding."""
        if self.preview_layer and self.preview_layer.isValid():
            # Get the layer extent
            extent = self.preview_layer.extent()

            if extent.isEmpty():
                return

            # Get canvas dimensions
            canvas_width = self.previewCanvas.width()
            canvas_height = self.previewCanvas.height()

            if canvas_width <= 0 or canvas_height <= 0:
                # Fallback if canvas dimensions are not available yet
                self.previewCanvas.setExtent(extent)
                self.previewCanvas.refresh()
                return

            # Calculate the aspect ratios
            extent_width = extent.width()
            extent_height = extent.height()

            # Handle edge cases where extent has zero width or height (line or point)
            if extent_width <= 0:
                extent_width = extent_height if extent_height > 0 else 1
            if extent_height <= 0:
                extent_height = extent_width if extent_width > 0 else 1

            canvas_aspect = canvas_width / canvas_height
            extent_aspect = extent_width / extent_height

            # Add padding (15% on each side)
            padding_factor = 0.15

            # Calculate the new extent to fit the polygon while maintaining aspect ratio
            if extent_aspect > canvas_aspect:
                # Extent is wider than canvas - fit width, expand height
                new_width = extent_width * (1 + 2 * padding_factor)
                new_height = new_width / canvas_aspect
            else:
                # Extent is taller than canvas - fit height, expand width
                new_height = extent_height * (1 + 2 * padding_factor)
                new_width = new_height * canvas_aspect

            # Calculate the center of the extent
            center_x = extent.center().x()
            center_y = extent.center().y()

            # Create new extent centered on the polygon
            new_extent = QgsRectangle(
                center_x - new_width / 2,
                center_y - new_height / 2,
                center_x + new_width / 2,
                center_y + new_height / 2
            )

            self.previewCanvas.setExtent(new_extent)
            self.previewCanvas.refresh()

    PLOT_LAYER_NAMES = ("Title Plot Preview", "Title Plot Vertices", "Title Plot Lines")

    @staticmethod
    def _string_field(name):
        """Create a string QgsField across QGIS APIs (QMetaType on 3.38+, QVariant before)."""
        try:
            return QgsField(name, QMetaType.Type.QString)
        except TypeError:
            return QgsField(name, QVariant.String)

    def _plot_label_format(self):
        """Text format shared by the plotted-lot labels: red text with a white buffer."""
        text_format = QgsTextFormat()
        text_format.setFont(QFont('Arial', 8, QFont.Weight.Bold))
        text_format.setSize(8)
        text_format.setColor(QColor('red'))

        buffer_settings = text_format.buffer()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1)
        buffer_settings.setColor(QColor('#ffffff'))
        text_format.setBuffer(buffer_settings)
        return text_format

    def _label_placement(self, name):
        """Resolve a label placement enum across QGIS 3.22 - 4.x APIs."""
        try:
            from qgis.core import Qgis
            return getattr(Qgis.LabelPlacement, name)
        except (ImportError, AttributeError):
            return getattr(QgsPalLayerSettings, name)

    def _apply_plot_labels(self, layer, expression, is_expression, placement_name, dist=0.0):
        """Enable simple labeling on one of the plotted-lot memory layers."""
        settings = QgsPalLayerSettings()
        settings.fieldName = expression
        settings.isExpression = is_expression
        settings.placement = self._label_placement(placement_name)
        if dist:
            try:
                settings.dist = dist
            except AttributeError:
                pass  # property removed in a future API; default distance is acceptable
        settings.setFormat(self._plot_label_format())
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    def _plot_ring_points(self, geometry):
        """Exterior-ring vertices of the plotted polygon, without the closing point."""
        polygon = geometry.asPolygon()
        if not polygon and geometry.isMultipart():
            multi = geometry.asMultiPolygon()
            polygon = multi[0] if multi else []
        if not polygon or not polygon[0]:
            return []
        ring = list(polygon[0])
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        return ring

    def _build_plot_vertex_layer(self, ring, crs_authid):
        """Corner markers: hollow red circles, each labeled with the line it starts (1-2, 2-3, ...)."""
        layer = QgsVectorLayer(f"Point?crs={crs_authid}", "Title Plot Vertices", "memory")
        layer.dataProvider().addAttributes([self._string_field("line_name")])
        layer.updateFields()

        n = len(ring)
        features = []
        for i in range(n):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(ring[i]))
            feature.setAttributes([f"{i + 1}-{(i + 1) % n + 1}"])
            features.append(feature)
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()

        symbol = QgsMarkerSymbol.createSimple({
            'name': 'circle',
            'color': '255,255,255,0',  # hollow fill
            'outline_color': 'red',
            'outline_width': '0.4',
            'size': '2.6'
        })
        layer.renderer().setSymbol(symbol)
        self._apply_plot_labels(layer, "line_name", False, "AroundPoint", dist=1.5)
        return layer

    def _build_plot_line_layer(self, ring, crs_authid):
        """One line feature per lot segment, labeled with its length along the line."""
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "Title Plot Lines", "memory")
        layer.dataProvider().addAttributes([self._string_field("line_name")])
        layer.updateFields()

        n = len(ring)
        features = []
        for i in range(n):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPolylineXY([ring[i], ring[(i + 1) % n]]))
            feature.setAttributes([f"{i + 1}-{(i + 1) % n + 1}"])
            features.append(feature)
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()

        symbol = QgsLineSymbol.createSimple({
            'line_color': 'red',
            'line_width': '0.3'
        })
        layer.renderer().setSymbol(symbol)
        self._apply_plot_labels(layer, "round($length / 1000, 2) || ' m'", True, "Line")
        return layer

    def plot_on_map(self):
        """Plot the polygon on the map canvas."""
        if not self.last_wkt:
            QMessageBox.warning(self, "Error", "No valid polygon to plot.")
            return

        try:
            # Get the map canvas from the main window and check its CRS
            canvas = self.iface.mapCanvas()
            if not canvas:
                QMessageBox.warning(self, "Warning", "Could not access map canvas.")
                return

            canvas_crs = canvas.mapSettings().destinationCrs()

            # Check if the canvas CRS is EPSG:4326 (WGS84)
            if canvas_crs.authid() == "EPSG:4326":
                # Show informative message and open CRS selection dialog
                QMessageBox.information(
                    self,
                    "Select Coordinate System",
                    "The current project is using WGS84 (EPSG:4326) which uses latitude/longitude.\n\n"
                    "Title Plotter requires a local projected coordinate system.\n\n"
                    "Please select an appropriate Philippine coordinate system:\n"
                    "• PRS92 / Philippines Zone 3 (EPSG:3123)\n"
                    "• PRS92 / Philippines Zone 4 (EPSG:3124)\n"
                    "• PRS92 / Philippines Zone 5 (EPSG:3125)"
                )

                # Open CRS selection dialog
                crs_dialog = QgsProjectionSelectionDialog(self)
                crs_dialog.setWindowTitle("Select Project Coordinate System")
                crs_dialog.setCrs(QgsCoordinateReferenceSystem("EPSG:3123"))  # Default to PRS92 Zone 3

                if crs_dialog.exec():
                    selected_crs = crs_dialog.crs()

                    # Check if user selected a valid non-WGS84 CRS
                    if selected_crs.isValid() and selected_crs.authid() != "EPSG:4326":
                        # Set the project CRS
                        QgsProject.instance().setCrs(selected_crs)
                        canvas_crs = selected_crs
                    else:
                        QMessageBox.warning(
                            self,
                            "Invalid Selection",
                            "Please select a projected coordinate system (not WGS84)."
                        )
                        return
                else:
                    # User cancelled the dialog
                    return

            # Remove existing title-plot layers if they exist
            for existing_layer in list(QgsProject.instance().mapLayers().values()):
                if existing_layer.name() in self.PLOT_LAYER_NAMES:
                    QgsProject.instance().removeMapLayer(existing_layer)

            # Create a new memory layer with the canvas CRS
            layer = QgsVectorLayer(f"Polygon?crs={canvas_crs.authid()}", "Title Plot Preview", "memory")

            # Add attribute field for feature identification
            layer.dataProvider().addAttributes([self._string_field("name")])
            layer.updateFields()

            # Create and add feature
            feature = QgsFeature()

            # Parse WKT and create geometry
            geometry = QgsGeometry.fromWkt(self.last_wkt)

            # Validate geometry
            if not geometry or geometry.isEmpty():
                QMessageBox.warning(self, "Invalid Geometry", "The generated polygon is empty or invalid.")
                return

            if not geometry.isGeosValid():
                QMessageBox.warning(self, "Invalid Geometry", "The generated polygon is not valid.")
                return

            # Set geometry and attributes
            feature.setGeometry(geometry)
            feature.setAttributes(["Title Plot"])

            # Add feature to layer
            layer.dataProvider().addFeatures([feature])

            # Update layer extent and add to project
            layer.updateExtents()
            QgsProject.instance().addMapLayer(layer)

            # Set layer style: thin red boundary line, no fill
            symbol = QgsFillSymbol.createSimple({
                'style': 'no',
                'outline_color': 'red',
                'outline_width': '0.3'
            })
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()

            # Companion layers: per-segment length labels + labeled corner markers
            # (added after the polygon so they render above it)
            ring = self._plot_ring_points(geometry)
            if ring:
                QgsProject.instance().addMapLayer(
                    self._build_plot_line_layer(ring, canvas_crs.authid()))
                QgsProject.instance().addMapLayer(
                    self._build_plot_vertex_layer(ring, canvas_crs.authid()))

            # Zoom to the new polygon, with a margin so corner labels stay visible
            extent = QgsRectangle(layer.extent())
            extent.scale(1.15)
            canvas.setExtent(extent)
            canvas.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to plot polygon: {str(e)}")

    def open_ocr_dialog(self):
        """Open the LLM OCR dialog for TCT image processing."""
        if not OCR_AVAILABLE:
            QMessageBox.warning(self, "OCR Unavailable",
                                "LLM OCR dialog module could not be loaded.")
            return

        dialog = LLMOCRDialog(self)
        dialog.exec()

    def resizeEvent(self, event):
        """Handles resize event for the dialog."""
        super().resizeEvent(event)

    def print_report(self):
        """Export a PDF technical report with landscape 2-column Survey Plan layout."""
        # Get save file path
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Technical Report",
            os.path.join(
                os.path.expanduser("~"),
                f"Survey_Plan_{self.lotNumberInput.text().strip().replace(' ', '_')}.pdf"),
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        # Ensure .pdf extension
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'

        try:
            # Create PDF writer with Letter size in LANDSCAPE orientation
            writer = QPdfWriter(file_path)
            page_layout = QPageLayout(
                QPageSize(QPageSize.PageSizeId.Letter),
                QPageLayout.Orientation.Landscape,
                QMarginsF(5, 5, 5, 5)  # 12mm margins
            )
            writer.setPageLayout(page_layout)
            writer.setResolution(300)  # 300 DPI for high quality

            # Get page dimensions in device pixels
            page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
            page_width = page_rect.width()
            page_height = page_rect.height()

            # Create painter
            painter = QPainter(writer)

            # Define colors
            header_color = QColor("#14575b")
            text_color = QColor("#252b33")
            border_color = QColor("#14575b")
            table_header_bg = QColor("#14575b")
            table_alt_bg = QColor("#f6f8fb")

            # Define fonts (scaled for 300 DPI)
            title_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
            subtitle_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
            section_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            value_font = QFont("Segoe UI", 9)
            small_font = QFont("Segoe UI", 7)

            # Calculate layout dimensions
            margin = 50  # pixels
            column_gap = 20  # Gap between columns inside the container

            # Three-column layout inside one container
            # Tech Desc (30%) | Lot Preview (40%) | Property Info (30%)
            usable_width = page_width - 2 * margin
            container_padding = 15  # Padding inside the main container
            inner_width = usable_width - 2 * container_padding - 2 * column_gap
            left_col_width = int(inner_width * 0.25)  # Technical Description
            middle_col_width = int(inner_width * 0.50)  # Lot Preview
            right_col_width = inner_width - left_col_width - middle_col_width  # Property Info

            # Current Y position
            y = margin

            # === THREE-COLUMN LAYOUT INSIDE ONE CONTAINER ===
            # (Header moved to right column)
            content_height = page_height - y - margin - 50  # Leave space for footer
            container_rect = QRectF(margin, y, usable_width, content_height)

            # Draw main container border and background (thin dark teal border)
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            painter.drawRect(container_rect.toRect())

            # Column positions inside the container
            left_x = margin + container_padding
            middle_x = left_x + left_col_width + column_gap
            right_x = middle_x + middle_col_width + column_gap
            content_start_y = y + container_padding
            content_inner_height = content_height - 2 * container_padding

            # === LEFT COLUMN: TECHNICAL DESCRIPTION ===
            table_x = left_x
            table_y_start = content_start_y

            # Calculate table dimensions
            table_width = left_col_width
            row_height = 40
            header_height = 40
            title_height = 50
            num_rows = len(self.bearing_rows)
            table_content_height = header_height + (num_rows * row_height)

            # Reset painter state for table drawing
            painter.setBrush(Qt.NoBrush)

            # Table title header background
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QBrush(table_header_bg))
            title_rect = QRectF(table_x, table_y_start, table_width, title_height)
            painter.drawRect(title_rect.toRect())

            # Table title text
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "TECHNICAL DESCRIPTION")
            table_y = table_y_start + title_height

            # Draw table background (white)
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            table_bg_rect = QRectF(table_x, table_y, table_width, table_content_height)
            painter.drawRect(table_bg_rect.toRect())

            # Column widths for vertical table layout
            col_widths = [
                int(table_width * 0.16),  # Line
                int(table_width * 0.12),  # N/S
                int(table_width * 0.15),  # Deg
                int(table_width * 0.15),  # Min
                int(table_width * 0.12),  # E/W
                int(table_width * 0.30),  # Distance
            ]
            headers = ["Line", "N/S", "Deg", "Min", "E/W", "Dist (m)"]

            # Table header row background
            painter.fillRect(int(table_x), int(table_y), int(table_width), header_height, table_header_bg)

            # Table header text
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.setPen(Qt.GlobalColor.white)
            painter.setBrush(Qt.NoBrush)

            col_x = table_x
            for header, width in zip(headers, col_widths):
                header_rect = QRectF(col_x, table_y, width, header_height)
                painter.drawText(header_rect, Qt.AlignmentFlag.AlignCenter, header)
                col_x += width

            table_y += header_height

            # Table data rows
            table_data_font = QFont("Segoe UI", 7)
            painter.setFont(table_data_font)

            for i, row in enumerate(self.bearing_rows):
                # Alternate row background
                if i % 2 == 0:
                    painter.fillRect(int(table_x), int(table_y), int(table_width), row_height, table_alt_bg)

                # Set pen for text
                painter.setPen(text_color)
                painter.setBrush(Qt.NoBrush)

                col_x = table_x
                row_data = [
                    row.lineLabel.text(),
                    row.directionInput.text().strip().upper(),
                    row.degreesInput.text().strip(),
                    row.minutesInput.text().strip(),
                    row.quadrantInput.text().strip().upper(),
                    row.distanceInput.text().strip()
                ]

                for data, width in zip(row_data, col_widths):
                    cell_rect = QRectF(col_x, table_y, width, row_height)
                    painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, data)
                    col_x += width

                # Draw row border
                painter.setPen(QPen(border_color, 0.5))
                painter.drawLine(int(table_x), int(table_y + row_height),
                                 int(table_x + table_width), int(table_y + row_height))
                table_y += row_height

            # Draw table outer border
            painter.setPen(QPen(border_color, 2))
            painter.setBrush(Qt.NoBrush)
            full_table_rect = QRectF(table_x, table_y_start, table_width, title_height + table_content_height)
            painter.drawRect(full_table_rect.toRect())

            # === MIDDLE COLUMN: LOT PREVIEW (map) ===
            if self.preview_layer and self.preview_layer.isValid():
                # Map area is in the middle column
                map_x = middle_x
                map_y = content_start_y
                map_width = middle_col_width
                map_height = content_inner_height

                # Render the map canvas to an image
                img_width = int(map_width * 2)
                img_height = int(map_height * 2)
                img = QImage(img_width, img_height, QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.white)

                map_painter = QPainter(img)
                map_painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                # Get the extent and render
                extent = self.preview_layer.extent()
                if extent.isNull() or not extent.isFinite():
                    extent = QgsRectangle(-100, -100, 100, 100)

                # Calculate proper zoom to fit with aspect ratio preservation
                map_aspect = map_width / map_height
                extent_width = extent.width()
                extent_height = extent.height()

                # Handle zero dimensions
                if extent_width <= 0:
                    extent_width = 1
                if extent_height <= 0:
                    extent_height = 1

                # Add padding for better visual appearance (zoom to fit with margins)
                padding_factor = 0.35  # 35% padding on each side for comfortable fit

                # First, expand the extent by padding on all sides
                padded_width = extent_width * (1 + padding_factor * 2)
                padded_height = extent_height * (1 + padding_factor * 2)

                # Adjust extent to match map aspect ratio (centers the polygon)
                center_x = extent.center().x()
                center_y = extent.center().y()

                if padded_width / padded_height > map_aspect:
                    # Padded extent is wider than map - use width as constraint
                    new_width = padded_width
                    new_height = new_width / map_aspect
                else:
                    # Padded extent is taller than map - use height as constraint
                    new_height = padded_height
                    new_width = new_height * map_aspect

                # Create the final extent centered on the polygon
                extent = QgsRectangle(
                    center_x - new_width / 2,
                    center_y - new_height / 2,
                    center_x + new_width / 2,
                    center_y + new_height / 2
                )

                # Set up map settings for rendering
                from qgis.core import QgsMapSettings, QgsMapRendererCustomPainterJob

                # === SCALE UP SYMBOLS FOR PDF OUTPUT ===
                # Store original sizes and scale up for better PDF visibility
                pdf_scale_factor = 5  # Scale factor for PDF rendering

                original_marker_size = None
                original_outline_width = None
                if self.preview_points_layer and self.preview_points_layer.isValid():
                    marker_symbol = self.preview_points_layer.renderer().symbol()
                    if marker_symbol:
                        original_marker_size = marker_symbol.size()
                        original_outline_width = (
                            marker_symbol.symbolLayer(0).strokeWidth()
                            if marker_symbol.symbolLayerCount() > 0 else 0.2)
                        # Scale up marker size for PDF
                        marker_symbol.setSize(original_marker_size * pdf_scale_factor)
                        if marker_symbol.symbolLayerCount() > 0:
                            marker_symbol.symbolLayer(0).setStrokeWidth(original_outline_width * pdf_scale_factor)

                original_text_formats = []
                if self.preview_annotation_layer:
                    # Scale up annotation text for PDF
                    for item_id in self.preview_annotation_layer.items():
                        item = self.preview_annotation_layer.item(item_id)
                        if hasattr(item, 'format'):
                            text_format = item.format()
                            original_size = text_format.size()
                            original_buffer_size = text_format.buffer().size() if text_format.buffer().enabled() else 1
                            original_text_formats.append((item_id, original_size, original_buffer_size))
                            # Scale up text size for PDF
                            text_format.setSize(original_size * pdf_scale_factor)
                            # Also scale up the buffer
                            buffer_settings = text_format.buffer()
                            if buffer_settings.enabled():
                                buffer_settings.setSize(original_buffer_size * pdf_scale_factor)
                                text_format.setBuffer(buffer_settings)
                            item.setFormat(text_format)

                map_settings = QgsMapSettings()
                # Include polygon, points, and annotation layers for rendering
                # Note: In setLayers(), first layer renders on TOP, so build list with polygon last
                layers_to_render = []
                if self.preview_annotation_layer:
                    layers_to_render.append(self.preview_annotation_layer)
                if self.preview_points_layer and self.preview_points_layer.isValid():
                    layers_to_render.append(self.preview_points_layer)
                layers_to_render.append(self.preview_layer)
                map_settings.setLayers(layers_to_render)
                map_settings.setExtent(extent)
                map_settings.setOutputSize(img.size())
                map_settings.setBackgroundColor(Qt.GlobalColor.white)

                # Render
                render_job = QgsMapRendererCustomPainterJob(map_settings, map_painter)
                render_job.start()
                render_job.waitForFinished()

                map_painter.end()

                # Draw the image on PDF
                map_rect = QRectF(map_x, map_y, map_width, map_height)
                painter.drawImage(map_rect.toRect(), img)

                # === RESTORE ORIGINAL SYMBOL SIZES ===
                # Restore marker size
                if (self.preview_points_layer and self.preview_points_layer.isValid()
                        and original_marker_size is not None):
                    marker_symbol = self.preview_points_layer.renderer().symbol()
                    if marker_symbol:
                        marker_symbol.setSize(original_marker_size)
                        if marker_symbol.symbolLayerCount() > 0 and original_outline_width is not None:
                            marker_symbol.symbolLayer(0).setStrokeWidth(original_outline_width)
                    self.preview_points_layer.triggerRepaint()

                # Restore annotation text sizes
                if self.preview_annotation_layer and original_text_formats:
                    for item_id, original_size, original_buffer_size in original_text_formats:
                        item = self.preview_annotation_layer.item(item_id)
                        if hasattr(item, 'format'):
                            text_format = item.format()
                            text_format.setSize(original_size)
                            # Restore buffer size
                            buffer_settings = text_format.buffer()
                            if buffer_settings.enabled():
                                buffer_settings.setSize(original_buffer_size)
                                text_format.setBuffer(buffer_settings)
                            item.setFormat(text_format)

                # Refresh the canvas to show original sizes
                self.previewCanvas.refresh()

            # === RIGHT COLUMN: PROPERTY INFORMATION ===
            # Draw solid black border around right column
            right_col_rect = QRectF(right_x, content_start_y, right_col_width, content_inner_height)
            painter.setPen(QPen(QColor("#000000"), 2))  # Solid black border
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            painter.drawRect(right_col_rect.toRect())

            right_col_padding = 35  # MASSIVELY increased padding inside right column for maximum breathing room
            right_y = content_start_y + right_col_padding
            right_col_max_y = content_start_y + content_inner_height - right_col_padding  # Maximum Y boundary

            # Helper function to draw wrapped text and return actual height used
            def draw_wrapped_text(text, x, y, width, font, color, align_flags):
                """Draw text with word wrapping using QFontMetrics and return the actual height used."""
                painter.setFont(font)
                painter.setPen(QPen(color))

                # Use QFontMetrics to calculate proper line height with leading
                fm = QFontMetrics(font)

                # Calculate line height including leading for better readability
                line_height = fm.height()  # This includes ascent + descent + leading

                # Calculate bounding rectangle with word wrap enabled
                bounding_rect = fm.boundingRect(
                    int(x), int(y), int(width), 10000,  # Large height for calculation
                    align_flags | Qt.TextFlag.TextWordWrap,
                    text
                )

                # Calculate number of lines based on bounding rect height
                actual_height = bounding_rect.height()
                num_lines = max(1, int(actual_height / line_height) + 1)  # Add 1 to ensure enough space

                # Calculate the RENDERING height - use line_height * num_lines for proper display
                rendering_height = line_height * num_lines * 1.5  # 1.5x multiplier to ensure no clipping

                # Add SIGNIFICANT extra spacing for return value (positioning next element)
                extra_spacing = int(line_height * 0.5 * num_lines) if num_lines > 1 else int(line_height * 0.3)
                total_height = actual_height + extra_spacing

                # Create a LARGE rect for drawing to prevent ANY clipping
                draw_rect = QRectF(x, y, width, rendering_height)

                # Draw the text with word wrapping - this rect must be LARGE enough
                painter.drawText(draw_rect, align_flags | Qt.TextFlag.TextWordWrap, text)

                # Return the height for positioning (not the rendering height)
                return total_height

            # === LOT REPORT HEADER (centered at top of right column) ===
            title_text = "LOT REPORT"
            title_height = draw_wrapped_text(
                title_text,
                right_x + right_col_padding,
                right_y,
                right_col_width - 2 * right_col_padding,
                title_font,
                header_color,
                Qt.AlignmentFlag.AlignCenter
            )
            # Use font metrics for spacing after title - INCREASED
            fm_title = QFontMetrics(title_font)
            title_spacing = int(fm_title.height() * 1.2)  # 1.2x title font height (was 0.5)
            right_y += title_height + title_spacing

            # Subtitle with lot and survey info (centered)
            subtitle = f"{self.lotNumberInput.text().strip()} - {self.surveyNumberInput.text().strip()}"
            subtitle_height = draw_wrapped_text(
                subtitle,
                right_x + right_col_padding,
                right_y,
                right_col_width - 2 * right_col_padding,
                subtitle_font,
                text_color,
                Qt.AlignmentFlag.AlignCenter
            )
            # Use font metrics for spacing after subtitle - MASSIVELY INCREASED
            fm_subtitle = QFontMetrics(subtitle_font)
            subtitle_spacing = int(fm_subtitle.height() * 3.0)  # 3x subtitle font height (was 1.5)
            right_y += subtitle_height + subtitle_spacing

            # Helper function to draw a property field with proper wrapping
            def draw_field(label, value, y_pos, is_header=False):
                """Draw a property field with label and value, using font metrics for proper spacing."""
                # Check if we have space left in the column
                if y_pos >= right_col_max_y:
                    return y_pos  # Stop drawing if we've reached the bottom

                field_padding = right_col_padding
                field_width = right_col_width - field_padding * 2

                if is_header:
                    # Section header - centered, bold with LARGE extra spacing
                    header_height = draw_wrapped_text(
                        label,
                        right_x + field_padding,
                        y_pos,
                        field_width,
                        section_font,
                        header_color,
                        Qt.AlignmentFlag.AlignCenter
                    )
                    # Use QFontMetrics to calculate proper spacing after header - INCREASED
                    fm = QFontMetrics(section_font)
                    section_spacing = int(fm.height() * 2.0)  # 2x header font height (was 0.8)
                    return y_pos + header_height + section_spacing
                else:
                    # Label - centered with font-based spacing
                    label_height = draw_wrapped_text(
                        label,
                        right_x + field_padding,
                        y_pos,
                        field_width,
                        label_font,
                        header_color,
                        Qt.AlignmentFlag.AlignCenter
                    )

                    # Calculate spacing between label and value - INCREASED
                    fm_label = QFontMetrics(label_font)
                    label_value_spacing = int(fm_label.height() * 1.0)  # 1x label font height (was 0.4)
                    y_pos += label_height + label_value_spacing

                    # Value - centered with wrapping
                    value_height = draw_wrapped_text(
                        value,
                        right_x + field_padding,
                        y_pos,
                        field_width,
                        value_font,
                        text_color,
                        Qt.AlignmentFlag.AlignCenter
                    )

                    # Calculate spacing after value - MASSIVELY INCREASED
                    fm_value = QFontMetrics(value_font)
                    after_value_spacing = int(fm_value.height() * 1.8)  # 1.8x value font height (was 0.6)

                    return y_pos + value_height + after_value_spacing

            # --- Property Information Section ---
            right_y = draw_field("PROPERTY INFORMATION", "", right_y, is_header=True)
            right_y = draw_field("Registered Owner", self.registeredOwnerInput.text().strip(), right_y)
            right_y = draw_field("Lot Number", self.lotNumberInput.text().strip(), right_y)
            right_y = draw_field("Survey Number", self.surveyNumberInput.text().strip(), right_y)
            right_y = draw_field("Title Area", self.titleAreaInput.text().strip(), right_y)

            # Section spacing based on section font height for visual separation - INCREASED
            fm_section = QFontMetrics(section_font)
            section_break_spacing = int(fm_section.height() * 2.5)  # 2.5x section font height (was 1.2)
            right_y += section_break_spacing

            # --- Location Section ---
            right_y = draw_field("LOCATION", "", right_y, is_header=True)
            right_y = draw_field("Barangay", self.barangayInput.text().strip(), right_y)
            right_y = draw_field("Municipality/City", self.municipalityInput.text().strip(), right_y)
            right_y = draw_field("Province", self.provinceInput.text().strip(), right_y)

            right_y += section_break_spacing

            # --- Tie Point Section ---
            right_y = draw_field("TIE POINT COORDINATES", "", right_y, is_header=True)
            right_y = draw_field("Northing", self.tiePointNorthingInput.text().strip(), right_y)
            right_y = draw_field("Easting", self.tiePointEastingInput.text().strip(), right_y)

            right_y += section_break_spacing

            # --- Computed Values Section ---
            right_y = draw_field("COMPUTED VALUES", "", right_y, is_header=True)
            right_y = draw_field("Computed Area", self.areaValueLabel.text(), right_y)
            variance_text = self.varianceValueLabel.text() if hasattr(self, 'varianceValueLabel') else "N/A"
            right_y = draw_field("Variance", variance_text, right_y)
            right_y = draw_field("Misclosure", self.misclosureValueLabel.text(), right_y)

            # === FOOTER ===
            footer_y = page_height - margin - 15

            # Footer font: small + italic
            footer_font = QFont(small_font)
            footer_font.setPointSize(3)
            footer_font.setItalic(True)

            # Date on left (wrapped)
            date_text = f"Generated: {QDate.currentDate().toString('MMMM d, yyyy')} | QGIS Title Plotter v1.2.0"
            date_width = (page_width - 2 * margin) / 2 - 10
            draw_wrapped_text(
                date_text,
                margin,
                footer_y - 10,
                date_width,
                footer_font,
                text_color,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            # Credit on right (wrapped)
            credit_text = (
                "This lot report is for visual reference only and does not "
                "establish legal boundaries. For official verification, "
                "consult a licensed surveyor or geodetic engineer.")
            credit_width = (page_width - 2 * margin) / 2 - 10
            draw_wrapped_text(
                credit_text,
                page_width / 2 + 10,
                footer_y - 10,
                credit_width,
                footer_font,
                text_color,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            painter.end()

            # Show success message with options to open the PDF or folder
            self._show_pdf_saved_dialog(file_path)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export report:\n{str(e)}"
            )

    def _show_pdf_saved_dialog(self, file_path):
        """Show a custom dialog with options to open the PDF or containing folder."""
        # Create custom message box
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Report Exported Successfully")
        msg_box.setIcon(QMessageBox.Icon.Information)

        # Get file name and folder path
        file_name = os.path.basename(file_path)
        folder_path = os.path.dirname(file_path)

        # Create message text with clickable path
        msg_box.setText("Technical report has been saved successfully!")
        msg_box.setInformativeText(
            f"<b>File:</b> {file_name}<br>"
            f"<b>Location:</b> {folder_path}"
        )

        # Add custom buttons
        open_pdf_btn = msg_box.addButton("Open PDF", QMessageBox.ActionRole)
        open_folder_btn = msg_box.addButton("Open Folder", QMessageBox.ActionRole)
        msg_box.addButton("Close", QMessageBox.RejectRole)

        # Style the dialog
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #252b33;
                font-size: 9pt;
            }
            QPushButton {
                background-color: #14575b;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                color: #ffffff;
                font-size: 8pt;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #114a4e;
            }
            QPushButton:pressed {
                background-color: #114a4e;
            }
        """)

        # Show dialog and handle button clicks
        msg_box.exec()

        # Check which button was clicked
        clicked_button = msg_box.clickedButton()

        if clicked_button == open_pdf_btn:
            # Open the PDF file
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Open Error",
                    f"Could not open PDF:\n{str(e)}"
                )
        elif clicked_button == open_folder_btn:
            # Open the folder containing the PDF
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Open Error",
                    f"Could not open folder:\n{str(e)}"
                )

    def reset_plotter(self):
        """Reset all inputs and clear the plotter."""
        # Clear tie point inputs
        self.tiePointNorthingInput.setText("")
        self.tiePointEastingInput.setText("")
        self.tie_point = None

        # Clear all bearing rows except the first one
        while len(self.bearing_rows) > 1:
            self.remove_bearing_row(self.bearing_rows[-1])

        # Reset the first row
        if self.bearing_rows:
            self.bearing_rows[0].reset_values()

        # Clear property information fields
        self.registeredOwnerInput.setText("")
        self.barangayInput.setText("")
        self.municipalityInput.setText("")
        self.provinceInput.setText("")
        self.lotNumberInput.setText("")
        self.surveyNumberInput.setText("")
        self.titleAreaInput.setText("")

        # Clear WKT and preview
        self.labelWKT.setText("")
        self.last_wkt = None
        if self.preview_layer and self.preview_layer.isValid():
            QgsProject.instance().removeMapLayer(self.preview_layer)
            self.preview_layer = None
        if self.preview_points_layer and self.preview_points_layer.isValid():
            QgsProject.instance().removeMapLayer(self.preview_points_layer)
            self.preview_points_layer = None
        if self.preview_annotation_layer:
            self.preview_annotation_layer = None
        self.previewCanvas.setLayers([])
        self.previewCanvas.refresh()

        # Clear area and misclosure info panel
        self._clear_info_panel()

        # Update Print Report button state
        self.check_print_report_enabled()

    def export_data(self):
        """Export all current data to a JSON file."""
        try:
            # Collect all data
            data = {
                "version": "1.0",
                "tie_point": {
                    "northing": self.tiePointNorthingInput.text().strip(),
                    "easting": self.tiePointEastingInput.text().strip()
                },
                "property_info": {
                    "registered_owner": self.registeredOwnerInput.text().strip(),
                    "lot_number": self.lotNumberInput.text().strip(),
                    "survey_number": self.surveyNumberInput.text().strip(),
                    "title_area": self.titleAreaInput.text().strip(),
                    "barangay": self.barangayInput.text().strip(),
                    "municipality": self.municipalityInput.text().strip(),
                    "province": self.provinceInput.text().strip()
                },
                "bearing_rows": []
            }

            # Collect bearing row data
            for row in self.bearing_rows:
                row_data = {
                    "direction": row.directionInput.text().strip(),
                    "degrees": row.degreesInput.text().strip(),
                    "minutes": row.minutesInput.text().strip(),
                    "quadrant": row.quadrantInput.text().strip(),
                    "distance": row.distanceInput.text().strip()
                }
                # Only add if at least one field has data
                if any(row_data.values()):
                    data["bearing_rows"].append(row_data)

            # Generate default filename based on lot number
            lot_number = self.lotNumberInput.text().strip().replace(" ", "_") or "plot"
            default_filename = f"{lot_number}_data.json"

            # Open save dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Plot Data",
                os.path.join(os.path.expanduser("~"), default_filename),
                "JSON Files (*.json);;All Files (*)"
            )

            if file_path:
                # Ensure .json extension
                if not file_path.lower().endswith('.json'):
                    file_path += '.json'

                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Plot data has been exported to:\n{file_path}"
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export data:\n{str(e)}"
            )

    def import_data(self):
        """Import data from a JSON file."""
        try:
            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Plot Data",
                os.path.expanduser("~"),
                "JSON Files (*.json);;All Files (*)"
            )

            if not file_path:
                return

            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate data structure
            if not isinstance(data, dict):
                raise ValueError("Invalid file format: expected JSON object")

            # Ask user if they want to clear existing data
            if any([
                self.tiePointNorthingInput.text().strip(),
                self.tiePointEastingInput.text().strip(),
                self.registeredOwnerInput.text().strip(),
                any(row.directionInput.text().strip() for row in self.bearing_rows)
            ]):
                reply = QMessageBox.question(
                    self,
                    "Import Data",
                    "This will replace all current data. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # Clear existing data first
            self.reset_plotter()

            # Import tie point data
            tie_point = data.get("tie_point", {})
            if tie_point.get("northing"):
                self.tiePointNorthingInput.setText(tie_point["northing"])
            if tie_point.get("easting"):
                self.tiePointEastingInput.setText(tie_point["easting"])

            # Import property info
            prop_info = data.get("property_info", {})
            if prop_info.get("registered_owner"):
                self.registeredOwnerInput.setText(prop_info["registered_owner"])
            if prop_info.get("lot_number"):
                self.lotNumberInput.setText(prop_info["lot_number"])
            if prop_info.get("survey_number"):
                self.surveyNumberInput.setText(prop_info["survey_number"])
            if prop_info.get("title_area"):
                self.titleAreaInput.setText(prop_info["title_area"])
            if prop_info.get("barangay"):
                self.barangayInput.setText(prop_info["barangay"])
            if prop_info.get("municipality"):
                self.municipalityInput.setText(prop_info["municipality"])
            if prop_info.get("province"):
                self.provinceInput.setText(prop_info["province"])

            # Import bearing rows
            bearing_rows = data.get("bearing_rows", [])
            if bearing_rows:
                # Fill first row
                first_row_data = bearing_rows[0]
                if self.bearing_rows:
                    first_row = self.bearing_rows[0]
                    first_row.directionInput.setText(first_row_data.get("direction", ""))
                    first_row.degreesInput.setText(first_row_data.get("degrees", ""))
                    first_row.minutesInput.setText(first_row_data.get("minutes", ""))
                    first_row.quadrantInput.setText(first_row_data.get("quadrant", ""))
                    first_row.distanceInput.setText(first_row_data.get("distance", ""))

                # Add and fill additional rows
                for row_data in bearing_rows[1:]:
                    self.add_bearing_row()
                    new_row = self.bearing_rows[-1]
                    new_row.directionInput.setText(row_data.get("direction", ""))
                    new_row.degreesInput.setText(row_data.get("degrees", ""))
                    new_row.minutesInput.setText(row_data.get("minutes", ""))
                    new_row.quadrantInput.setText(row_data.get("quadrant", ""))
                    new_row.distanceInput.setText(row_data.get("distance", ""))

            # Update UI state
            self.check_print_report_enabled()

            # Trigger preview update if we have enough data
            if len(bearing_rows) >= 3:
                self.generate_wkt()

            QMessageBox.information(
                self,
                "Import Successful",
                f"Plot data has been imported from:\n{file_path}"
            )

        except json.JSONDecodeError as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Invalid JSON file:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import data:\n{str(e)}"
            )
