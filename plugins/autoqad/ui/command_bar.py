# -*- coding: utf-8 -*-
"""The command line — AutoQAD's bottom dock.

A history pane over an input line, with the active prompt shown inline to the
left of the caret, exactly where a CAD user expects it. Keyboard behaviour is
the part that carries the feel:

* **Enter** on an empty line repeats the previous command.
* **Escape** cancels the running command.
* **Up / Down** walk the command history.
* **Tab** completes against the registry.
* **Space** at the start behaves like Enter, as AutoCAD's command line does.

The status toggles (SNAP, GRID, ORTHO, POLAR, OSNAP, LWT, DYN) sit along the
bottom edge, each bound to the system variable of the same name so the button
and the variable can never drift apart.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget, QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import theme

MAX_HISTORY_LINES = 500


class CommandInput(QLineEdit):
    """The input line, with CAD keyboard semantics."""

    escapePressed = pyqtSignal()
    historyBack = pyqtSignal()
    historyForward = pyqtSignal()
    completeRequested = pyqtSignal()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            self.historyBack.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            self.historyForward.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Tab:
            self.completeRequested.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Space and not self.text():
            # A leading space submits, matching AutoCAD's command line.
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CommandBarDock(QDockWidget):
    """History pane, prompt, input line and status toggles."""

    #: The user submitted a line of input.
    submitted = pyqtSignal(str)
    #: The user pressed Escape.
    cancelled = pyqtSignal()

    def __init__(self, variables, registry, parent=None):
        super().__init__("AutoQAD Command Line", parent)
        self.setObjectName("aqCommandBar")
        self.variables = variables
        self.registry = registry

        self._history = []
        self._history_index = 0

        self._build()
        theme.apply(self)
        self.variables.changed.connect(self._on_variable_changed)
        self.set_current_layer(self.variables.get("CLAYER"))

    # ---- construction ----

    def _build(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.history_view = QTextEdit(container)
        self.history_view.setObjectName("aqCommandHistory")
        self.history_view.setReadOnly(True)
        self.history_view.setMinimumHeight(64)
        self.history_view.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Expanding)
        layout.addWidget(self.history_view, 1)

        prompt_row = QFrame(container)
        prompt_layout = QHBoxLayout(prompt_row)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(0)

        self.prompt_label = QLabel("Command:", prompt_row)
        self.prompt_label.setObjectName("aqPromptLabel")
        prompt_layout.addWidget(self.prompt_label, 0)

        self.input = CommandInput(prompt_row)
        self.input.setObjectName("aqCommandInput")
        self.input.setPlaceholderText("Type a command — LINE, PL, REC, C, H …")
        prompt_layout.addWidget(self.input, 1)
        layout.addWidget(prompt_row, 0)

        layout.addWidget(self._build_status_bar(container), 0)

        self.setWidget(container)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea
                             | Qt.DockWidgetArea.TopDockWidgetArea)

        self.input.returnPressed.connect(self._on_submit)
        self.input.escapePressed.connect(self._on_escape)
        self.input.historyBack.connect(self._history_back)
        self.input.historyForward.connect(self._history_forward)
        self.input.completeRequested.connect(self._complete)

    def _build_status_bar(self, parent):
        """A readout strip: cursor coordinates and the current layer.

        No mode toggles. Drafting modes are driven by their function keys
        (F3/F8/F9/F10) and the DSETTINGS dialog, which is what a CAD user
        reaches for — a row of on-screen buttons duplicates knowledge they
        already have.
        """
        bar = QFrame(parent)
        bar.setObjectName("aqStatusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(12)

        self.coordinate_label = QLabel("", bar)
        self.coordinate_label.setProperty("role", "muted")
        layout.addWidget(self.coordinate_label)

        layout.addStretch(1)

        self.layer_label = QLabel("", bar)
        self.layer_label.setProperty("role", "muted")
        layout.addWidget(self.layer_label)

        return bar

    # ---- input handling ----

    def _on_submit(self):
        text = self.input.text()
        self.input.clear()
        if text.strip():
            self._history.append(text)
            self._history_index = len(self._history)
        self.submitted.emit(text)

    def _on_escape(self):
        self.input.clear()
        self.cancelled.emit()

    def _history_back(self):
        if not self._history:
            return
        self._history_index = max(0, self._history_index - 1)
        self.input.setText(self._history[self._history_index])

    def _history_forward(self):
        if not self._history:
            return
        self._history_index = min(len(self._history), self._history_index + 1)
        if self._history_index >= len(self._history):
            self.input.clear()
        else:
            self.input.setText(self._history[self._history_index])

    def _complete(self):
        prefix = self.input.text().strip()
        if not prefix:
            return
        matches = self.registry.completions(prefix)
        if len(matches) == 1:
            self.input.setText(matches[0])
        elif matches:
            self.write(" ".join(matches[:20]))

    # ---- output ----

    def write(self, text):
        """Append a line to the history pane."""
        if not text:
            return
        self.history_view.append(str(text))
        self._trim_history()
        scrollbar = self.history_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _trim_history(self):
        document = self.history_view.document()
        while document.blockCount() > MAX_HISTORY_LINES:
            cursor = self.history_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def set_prompt(self, text):
        """Show the active prompt beside the caret."""
        self.prompt_label.setText(text or "Command:")

    def set_coordinates(self, point, precision=4):
        if point is None:
            self.coordinate_label.setText("")
            return
        self.coordinate_label.setText(
            "{0:.{p}f}, {1:.{p}f}".format(point[0], point[1], p=precision))

    def set_current_layer(self, name):
        self.layer_label.setText("  Layer: {0}  ".format(name or "0"))

    def focus_input(self):
        self.input.setFocus(Qt.FocusReason.OtherFocusReason)

    # ---- variable feedback ----

    def _on_variable_changed(self, name):
        if name in ("CLAYER", "*"):
            self.set_current_layer(self.variables.get("CLAYER"))
