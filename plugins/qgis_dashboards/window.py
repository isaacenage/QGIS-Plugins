# -*- coding: utf-8 -*-
"""Dashboard window — a standalone top-level dashboard.

Per the redesign the dashboard is no longer docked inside QGIS: it is its own
window (``QMainWindow``). It holds a tab bar + a ``QStackedWidget`` of pages;
each page is a :class:`PageView` (a scroll area wrapping one free-form
drag/resize :class:`DashboardCanvas`). The window owns the one shared
:class:`DashboardBus` (theme + live ``iface`` are global; cross-filter wiring
is page-local).

Persistence: the whole dashboard — every page's tiles and their pixel
placement, the per-page connection graph, the theme and the window size — is
serialized to JSON (schema v3) in the ``.qgz`` project file and restored on
open. ``migrate_layout`` upgrades the older v1 (bare list) and v2 (single page)
blobs on load.
"""

import copy
import json
import os
import uuid

from qgis.PyQt.QtWidgets import (
    QMainWindow, QLabel, QWidget, QFrame, QHBoxLayout, QToolButton,
    QTabBar, QStackedWidget, QVBoxLayout, QMessageBox, QInputDialog, QMenu,
    QFileDialog,
)
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtCore import Qt, QSize, QEvent, QTimer, pyqtSignal
from qgis.PyQt import sip
from qgis.core import QgsProject

# QShortcut lives in QtWidgets on Qt5 (PyQt5) but moved to QtGui on Qt6 (PyQt6);
# import defensively so the plugin works across QGIS 3.22 – 4.99.
try:                                          # Qt6 / PyQt6
    from qgis.PyQt.QtGui import QShortcut
except ImportError:                           # pragma: no cover - Qt5 / PyQt5
    from qgis.PyQt.QtWidgets import QShortcut

from .history import History

from .bus import DashboardBus
from .theme import Theme, CHROME
from .layout_util import default_locked
from .auto_layout import compute_auto_layout
from . import project_io
from .recent_store import RecentStore
from .start_view import StartView
from . import user_fonts
from .export.theme_css import referenced_families
from .icons import logo_icon, monochrome_icon
from .sidebar import Sidebar
from .minimized_bubble import MinimizedBubble
from .dashboard_canvas import (
    DashboardCanvas, DEFAULT_REGION_W, DEFAULT_REGION_H, MARGIN as CANVAS_MARGIN)
from .page_view import PageView
from .elements import create_element, ELEMENT_LABELS
from .elements.header_layout import materialize_header_tiles
from .add_element_dialog import AddElementDialog, ElementConfigForm
from .element_picker import ElementPicker
from .settings_dialog import SettingsPanel
from .tile_style_form import TileStyleForm
from .connections_dialog import ConnectionsForm
from .side_panel import InspectorPanel

PROJECT_SCOPE = "QgisDashboard"
PROJECT_KEY = "layout"
DEFAULT_COLS = 12
DEFAULT_ROWS = 8
DEFAULT_GAP = 0   # global element gap (logical px): cards may touch by default
# the export/print region (the "page") — one global size for the whole dashboard
DEFAULT_CANVAS_W = DEFAULT_REGION_W
DEFAULT_CANVAS_H = DEFAULT_REGION_H
CANVAS_SIZE_STEP = 40   # round a content-derived region up to a tidy multiple


def migrate_layout(raw):
    """Normalize any stored layout (v1 list / v2 dict / v3 dict) to v3.

    v3 shape::

        {version, grid:{cols,rows}, gap, canvas:{w,h}?, theme, window, locked,
         active_page, pages:[{id, title, connections, elements:[...]}]}
    """
    if not raw:
        raw = {"elements": []}
    # v1: a bare list of element configs
    if isinstance(raw, list):
        raw = {"elements": raw}

    version = raw.get("version", 2)
    grid = raw.get("grid", {})
    out = {
        "version": 3,
        "grid": {"cols": grid.get("cols", DEFAULT_COLS),
                 "rows": grid.get("rows", DEFAULT_ROWS)},
        "gap": int(raw.get("gap", DEFAULT_GAP)),
        # the export/print region; absent in older blobs (resolved from the
        # content bounding box on apply so existing exports don't change)
        "canvas": raw.get("canvas") or None,
        "theme": raw.get("theme") or {},
        "window": raw.get("window", {}),
        # optional global header (brand banner); absent in v1/v2/older v3 blobs
        "header": raw.get("header") or None,
        # embedded custom fonts (.qdash / HTML only; never in a .qgz blob);
        # carried through untouched so opening installs them. Absent elsewhere.
        "fonts": raw.get("fonts") or None,
    }

    if version >= 3 and isinstance(raw.get("pages"), list):
        pages = []
        for p in raw["pages"]:
            pages.append({
                "id": p.get("id") or uuid.uuid4().hex[:8],
                "title": p.get("title") or "Page",
                "connections": p.get("connections") or {},
                "elements": p.get("elements") or [],
                "header": p.get("header") or None,
            })
        if not pages:
            pages = [{"id": uuid.uuid4().hex[:8], "title": "Page 1",
                      "connections": {}, "elements": []}]
        out["pages"] = pages
        out["active_page"] = raw.get("active_page") or pages[0]["id"]
    else:
        # v1/v2: collapse into a single page
        page = {
            "id": uuid.uuid4().hex[:8],
            "title": "Page 1",
            "connections": raw.get("connections") or {},
            "elements": raw.get("elements") or [],
        }
        out["pages"] = [page]
        out["active_page"] = page["id"]

    # Lock/Use mode: persisted as a top-level bool. Older blobs (no key) default
    # via content — a dashboard with tiles opens in Use mode, an empty one in
    # Build mode — so existing dashboards open ready to use, not ready to edit.
    out["locked"] = (bool(raw["locked"]) if "locked" in raw
                     else default_locked(out))
    return out


class DashboardPage:
    """One dashboard page: an id/title plus its PageView (and its canvas)."""

    def __init__(self, page_id, title, view):
        self.id = page_id
        self.title = title
        self.view = view
        self.canvas = view.canvas


class DashboardWindow(QMainWindow):
    closed = pyqtSignal()   # the window was hidden/closed by the user

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        user_fonts.register_all()   # register the user's installed custom fonts
        self.iface = iface
        self.setWindowTitle("QGIS Dashboard")
        self.setWindowIcon(logo_icon())
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(1100, 720)

        self.bus = DashboardBus(iface, Theme.default(), self)

        # floating puck shown while minimized (replaces Qt's parented-window
        # minimize stub that pins itself over the QGIS status bar)
        self._bubble = None

        # tab bar + stack of pages
        self._pages = []
        self._tab_bar = QTabBar()
        self._tab_bar.setMovable(True)
        self._tab_bar.setExpanding(False)
        # Suppress the platform style's dark base line under the tabs; the
        # theme draws a single soft hairline (border-bottom) instead.
        self._tab_bar.setDrawBase(False)
        self._stack = QStackedWidget()

        # layout lock (view-only, not persisted): when on, tiles can't be
        # moved/resized. Off by default so the dashboard is editable on open.
        self._editing_locked = False

        # undo/redo over whole-dashboard snapshots (session-only, like zoom).
        # Recording is debounced so the many signals one edit fires — and the
        # slider drags of a live appearance edit — collapse into one entry; it
        # is suspended while a snapshot is being replayed so undo/redo can't
        # re-record themselves. Seeded once the first page exists.
        self._history = History()
        self._suspend_history = True
        self._history_timer = QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(120)
        self._history_timer.timeout.connect(self._record_history)

        # set when a dashboard is loaded/created while the window is hidden, so
        # the first show fits the export/print region to the viewport.
        self._needs_reframe = False

        # left icon rail + (tab strip over page stack)
        self._build_sidebar()
        pages_col = QWidget()
        col = QVBoxLayout(pages_col)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._build_tab_strip())
        col.addWidget(self._stack, 1)
        self._pages_col = pages_col

        # content area: a stack swapping between the Start screen (recent-
        # project cards) and the page canvas. The Start screen greets a project
        # that has no dashboard yet; the Home rail button returns to it.
        self._recent_store = RecentStore()
        self.start_view = StartView(self.bus.theme, self)
        self.start_view.continueRequested.connect(self.show_dashboard)
        self.start_view.newRequested.connect(self.new_dashboard)
        self.start_view.openFileRequested.connect(self.open_from_file)
        self.start_view.openRecentRequested.connect(self.open_file_path)
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self.start_view)   # index 0
        self._content_stack.addWidget(pages_col)         # index 1

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addWidget(self._content_stack, 1)
        self.setCentralWidget(container)

        # ArcGIS-style right-edge inspector that overlays the canvas. It hosts
        # the tile/header editors (Configure / Connections / appearance) one at
        # a time, opened only from a tile's right-click menu — never modal.
        self._inspector = InspectorPanel(self.bus.theme, container)
        # the Add-element picker is a matching slim panel docked on the LEFT,
        # flush against the rail; created lazily on first open.
        self._element_picker = None

        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabBarDoubleClicked.connect(self._rename_page_at)
        self._tab_bar.tabMoved.connect(self._on_tab_moved)
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.customContextMenuRequested.connect(self._tab_context_menu)

        self._build_status_bar()
        self._apply_window_style()

        # A freshly-constructed window holds one default page and shows the
        # canvas. The Start screen (recent-project cards) is driven by the
        # project lifecycle: load_from_project() shows it for a .qgz with no
        # dashboard, and the plugin shows it on New Project — so a brand-new
        # project greets the user with the cards, while an existing dashboard
        # opens straight to the canvas.
        self.add_page("Page 1")
        self.show_dashboard()

        # Keep config combos / map mirror fresh as project layers change.
        # These live on the long-lived QgsProject singleton, which OUTLIVES this
        # window — so connect a bound method (PyQt auto-disconnects it when the
        # window is destroyed) rather than a lambda (never auto-disconnected,
        # leaving a dangling call into a deleted DashboardBus). cleanup() also
        # drops them explicitly on plugin unload. See _on_project_layers_changed.
        QgsProject.instance().layersAdded.connect(self._on_project_layers_changed)
        QgsProject.instance().layersRemoved.connect(self._on_project_layers_changed)
        self.bus.filtersChanged.connect(self._update_filter_label)
        self.bus.filtersCleared.connect(self._update_filter_label)
        self.bus.themeChanged.connect(self._on_theme_changed)

        # persisted, non-geometry mutations also feed the undo timeline (tile
        # geometry/add/remove come in via each canvas.layoutChanged, wired in
        # add_page). filtersChanged is deliberately NOT recorded — live
        # cross-filter selection is not part of the saved layout.
        self.bus.themeChanged.connect(self._schedule_history)
        self.bus.connectionsChanged.connect(self._schedule_history)

        # Window-wide undo/redo shortcuts (the rail buttons mirror these).
        self._add_shortcut("Ctrl+Z", self.undo)
        self._add_shortcut("Ctrl+Y", self.redo)
        self._add_shortcut("Ctrl+Shift+Z", self.redo)

        # seed the timeline from the initial blank dashboard and enable signals
        self._reset_history()

    # ---- chrome ----

    def _build_sidebar(self):
        """Vertical icon rail replacing the old horizontal toolbar."""
        self.sidebar = Sidebar(self.bus.theme, self)
        self.sidebar.add_action(
            "home", "Home — recent dashboards", self.show_start)
        self.sidebar.add_separator()
        self._add_element_btn = self.sidebar.add_action(
            "add_element", "Add element", self.open_element_picker)
        self.sidebar.add_action(
            "add_page", "Add page", self._add_page_interactive)
        self.sidebar.add_separator()
        self._undo_btn = self.sidebar.add_action(
            "undo", "Undo (Ctrl+Z)", self.undo)
        self._redo_btn = self.sidebar.add_action(
            "redo", "Redo (Ctrl+Y)", self.redo)
        self.sidebar.add_separator()
        self.sidebar.add_action("zoom_in", "Zoom in", self._zoom_in)
        self.sidebar.add_action(
            "zoom_out", "Zoom out", self._zoom_out)
        self.sidebar.add_action(
            "zoom_reset", "Reset zoom (100%)", self._zoom_reset)
        self.sidebar.add_action(
            "auto_arrange", "Auto-arrange — fit tiles to page",
            self.auto_arrange)
        self.sidebar.add_stretch()
        self.sidebar.add_action(
            "clear_filter", "Clear filter", self.bus.clear_all_filters)
        self.sidebar.add_separator()
        # Save + the Settings hub (Appearance, About) live at the foot of the rail.
        self.sidebar.add_action(
            "save", "Save dashboard to a file", self.save_to_file)
        self.sidebar.add_action("settings", "Settings", self.open_settings)

    def _build_tab_strip(self):
        """The page tab bar plus right-aligned lock + export buttons.

        Lives in one row that carries the soft bottom hairline; the tab bar
        stretches and the action buttons sit at the right edge.
        """
        strip = QFrame()
        strip.setObjectName("dashTabStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(4)
        row.addWidget(self._tab_bar, 1)

        self._lock_btn = self._make_strip_button(
            "unlock", "Lock layout — prevent moving/resizing tiles",
            checkable=True)
        self._lock_btn.toggled.connect(self._on_lock_toggled)
        row.addWidget(self._lock_btn)

        self._export_btn = self._make_strip_button(
            "export", "Export dashboard (HTML / PNG / PDF)")
        self._export_btn.clicked.connect(self._open_export_menu)
        row.addWidget(self._export_btn)
        return strip

    def _make_strip_button(self, icon_name, tooltip, checkable=False):
        btn = QToolButton()
        btn.setObjectName("dashRailButton")   # reuse the rail's themed hover/focus
        btn.setIcon(monochrome_icon(icon_name, CHROME["muted"]))
        btn.setIconSize(QSize(18, 18))
        btn.setFixedSize(30, 28)
        btn.setAutoRaise(True)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        return btn

    def _on_lock_toggled(self, locked):
        self._set_editing_locked(locked, update_button=False)

    def _set_editing_locked(self, locked, *, update_button=True):
        """Switch the whole dashboard between Build (unlocked) and Use (locked).

        Build mode = tiles move/resize/configure, contents inert; Use mode =
        geometry fixed, contents interactive (chart click → filter, map pan /
        identify / fly-to). ``update_button`` keeps the toggle in sync when the
        mode is applied programmatically (e.g. restored from a saved file).
        """
        self._editing_locked = bool(locked)
        if update_button:
            self._lock_btn.blockSignals(True)
            self._lock_btn.setChecked(self._editing_locked)
            self._lock_btn.blockSignals(False)
        self._lock_btn.setIcon(monochrome_icon(
            "lock" if self._editing_locked else "unlock", CHROME["muted"]))
        self._lock_btn.setToolTip(
            "Unlock to edit — currently in Use mode (tiles fixed, interactive)"
            if self._editing_locked
            else "Lock to use — currently in Build mode (move/resize/configure)")
        for page in self._pages:
            page.canvas.set_locked(self._editing_locked)
        self._schedule_history()   # the Build/Use lock is persisted (suspended on load)

    def _open_export_menu(self):
        menu = QMenu(self)
        menu.addAction("Export to HTML").triggered.connect(self.export_to_html)
        menu.addAction("Export to PNG").triggered.connect(self.export_to_png)
        menu.addAction("Export to PDF").triggered.connect(self.export_to_pdf)
        menu.addSeparator()
        menu.addAction("Publish to public…").triggered.connect(
            self.publish_to_public)
        menu.exec(self._export_btn.mapToGlobal(
            self._export_btn.rect().bottomLeft()))

    def _build_status_bar(self):
        """Bottom status strip carrying the live cross-filter indicator."""
        bar = self.statusBar()
        self._filter_dot = QFrame()
        self._filter_dot.setObjectName("dashFilterDot")
        self._filter_dot.setFixedSize(8, 8)
        self._filter_dot.hide()
        self.filter_label = QLabel("No active filter")
        self.filter_label.setObjectName("dashFilterStatus")
        bar.addWidget(self._filter_dot)
        bar.addWidget(self.filter_label)

    # ---- zoom helpers (act on the current page's view) ----

    def _zoom_in(self):
        view = self.current_view()
        if view is not None:
            view.zoom_in()

    def _zoom_out(self):
        view = self.current_view()
        if view is not None:
            view.zoom_out()

    def _zoom_reset(self):
        view = self.current_view()
        if view is not None:
            view.reset_zoom()

    def auto_arrange(self):
        """One-click rearrange: fill every page's canvas with no gaps.

        Reflows each page through the pure
        :func:`auto_layout.compute_auto_layout`, honoring per-element shape
        biases (indicators equal & adjacent, map biggest, charts shaped by
        type, lists portrait) while tiling the canvas region edge to edge.
        The whole multi-page rearrange is one debounced undo step.
        """
        for page in self._pages:
            canvas = page.canvas
            tiles = canvas.tiles()
            if not tiles:
                continue
            items = [(t.element.type_name,
                      t.element.config.get("chart_type")) for t in tiles]
            rects = compute_auto_layout(items, *canvas.content_size())
            for t, rect in zip(tiles, rects):
                t.x_px, t.y_px, t.w_px, t.h_px = rect
                t._prev = rect            # so a later drag reverts to here
            canvas.reflow()
            canvas.sync_size()
            canvas.layoutChanged.emit()   # persists + schedules one undo step

    def _reframe_current(self):
        """Fit the current page's export/print region to the viewport."""
        view = self.current_view()
        if view is not None:
            view.reset_zoom()

    def _schedule_reframe(self):
        """Reframe the page now (if shown) or on the next show (if hidden).

        Deferred a tick so the viewport has its final size before fitting.
        """
        if self.isVisible():
            QTimer.singleShot(0, self._reframe_current)
        else:
            self._needs_reframe = True

    def showEvent(self, e):
        super().showEvent(e)
        if self._needs_reframe:
            self._needs_reframe = False
            QTimer.singleShot(0, self._reframe_current)

    def _apply_window_style(self):
        self.setStyleSheet(self.bus.theme.window_qss())
        cur = self.current_canvas()
        if cur is not None:
            cur.update()

    def _on_theme_changed(self):
        self.sidebar.apply_theme(self.bus.theme)
        self.start_view.apply_theme(self.bus.theme)
        self._inspector.apply_theme(self.bus.theme)
        if self._element_picker is not None:
            self._element_picker.apply_theme(self.bus.theme)
        self._apply_window_style()
        # The tab-strip buttons are chrome — keep them at the fixed CHROME tint
        # (a theme change must not recolor them).
        self._lock_btn.setIcon(monochrome_icon(
            "lock" if self._editing_locked else "unlock", CHROME["muted"]))
        self._export_btn.setIcon(monochrome_icon("export", CHROME["muted"]))

    def _update_filter_label(self):
        n = self.bus.active_filter_count()
        self.filter_label.setText(
            "No active filter" if n == 0 else "Filters active: {}".format(n))
        self._filter_dot.setVisible(n > 0)

    # ---- start screen / view switching ----

    def show_start(self):
        """Show the Start screen (recent-project cards) in the canvas area."""
        self.start_view.set_can_continue(bool(self._pages))
        self.start_view.set_recents(self._recent_store.load_recents())
        self._content_stack.setCurrentWidget(self.start_view)
        self._update_history_buttons()   # undo/redo don't apply on the Start screen

    def show_dashboard(self):
        """Show the page canvas, leaving the Start screen."""
        if not self._pages:
            return   # nothing to show yet — stay on the Start screen
        self._content_stack.setCurrentWidget(self._pages_col)
        self._update_history_buttons()

    # ---- undo / redo (whole-dashboard snapshot timeline) ----

    def _add_shortcut(self, sequence, slot):
        sc = QShortcut(QKeySequence(sequence), self)
        sc.activated.connect(slot)
        return sc

    def _snapshot(self):
        """A normalized deep copy of the current layout for the history stack."""
        return copy.deepcopy(self._build_layout_dict())

    def _schedule_history(self, *args):
        """Queue a (debounced) history record after the current edit settles."""
        if self._suspend_history:
            return
        self._history_timer.start()

    def _record_history(self):
        """Commit the current dashboard state as a new timeline entry."""
        if self._suspend_history or not self._pages:
            return
        if self._history.record(self._snapshot()):
            self._update_history_buttons()

    def _reset_history(self):
        """Re-seed the timeline from the current dashboard (load / new / boot).

        Clears the undo/redo stacks: a freshly loaded or created dashboard
        starts a brand-new timeline. Also (re)enables recording.
        """
        self._history_timer.stop()
        self._history = History(self._snapshot() if self._pages else None)
        self._suspend_history = False
        self._update_history_buttons()

    def _history_active(self):
        """Undo/redo only act on a shown dashboard, never mid-rebuild.

        Gating here (not just on button state) matters because the keyboard
        shortcuts fire regardless of the rail buttons — so without this, Ctrl+Z
        on the Start screen would pop a state off the stack without applying it.
        """
        return (not self._suspend_history and bool(self._pages)
                and self._content_stack.currentWidget() is self._pages_col)

    def _update_history_buttons(self):
        on_dash = bool(self._pages) and \
            self._content_stack.currentWidget() is self._pages_col
        if getattr(self, "_undo_btn", None) is not None:
            self._undo_btn.setEnabled(on_dash and self._history.can_undo())
        if getattr(self, "_redo_btn", None) is not None:
            self._redo_btn.setEnabled(on_dash and self._history.can_redo())

    def undo(self):
        if self._history_active():
            self._apply_history(self._history.undo())

    def redo(self):
        if self._history_active():
            self._apply_history(self._history.redo())

    def _apply_history(self, snapshot):
        """Replay *snapshot* (from undo/redo) without disturbing the timeline."""
        if snapshot is None or not self._pages:
            return
        self._suspend_history = True
        try:
            self._apply_layout_dict(snapshot)
            self.show_dashboard()
        finally:
            # cancel any record the rebuild's signals queued, then re-arm
            self._history_timer.stop()
            self._suspend_history = False
        self._update_history_buttons()

    def new_dashboard(self):
        """Create a fresh, blank dashboard (one page) and show it."""
        if not self._confirm_replace():
            return
        self.clear_all()
        self.bus.set_theme(Theme.default())
        self._apply_window_style()
        self.add_page("Page 1")
        self._apply_grid_to_all(DEFAULT_COLS, DEFAULT_ROWS)
        self._set_editing_locked(False)   # a blank dashboard opens in Build mode
        self.show_dashboard()
        self._schedule_reframe()
        self._reset_history()             # fresh dashboard → fresh timeline

    # ---- standalone .qdash save / open ----

    def save_to_file(self):
        """Write the whole dashboard to a portable ``.qdash`` file."""
        if not self._pages:
            QMessageBox.information(
                self, "Nothing to save",
                "Create a dashboard first (New Dashboard), then save it.")
            return
        cur = self.current_page()
        suggested = os.path.join(
            self._recent_store.default_directory(),
            project_io.ensure_suffix(cur.title if cur else "dashboard"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save dashboard", suggested, project_io.QDASH_FILTER)
        if not path:
            return
        try:
            data = self._build_layout_dict()
            fonts = self._collect_embedded_fonts()
            if fonts:
                data["fonts"] = fonts
            final = project_io.write_layout_file(path, data)
        except OSError as exc:
            QMessageBox.critical(
                self, "Save failed",
                "Could not save the dashboard:\n{}".format(exc))
            return
        self._recent_store.record(final, project_io.display_name(final))
        self._recent_store.remember_dir(final)
        self.statusBar().showMessage("Saved dashboard to {}".format(final), 5000)

    def open_from_file(self):
        """Pick a ``.qdash`` file from disk and open it."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open dashboard", self._recent_store.default_directory(),
            project_io.QDASH_FILTER)
        if path:
            self.open_file_path(path)

    def open_file_path(self, path):
        """Load a ``.qdash`` file at *path* (used by recent cards too)."""
        if not self._confirm_replace():
            return
        try:
            data = migrate_layout(project_io.read_layout_file(path))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self, "Open failed",
                "Could not open this dashboard file:\n{}".format(exc))
            return
        self._apply_layout_dict(data)
        self.show_dashboard()
        self._reset_history()             # opened dashboard → fresh timeline
        self._recent_store.record(path, project_io.display_name(path))

    def _confirm_replace(self):
        """Confirm before discarding a dashboard that currently has tiles."""
        if not any(p.canvas.tiles() for p in self._pages):
            return True
        ans = QMessageBox.question(
            self, "Open dashboard",
            "Opening a dashboard replaces the one currently loaded. Continue?")
        return ans == QMessageBox.StandardButton.Yes

    # ---- pages ----

    def pages(self):
        return list(self._pages)

    def current_page(self):
        idx = self._tab_bar.currentIndex()
        return self._pages[idx] if 0 <= idx < len(self._pages) else None

    def current_canvas(self):
        page = self.current_page()
        return page.canvas if page else None

    def current_view(self):
        page = self.current_page()
        return page.view if page else None

    def canvas_cols(self):
        return self._pages[0].canvas.cols if self._pages else DEFAULT_COLS

    def canvas_rows(self):
        return self._pages[0].canvas.rows if self._pages else DEFAULT_ROWS

    def canvas_gap(self):
        return self._pages[0].canvas.gap if self._pages else DEFAULT_GAP

    def canvas_size(self):
        """The global export/print region ``(w, h)`` (logical px)."""
        if self._pages:
            return self._pages[0].canvas.region_size()
        return (DEFAULT_CANVAS_W, DEFAULT_CANVAS_H)

    def add_page(self, title, page_id=None, make_active=True):
        page_id = page_id or uuid.uuid4().hex[:8]
        canvas = DashboardCanvas(self.bus, self.canvas_cols(), self.canvas_rows())
        canvas.set_locked(self._editing_locked)   # honour the current layout lock
        canvas.set_gap(self.canvas_gap())          # honour the current element gap
        canvas.set_region(*self.canvas_size())     # honour the current page size
        # tile move/resize/add/remove on this page feeds the undo timeline
        canvas.layoutChanged.connect(self._schedule_history)
        view = PageView(canvas)
        page = DashboardPage(page_id, title, view)
        self._pages.append(page)
        self._stack.addWidget(view)
        self._tab_bar.addTab(title)
        if make_active:
            self._tab_bar.setCurrentIndex(len(self._pages) - 1)
        self._update_tabbar_visibility()
        return page

    def delete_page(self, page_id):
        if len(self._pages) <= 1:
            return
        idx = next((i for i, p in enumerate(self._pages)
                    if p.id == page_id), -1)
        if idx < 0:
            return
        page = self._pages[idx]
        if page.canvas.tiles():
            ok = QMessageBox.question(
                self, "Delete page",
                'Delete "{}" and its {} tile(s)?'.format(
                    page.title, len(page.canvas.tiles())))
            if ok != QMessageBox.StandardButton.Yes:
                return
        page.canvas.clear()
        self.bus.forget_page(page.id)
        self._pages.pop(idx)
        self._stack.removeWidget(page.view)
        page.view.deleteLater()
        self._tab_bar.removeTab(idx)
        self._update_tabbar_visibility()
        self._schedule_history()

    def _update_tabbar_visibility(self):
        """Keep the page tab bar visible whenever there's at least one page.

        The tab bar is the place to rename (double-click / right-click) and
        delete pages, so it stays visible even for a single-page dashboard —
        otherwise that page could never be renamed.
        """
        self._tab_bar.setVisible(len(self._pages) >= 1)

    def _add_page_interactive(self):
        self.add_page("Page {}".format(len(self._pages) + 1))
        self._schedule_history()

    def _on_tab_changed(self, idx):
        # an open editor belongs to the page being left — keep its live edits
        if getattr(self, "_inspector", None) is not None:
            self._inspector.close_active(commit=True)
        if 0 <= idx < len(self._pages):
            page = self._pages[idx]
            self._stack.setCurrentWidget(page.view)
            self.bus.set_active_page(page.id)

    def _on_tab_moved(self, frm, to):
        self._pages.insert(to, self._pages.pop(frm))
        view = self._stack.widget(frm)
        self._stack.removeWidget(view)
        self._stack.insertWidget(to, view)
        self._schedule_history()

    def _rename_page_at(self, idx):
        if not (0 <= idx < len(self._pages)):
            return
        page = self._pages[idx]
        text, ok = QInputDialog.getText(self, "Rename page",
                                        "Title:", text=page.title)
        if ok and text.strip():
            page.title = text.strip()
            self._tab_bar.setTabText(idx, page.title)
            self._schedule_history()

    def _tab_context_menu(self, pos):
        idx = self._tab_bar.tabAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)
        menu.addAction("Rename").triggered.connect(
            lambda: self._rename_page_at(idx))
        menu.addAction("Delete").triggered.connect(
            lambda: self.delete_page(self._pages[idx].id))
        menu.exec(self._tab_bar.mapToGlobal(pos))

    def _apply_grid_to_all(self, cols, rows):
        for page in self._pages:
            page.canvas.set_grid(cols, rows)

    def _apply_gap_to_all(self, gap):
        for page in self._pages:
            page.canvas.set_gap(int(gap))

    # ---- element management ----

    def elements(self):
        page = self.current_page()
        return [t.element for t in page.canvas.tiles()] if page else []

    def open_element_picker(self):
        """Toggle the Add-element picker — a slim panel docked flush to the
        right of the rail.

        The picker chooses *only* the element type (AGOL Experience-Builder
        style); the tile is added with sensible defaults and configured
        afterward from its right-click ``Configure…`` menu (in the inspector).
        """
        if self._element_picker is None:
            self._element_picker = ElementPicker(self.bus.theme,
                                                 self.centralWidget())
            self._element_picker.elementChosen.connect(self._on_element_chosen)
        self._element_picker.open_beside(self.sidebar)

    def _on_element_chosen(self, type_name):
        # Adding a tile is a Build-mode action: drop the lock so the new tile is
        # movable/configurable rather than landing fixed-and-interactive.
        if self._editing_locked:
            self._set_editing_locked(False)
        if type_name == "header":
            # the title doubles as the banner text — start blank to configure
            config = {"title": ""}
        else:
            # seed a friendly default title
            config = {"title": ELEMENT_LABELS.get(type_name, type_name.title())}
        self.add_element(type_name, config)

    def add_element(self, type_name, config, grid_rect=None):
        page = self.current_page()
        if page is None:
            page = self.add_page("Page 1")
        return self._add_element_to(page, type_name, config, grid_rect)

    def _add_element_to(self, page, type_name, config, grid_rect=None):
        element = create_element(type_name, self.bus, config, page.canvas)
        tile = page.canvas.add_tile(element, grid_rect)
        tile.styleRequested.connect(self._edit_tile_style)
        tile.connectionsRequested.connect(self._edit_tile_connections)
        tile.configureRequested.connect(self._edit_tile_config)
        # if this tile is removed while the inspector edits it, drop the panel
        # without running its callbacks (the element is being destroyed)
        tile.closeRequested.connect(self._inspector.discard_if_subject)
        return tile

    def _edit_tile_config(self, element):
        """Edit the per-type config of a live tile in the inspector panel.

        Edits preview live (debounced): managed keys are replaced wholesale (a
        cleared field drops its key) while unmanaged keys — id, per-tile style
        override, base_filter — are kept. Cancel restores the original config.
        """
        original = dict(element.config)
        form = ElementConfigForm(element=element)

        def do_apply():
            _type, cfg = form.result_config()
            new_config = dict(element.config)
            for key in form.managed_keys():
                if key in cfg:
                    new_config[key] = cfg[key]
                else:
                    new_config.pop(key, None)
            new_config["id"] = element.id
            element.config = new_config
            element.reconfigure()

        debounce = self._make_debounce(do_apply)
        form.changed.connect(lambda: debounce.start())

        def commit():
            debounce.stop()
            do_apply()
            self._schedule_history()

        def cancel():
            debounce.stop()
            element.config = original
            element.reconfigure()
            self._schedule_history()   # reverts to baseline → deduped to a no-op

        self._inspector.open_editor(
            "Configure — {}".format(element.display_name()),
            form, on_commit=commit, on_cancel=cancel, subject=element)

    def _edit_tile_style(self, element):
        """Edit one tile's appearance override in the inspector, live.

        The schema-driven :class:`TileStyleForm` shows only the roles the
        element type has; it writes a **sparse** override (only fields changed
        from the global theme) to ``config["style"]`` and edits the tile's pixel
        size separately. Cancel restores both the style override and the size.
        """
        style = element.config.get("style")
        original = dict(style) if isinstance(style, dict) else None
        tile = getattr(element, "_grid_tile", None)
        original_size = tile.grid_rect()[2:4] if tile is not None else None
        form = TileStyleForm(element, self.bus.theme)

        def live():
            if form.is_cleared():
                element.config.pop("style", None)
            else:
                override = form.result_override()
                if override:
                    element.config["style"] = override
                else:
                    element.config.pop("style", None)
            element.apply_theme()
            size = form.tile_size()
            if size is not None and tile is not None:
                tile.set_size_px(size[0], size[1])

        form.changed.connect(live)

        def commit():
            live()
            self._schedule_history()

        def cancel():
            if original is not None:
                element.config["style"] = original
            else:
                element.config.pop("style", None)
            element.apply_theme()
            if original_size is not None and tile is not None:
                tile.set_size_px(original_size[0], original_size[1])
            self._schedule_history()   # reverts to baseline → deduped to a no-op

        self._inspector.open_editor(
            "Tile appearance — {}".format(element.display_name()),
            form, on_commit=commit, on_cancel=cancel, subject=element)

    def _make_debounce(self, fn, msec=160):
        """A single-shot QTimer that runs *fn* shortly after the last start()."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(msec)
        timer.timeout.connect(fn)
        return timer

    # ---- dialogs ----

    def _edit_tile_connections(self, element):
        """Edit one tile's cross-filter links in the inspector, live.

        Each ticked edge wires immediately so the dashboard previews the
        cross-filter; Cancel restores the page's connection graph snapshot.
        """
        page = self.current_page()
        pid = page.id if page else None
        snapshot = self.bus.connections_to_dict(pid)
        form = ConnectionsForm(self.bus, element, self.elements(), live=True)

        def cancel():
            self.bus.load_connections(snapshot, pid)
            self.bus.filtersChanged.emit()   # targets recompute their filter

        self._inspector.open_editor(
            "Connections — {}".format(element.display_name()),
            form, on_commit=None, on_cancel=cancel, subject=element)

    def open_settings(self):
        # Export now lives on the tab strip, not in Settings. Settings holds the
        # global controls: the *Themes* editor (canvas colors + fonts) embedded
        # inline, and the *Layout* page (corner radius, element spacing, text
        # sizes) — all applied live via the callbacks below.
        panel = SettingsPanel(self, theme=self.bus.theme,
                              on_appearance=self._apply_global_theme,
                              on_radius=self._set_global_radius,
                              on_gap=self._set_global_gap,
                              on_size=self._set_global_text_size,
                              on_canvas_size=self._set_canvas_size,
                              on_opacity=self._set_global_opacity,
                              on_border_width=self._set_global_border_width,
                              on_border_color=self._set_global_border_color,
                              gap=self.canvas_gap(),
                              canvas_size=self.canvas_size())
        # Settings is hosted in the right inspector panel (not a floating dialog)
        # so it never covers the canvas and theme/font/layout edits preview live
        # behind it. It applies live, so the footer is hidden (the ✕ closes it)
        # and the panel opens a bit wider than a tile editor. Recording is paused
        # while it's open so the whole session collapses into one undo step.
        was_suspended = self._suspend_history
        self._suspend_history = True

        def finalize():
            self._suspend_history = was_suspended
            self._schedule_history()

        self._inspector.open_editor(
            "Settings", panel, on_commit=finalize, on_cancel=finalize,
            footer=False, width=460)

    def _apply_global_theme(self, theme):
        """Apply a theme from the *Themes* editor (canvas colors + fonts).

        The editor rebuilds its Theme from an open-time snapshot, so the
        Layout-owned metrics (text sizes, corner radius, border + transparency)
        it carries may be stale; preserve the *live* ones so editing a color
        never reverts a size/radius/border the user just changed on Layout.
        """
        live = self.bus.theme
        self.bus.set_theme(theme.with_values(
            font_size=live.font_size, title_size=live.title_size,
            value_size=live.value_size, radius=live.radius,
            border=live.border, border_width=live.border_width,
            tile_opacity=live.tile_opacity))

    def _set_global_radius(self, value):
        """Live-apply a new global corner radius to every dashboard element."""
        self.bus.set_theme(self.bus.theme.with_values(radius=int(value)))

    def _set_global_opacity(self, value):
        """Live-apply element transparency (tiles, charts, tables) globally."""
        self.bus.set_theme(self.bus.theme.with_values(tile_opacity=int(value)))

    def _set_global_border_width(self, value):
        """Live-apply the global tile border thickness."""
        self.bus.set_theme(self.bus.theme.with_values(border_width=int(value)))

    def _set_global_border_color(self, hex_color):
        """Live-apply the global tile border color."""
        self.bus.set_theme(self.bus.theme.with_values(border=hex_color))

    def _set_global_text_size(self, key, value):
        """Live-apply a text-size change (font_size/title_size/value_size)."""
        if key in ("font_size", "title_size", "value_size"):
            self.bus.set_theme(self.bus.theme.with_values(**{key: int(value)}))

    def _set_global_gap(self, value):
        """Live-apply a new global element gap (spacing) to every page."""
        self._apply_gap_to_all(int(value))

    def _set_canvas_size(self, w, h):
        """Live-apply a new global export/print region to every page.

        Resizes every page's region, **scaling every tile to match** so the
        whole layout stays responsive (each tile keeps its aspect ratio), then
        reframes the current view so the user immediately sees the new page
        outline fit to the viewport.
        """
        for page in self._pages:
            page.canvas.set_region_scaled(int(w), int(h))
        view = self.current_view()
        if view is not None:
            view.reset_zoom()                  # reframe + re-sync the current one

    def export_to_html(self):
        from .export_dialog import prompt_and_export
        prompt_and_export(self, self)

    def export_to_png(self):
        from .export.raster_export import export_png
        export_png(self, self)

    def export_to_pdf(self):
        from .export.raster_export import export_pdf
        export_pdf(self, self)

    def publish_to_public(self):
        from .publish_dialog import PublishDialog
        PublishDialog(self, self).exec()

    # ---- lifecycle ----

    def _ensure_bubble(self):
        if self._bubble is None:
            # parent to the QGIS main window, NOT to self: a child top-level
            # window hides when its parent hides, but the puck must stay visible
            # precisely while the dashboard window is hidden.
            self._bubble = MinimizedBubble(self.iface.mainWindow())
            self._bubble.restoreRequested.connect(self.restore_from_bubble)
        return self._bubble

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # keep the overlay inspector pinned to the right edge of the canvas
        if getattr(self, "_inspector", None) is not None:
            self._inspector.reposition()
        # and the Add-element picker flush against the rail (while open)
        if getattr(self, "_element_picker", None) is not None \
                and self._element_picker.isVisible():
            self._element_picker.reposition(self.sidebar)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                # Defer past the state-change machinery, then swap the window
                # for the floating puck.
                QTimer.singleShot(0, self._collapse_to_bubble)

    def _collapse_to_bubble(self):
        # Clear the minimized bit so a later plain show()/restore is clean.
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.hide()
        self._ensure_bubble().show_at_corner()

    def restore_from_bubble(self):
        if self._bubble is not None:
            self._bubble.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_all(self):
        """Hide the window and the floating puck (toolbar toggled off)."""
        if self._bubble is not None:
            self._bubble.hide()
        self.hide()

    def hideEvent(self, event):
        # Whenever the window is hidden (toolbar toggle, close), drop the puck.
        # During _collapse_to_bubble the puck is (re)shown *after* this hide(),
        # so the two don't fight.
        if self._bubble is not None:
            self._bubble.hide()
        super().hideEvent(event)

    def closeEvent(self, event):
        # Hide rather than destroy so state survives a reopen; tell the plugin
        # so it can untick the toolbar action.
        self.closed.emit()
        if self._bubble is not None:
            self._bubble.deleteLater()
            self._bubble = None
        super().closeEvent(event)

    def clear_all(self):
        # pause history while the dashboard is torn down/rebuilt; the rebuild's
        # caller re-seeds the timeline (load/new) or undo/redo re-arms it.
        self._suspend_history = True
        # discard any open editor before its subject tiles are destroyed
        if getattr(self, "_inspector", None) is not None:
            self._inspector.close_active(commit=False)
        for page in self._pages:
            page.canvas.clear()
            self._stack.removeWidget(page.view)
            page.view.deleteLater()
        self._pages = []
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._update_tabbar_visibility()
        self.bus.clear_all_filters()

    # ---- serialization (shared by .qgz embedding and .qdash files) ----

    def _build_layout_dict(self):
        """Serialize the whole dashboard to the v3 layout dict.

        Used by both :meth:`save_to_project` (writes it into the ``.qgz``) and
        :meth:`save_to_file` (writes it to a portable ``.qdash`` file).
        """
        pages = []
        for page in self._pages:
            elements = []
            for tile in page.canvas.tiles():
                d = tile.element.to_dict()
                gx, gy, gw, gh = tile.grid_rect()
                d["grid"] = {"x": gx, "y": gy, "w": gw, "h": gh}
                elements.append(d)
            page_data = {
                "id": page.id,
                "title": page.title,
                "connections": self.bus.connections_to_dict(page.id),
                "elements": elements,
            }
            pages.append(page_data)
        cur = self.current_page()
        cw, ch = self.canvas_size()
        data = {
            "version": 3,
            "grid": {"cols": self.canvas_cols(), "rows": self.canvas_rows()},
            "gap": self.canvas_gap(),
            "canvas": {"w": cw, "h": ch},
            "theme": self.bus.theme.to_dict(),
            "window": {"w": self.width(), "h": self.height()},
            "locked": bool(self._editing_locked),
            "active_page": cur.id if cur else None,
            "pages": pages,
        }
        return data

    def _collect_embedded_fonts(self):
        """Base64-embed the custom fonts referenced by the current dashboard.

        Used by the ``.qdash`` save (and mirrored by the HTML export): collect
        the families used by the global theme and every tile override, keep only
        the ones installed as user fonts, and return their embeddable payloads
        so a shared dashboard renders — and installs the font — on another PC.
        Returns ``[]`` when no custom font is in use.
        """
        styles = []
        for page in self._pages:
            for tile in page.canvas.tiles():
                style = tile.element.config.get("style")
                if isinstance(style, dict):
                    styles.append(style)
        names = referenced_families(self.bus.theme.to_dict(), styles)
        custom = names & set(user_fonts.custom_families())
        return user_fonts.embedded_payload(sorted(custom))

    @staticmethod
    def _resolve_canvas_size(data):
        """The export/print region for a layout dict.

        Uses the stored ``canvas`` when present; otherwise (older blobs with no
        region) derives it from the content bounding box across all pages so the
        export keeps its previous extent, rounded up to a tidy step. Falls back
        to the default when the dashboard has no tiles.
        """
        cv = data.get("canvas")
        if isinstance(cv, dict) and cv.get("w") and cv.get("h"):
            return (int(cv["w"]), int(cv["h"]))
        max_r = max_b = 0
        for p in data.get("pages", []):
            for cfg in p.get("elements", []):
                g = cfg.get("grid")
                if isinstance(g, dict) and all(k in g for k in ("x", "y", "w", "h")):
                    max_r = max(max_r, g["x"] + g["w"])
                    max_b = max(max_b, g["y"] + g["h"])
        if max_r <= 0 or max_b <= 0:
            return (DEFAULT_CANVAS_W, DEFAULT_CANVAS_H)

        def round_up(v):
            step = CANVAS_SIZE_STEP
            return ((int(v) + CANVAS_MARGIN + step - 1) // step) * step

        return (round_up(max_r), round_up(max_b))

    def _apply_layout_dict(self, data):
        """Rebuild the whole dashboard from a migrated v3 layout dict.

        Self-contained: clears any current dashboard first, so it serves both
        the ``.qgz`` load and opening a ``.qdash`` file (replacing the current
        dashboard).
        """
        self.clear_all()
        # Install any fonts the dashboard carries (a shared .qdash) BEFORE the
        # theme is applied, so referenced custom families resolve. A .qgz blob
        # has no "fonts" key, so this is a no-op there.
        user_fonts.install_embedded(data.get("fonts"))
        self.bus.set_theme(Theme.from_dict(data.get("theme")))
        self._apply_window_style()
        grid = data.get("grid", {})
        cols = grid.get("cols", DEFAULT_COLS)
        rows = grid.get("rows", DEFAULT_ROWS)
        gap = int(data.get("gap", DEFAULT_GAP))
        region_w, region_h = self._resolve_canvas_size(data)
        # legacy docked headers (top-level global + per-page) become header
        # tiles in each page; the region grows uniformly to include the band
        src_pages, region_w, region_h = materialize_header_tiles(
            data["pages"], data.get("header"), region_w, region_h)

        for p in src_pages:
            page = self.add_page(p["title"], page_id=p["id"], make_active=False)
            page.canvas.set_grid(cols, rows)
            page.canvas.set_gap(gap)
            page.canvas.set_region(region_w, region_h)
            self.bus.load_connections(p.get("connections", {}), p["id"])
            for cfg in p.get("elements", []):
                cfg = dict(cfg)
                t = cfg.pop("__type__", None)
                g = cfg.pop("grid", None)
                rect = None
                # placement is a logical pixel rect; only honour it when fully
                # specified, otherwise let the canvas auto-place (first-free)
                if isinstance(g, dict) and all(
                        k in g for k in ("x", "y", "w", "h")):
                    rect = (g["x"], g["y"], g["w"], g["h"])
                if t:
                    self._add_element_to(page, t, cfg, rect)
            # legacy/implicit edges into a map keep the classic filter+zoom+flash
            # bundle so older dashboards fly-to as before; explicit action edges
            # (newer blobs) are left untouched.
            map_ids = [c.get("id") for c in p.get("elements", [])
                       if c.get("__type__") == "map" and c.get("id")]
            if map_ids:
                self.bus.upgrade_legacy_map_edges(p["id"], map_ids)

        active = data.get("active_page")
        idx = next((i for i, pg in enumerate(self._pages)
                    if pg.id == active), 0)
        self._tab_bar.setCurrentIndex(idx)

        win = data.get("window", {})
        if win.get("w") and win.get("h"):
            self.resize(int(win["w"]), int(win["h"]))

        # restore Build/Use mode (and sync the toggle); fans out to every tile
        # and header so contents become interactive iff the dashboard was saved
        # locked (or, for older blobs, defaults to Use mode when it has tiles).
        self._set_editing_locked(bool(data.get("locked")), update_button=True)

        self._schedule_reframe()   # fit the loaded page to the viewport

    # ---- project-wide signal wiring (QgsProject singleton) ----

    def _on_project_layers_changed(self, *args):
        """Project layers were added/removed — refresh layer-bound widgets.

        A plain method (not a lambda) on purpose: connected to the long-lived
        ``QgsProject`` singleton, it is auto-disconnected by PyQt when this
        window is destroyed, so a later add/remove can't fire into a deleted
        :class:`DashboardBus`.

        It is *also* guarded against a stale connection that outlived its
        objects: if a previous plugin build/reload left this slot wired to
        ``QgsProject`` but the owning window (and its child bus) were since torn
        down, adding a layer would otherwise raise ``RuntimeError: wrapped C/C++
        object of type DashboardBus has been deleted``. When that is detected we
        self-disconnect so the dead wiring stops firing.
        """
        if sip.isdeleted(self) or sip.isdeleted(self.bus):
            try:
                proj = QgsProject.instance()
                proj.layersAdded.disconnect(self._on_project_layers_changed)
                proj.layersRemoved.disconnect(self._on_project_layers_changed)
            except (TypeError, RuntimeError):
                pass
            return
        self.bus.layersChanged.emit()

    def cleanup(self):
        """Drop connections to the long-lived ``QgsProject`` singleton.

        Called by the plugin's ``unload()`` before the window is deleted. PyQt
        would auto-disconnect these on destruction anyway (they use a bound
        method), but disconnecting eagerly closes the window between
        ``deleteLater()`` and actual deletion where a layer change could still
        arrive.
        """
        proj = QgsProject.instance()
        for signal in (proj.layersAdded, proj.layersRemoved):
            try:
                signal.disconnect(self._on_project_layers_changed)
            except (TypeError, RuntimeError):
                pass

    # ---- persistence into the .qgz project ----

    def save_to_project(self):
        # No dashboard built yet (still on the Start screen): leave the project
        # clean so it reopens to the Start screen rather than a blank page.
        if not self._pages:
            return
        QgsProject.instance().writeEntry(
            PROJECT_SCOPE, PROJECT_KEY, json.dumps(self._build_layout_dict()))

    def load_from_project(self):
        raw, ok = QgsProject.instance().readEntry(
            PROJECT_SCOPE, PROJECT_KEY, "")
        self.clear_all()
        if not ok or not raw:
            # fresh project, no dashboard yet: greet with the Start screen
            self.bus.set_theme(Theme.default())
            self._apply_window_style()
            self.show_start()
            return
        try:
            data = migrate_layout(json.loads(raw))
        except (ValueError, TypeError):
            self.show_start()
            return
        self._apply_layout_dict(data)
        self.show_dashboard()
        self._reset_history()             # loaded dashboard → fresh timeline
