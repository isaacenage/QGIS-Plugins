# -*- coding: utf-8 -*-
"""The command box that opens at the cursor when you start typing.

In CAD mode the letter keys belong to the command line, not to the host
application — that is the AutoCAD contract, and it is why typing ``L`` starts a
line instead of toggling a layer panel. The cost is that a keystroke can
disappear into a command line the user is not looking at, twenty centimetres
below where their eyes are. AutoCAD's answer, and this module's, is to bring
the command line *to the cursor*: type anything and a small box opens
below-right of the crosshair, carrying what you typed.

Two things make it feel like AutoCAD rather than a text field on a map:

**Suggestions.** Every keystroke re-filters the command registry and lists what
you might mean — ranked by :meth:`~..engine.registry.CommandRegistry.suggest`,
so ``PL`` puts PLINE first because PL *is* its alias, and ``POL`` offers
POLYGON. Arrow keys walk the list, Enter or a click takes one.

**Inline completion.** The rest of the best match is appended and left
selected, so the next keystroke replaces it if you disagree and Enter accepts
it if you do not. Nothing is ever rewritten ahead of the caret; a completion
only extends what was actually typed.

The box **pins where it opened** rather than chasing the mouse. Reading a
suggestion list that slides away as the pointer drifts is unusable, and the
mouse is nearly always still while typing anyway.

While a command is running the same box serves its prompt, and the suggestions
become that prompt's keyword options — so ``Specify next point or
[Arc/Undo/Close]`` offers Arc, Undo and Close by name.
"""

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QLineEdit, QListWidget, QListWidgetItem

from ..ui import theme

#: Offset from the cursor to the box, in pixels. Below-right, clear of the
#: crosshair's own arms.
OFFSET_X = 18
OFFSET_Y = 18
#: Gap between the box and its suggestion list.
GAP = 2
#: Never narrower than this, so a one-letter command does not open a sliver.
MIN_WIDTH = 132
MAX_WIDTH = 340
#: Suggestion rows shown before the list scrolls.
MAX_ROWS = 8


def _entry_qss():
    return (
        "QLineEdit {{"
        " background:#ffffff; border:1px solid {accent}; color:{text};"
        " border-radius:3px; padding:2px 6px;"
        " font-family:{mono}; font-size:12px;"
        " selection-background-color:{accent}; selection-color:#ffffff;"
        "}}"
    ).format(accent=theme.PALETTE["accent"], text=theme.PALETTE["text"],
             mono=theme.MONO_FONT_STACK)


def _list_qss():
    return (
        "QListWidget {{"
        " background:#ffffff; border:1px solid {border}; color:{text};"
        " border-radius:3px; outline:none; padding:2px;"
        " font-family:{mono}; font-size:12px;"
        "}}"
        "QListWidget::item {{ padding:2px 6px; border-radius:2px; }}"
        "QListWidget::item:selected {{"
        " background:{brand_soft}; color:{accent};"
        "}}"
    ).format(border=theme.PALETTE["border"], text=theme.PALETTE["text"],
             brand_soft=theme.PALETTE["brand_soft"],
             accent=theme.PALETTE["accent"], mono=theme.MONO_FONT_STACK)


class _CommandEntry(QLineEdit):
    """The typed line. Reports intent; the owner decides what it means."""

    submitRequested = pyqtSignal()
    cancelRequested = pyqtSignal()
    #: Walk the suggestion list; carries -1 or +1 (or a page step).
    navigateRequested = pyqtSignal(int)
    #: Tab — take the highlighted suggestion without running it.
    completeRequested = pyqtSignal()
    #: Backspace on an already-empty line: the user is backing out.
    emptied = pyqtSignal()
    #: A character was *inserted* (as opposed to deleted). Completion hangs
    #: off this rather than off the text getting longer, because accepting a
    #: completion and then typing over it makes the text shorter — which is
    #: exactly the moment the next completion is wanted.
    charInserted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        #: Set by the owner from the running prompt; decides what Space means.
        self.literal_space = False

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitRequested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.completeRequested.emit()
            event.accept()
            return

        step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1,
                Qt.Key.Key_PageDown: MAX_ROWS,
                Qt.Key.Key_PageUp: -MAX_ROWS}.get(key)
        if step is not None:
            self.navigateRequested.emit(step)
            event.accept()
            return

        if key == Qt.Key.Key_Space and not self.literal_space:
            # A space submits at the command line, as it does in AutoCAD —
            # except where the answer is prose and a space is just a space.
            self.submitRequested.emit()
            event.accept()
            return

        if key == Qt.Key.Key_Backspace and not self.text():
            self.emptied.emit()
            event.accept()
            return

        typed = event.text()
        super().keyPressEvent(event)
        if typed and typed.isprintable():
            self.charInserted.emit()


class DynamicCommandInput(QObject):
    """Owns the cursor-anchored command box and its suggestion list."""

    #: A line was entered; carries the text, exactly as the dock's input does.
    submitted = pyqtSignal(str)
    #: Escape at an empty box — abort whatever is running.
    cancelled = pyqtSignal()
    #: The box opened or closed, so other cursor overlays can make room.
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, canvas, variables, registry, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.variables = variables
        self.registry = registry

        self._prompt = None
        self._enabled = False
        self._anchor = None
        #: Own the open/shown state rather than reading it back off Qt.
        #: A child of a hidden parent reports ``isVisible() == False`` however
        #: many times it was shown, which makes visibility a poor answer to
        #: "is the box up?".
        self._open = False
        self._list_shown = False
        #: Guards the refresh pass while we are the ones editing.
        self._updating = False

        self._entry = _CommandEntry(canvas)
        self._entry.setStyleSheet(_entry_qss())
        self._entry.hide()

        self._list = QListWidget(canvas)
        self._list.setStyleSheet(_list_qss())
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The entry keeps the keyboard; the list is driven from it. Clicking a
        # row is still allowed, which is why it is not fully disabled.
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.hide()

        self._entry.textEdited.connect(self._on_text_edited)
        self._entry.charInserted.connect(self._on_char_inserted)
        self._entry.submitRequested.connect(self._on_submit)
        self._entry.cancelRequested.connect(self._on_cancel)
        self._entry.navigateRequested.connect(self._navigate)
        self._entry.completeRequested.connect(self._take_suggestion)
        self._entry.emptied.connect(self.close)
        self._list.itemClicked.connect(lambda _item: self._accept_clicked())

    # ---- state ----

    @property
    def is_open(self):
        return self._open

    def set_enabled(self, enabled):
        """Enable the box. Disabled, typing falls back to the command dock."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self.close()

    @property
    def enabled(self):
        return self._enabled and bool(self.variables.get("DYNCMDINPUT"))

    def set_prompt(self, prompt):
        """Adopt the runner's active prompt (or ``None`` when idle)."""
        self._prompt = prompt
        self._entry.literal_space = bool(
            getattr(prompt, "literal_space", False))
        if self.is_open:
            self._entry.setPlaceholderText(self._placeholder())

    def _placeholder(self):
        if self._prompt is None:
            return "Command"
        return (self._prompt.message or "").strip()

    # ---- opening / closing ----

    def type_text(self, text, screen_pos=None):
        """Absorb a character typed on the canvas. True if it was taken.

        This is the *first* keystroke's path — it opens the box. Everything
        after it arrives at the entry directly, because opening gives the
        entry the keyboard focus.
        """
        if not self.enabled or not text:
            return False

        if not self._open:
            if text == "\b":
                return False          # nothing to erase; leave it alone
            self._show(screen_pos)

        if text == "\b":
            self._entry.backspace()
        else:
            self._entry.insert(text)

        self._refresh_suggestions(self._entry.text())
        if text != "\b":
            self._on_char_inserted()
        self._layout()
        return True

    def _show(self, screen_pos):
        self._anchor = self._anchor_point(screen_pos)
        self._entry.clear()
        self._entry.setPlaceholderText(self._placeholder())
        self._entry.show()
        self._entry.raise_()
        self._entry.setFocus(Qt.FocusReason.OtherFocusReason)
        self._open = True
        self._layout()
        self.visibilityChanged.emit(True)

    def _anchor_point(self, screen_pos):
        if screen_pos is None:
            return (OFFSET_X, OFFSET_Y)
        try:
            return (int(screen_pos.x()), int(screen_pos.y()))
        except AttributeError:
            return (int(screen_pos[0]), int(screen_pos[1]))

    def close(self):
        """Hide the box and hand the keyboard back to the canvas."""
        if not self._open and not self._list_shown:
            return
        self._entry.clear()
        self._entry.hide()
        self._hide_list()
        self._open = False
        self._anchor = None
        try:
            self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        except (RuntimeError, AttributeError):
            pass
        self.visibilityChanged.emit(False)

    #: Height the box occupies, so other cursor overlays can stack under it.
    def reserved_height(self):
        return self._entry.height() + GAP if self._open else 0

    # ---- editing ----

    def _on_text_edited(self, text):
        """The text changed under the user's hands — re-filter only.

        Completion deliberately does *not* hang off this: it has to know
        whether a character went in or came out, and the text alone cannot
        say (typing over an accepted completion makes it shorter).
        """
        if self._updating:
            return
        self._refresh_suggestions(text)
        self._layout()

    def _on_char_inserted(self):
        if not self._wants_completion():
            return
        self._apply_inline_completion(self._entry.text())
        self._layout()

    def _wants_completion(self):
        # Completing a command *name* is helpful; completing a coordinate or a
        # piece of prose is not, and would fight every keystroke.
        return self._prompt is None and bool(
            self.variables.get("AUTOCOMPLETE"))

    def _apply_inline_completion(self, text):
        completion = self.registry.best_completion(text)
        if not completion or len(completion) <= len(text):
            return
        self._updating = True
        try:
            self._entry.setText(completion)
            # Leave the appended part selected: type on to reject it, press
            # Enter to accept it. The suggestion list keeps the *typed*
            # filter, which is why it is refreshed before this runs.
            self._entry.setSelection(len(text), len(completion) - len(text))
        finally:
            self._updating = False

    # ---- suggestions ----

    def _refresh_suggestions(self, text):
        rows = self._suggestions(text)
        self._list.clear()

        if not rows:
            self._hide_list()
            return

        for label, detail in rows:
            item = QListWidgetItem(label)
            if detail:
                item.setToolTip(detail)
            self._list.addItem(item)

        self._list.setCurrentRow(0)
        self._list.show()
        self._list.raise_()
        self._list_shown = True

    def _hide_list(self):
        self._list.hide()
        self._list_shown = False

    def _suggestions(self, text):
        """``[(label, tooltip)]`` for the current prompt and typed text."""
        typed = (text or "").strip()
        if not typed:
            return []

        if self._prompt is None:
            return [(self._suggestion_label(row), row.description)
                    for row in self.registry.suggest(typed, limit=MAX_ROWS)]

        # Inside a command the useful list is the prompt's own keywords.
        upper = typed.upper()
        return [(option, "") for option in getattr(self._prompt, "options", [])
                if option.upper().startswith(upper)][:MAX_ROWS]

    @staticmethod
    def _suggestion_label(row):
        if not row.hint:
            return row.name
        return "{0}  ({1})".format(row.name, row.hint)

    @staticmethod
    def _label_value(label):
        """The command/keyword a row stands for, without its alias hint."""
        return label.split("  (")[0].strip()

    def _navigate(self, step):
        count = self._list.count()
        if not count or not self._list_shown:
            return
        row = min(count - 1, max(0, self._list.currentRow() + step))
        self._list.setCurrentRow(row)

    def _highlighted(self):
        item = self._list.currentItem()
        if item is None or not self._list_shown:
            return ""
        return self._label_value(item.text())

    def _take_suggestion(self):
        """Tab — put the highlighted suggestion in the box, do not run it."""
        value = self._highlighted()
        if not value:
            return
        self._updating = True
        try:
            self._entry.setText(value)
        finally:
            self._updating = False
        self._refresh_suggestions(value)
        self._layout()

    def _accept_clicked(self):
        value = self._highlighted()
        if value:
            self._emit(value)

    # ---- committing ----

    def _on_submit(self):
        text = self._entry.text()
        if not text.strip():
            # A bare Enter still means something — repeat, or finish the
            # current prompt — so it goes through as an empty line.
            self._emit("")
            return
        self._emit(text.strip())

    def _emit(self, text):
        self.close()
        self.submitted.emit(text)

    def _on_cancel(self):
        had_text = bool(self._entry.text())
        self.close()
        if not had_text:
            # Escape on an empty box means "abort the command", the same as
            # Escape on the canvas. With text in it, it just clears the box.
            self.cancelled.emit()

    # ---- geometry ----

    def _layout(self):
        """Place the box below-right of where it opened, and the list under it.

        Both are flipped rather than clipped when they would leave the canvas,
        so the box is always fully readable near an edge.
        """
        if self._anchor is None or not self._open:
            return

        width = self._preferred_width()
        self._entry.setFixedWidth(width)
        self._entry.adjustSize()
        self._entry.setFixedWidth(width)

        x = self._anchor[0] + OFFSET_X
        y = self._anchor[1] + OFFSET_Y
        height = self._entry.height()

        list_height = self._list_height() if self._list_shown else 0
        total = height + (GAP + list_height if list_height else 0)

        if x + width > self.canvas.width():
            x = max(0, self._anchor[0] - OFFSET_X - width)
        if y + total > self.canvas.height():
            y = max(0, self._anchor[1] - OFFSET_Y - total)

        self._entry.move(x, y)
        if list_height:
            self._list.setGeometry(x, y + height + GAP, width, list_height)

    def _preferred_width(self):
        metrics = self._entry.fontMetrics()
        text = self._entry.text() or self._entry.placeholderText()
        needed = metrics.horizontalAdvance(text) + 28
        for index in range(self._list.count()):
            item = self._list.item(index)
            needed = max(needed,
                         metrics.horizontalAdvance(item.text()) + 28)
        return max(MIN_WIDTH, min(MAX_WIDTH, needed))

    def _list_height(self):
        count = self._list.count()
        if not count:
            return 0
        row = self._list.sizeHintForRow(0)
        if row <= 0:
            row = self._entry.height()
        return row * min(count, MAX_ROWS) + 6

    # ---- teardown ----

    def dispose(self):
        for widget in (self._list, self._entry):
            try:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            except (RuntimeError, AttributeError):
                pass
