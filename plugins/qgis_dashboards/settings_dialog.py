# -*- coding: utf-8 -*-
"""Settings dialogs.

* :class:`SettingsDialog` — the gear-button hub on the rail. A **two-column
  master/detail** dialog: a slim left nav lists the sections (*Themes*,
  *Layout*, *About*) and the right pane shows that section's controls,
  descriptions and actions. It gathers the configuration-style actions that
  don't belong on the always-visible rail.

  *Themes* edits the dashboard **theme** — the colors, chart palette and fonts
  that style the **canvas elements only** (the plugin chrome keeps a fixed
  System font). *Layout* gathers everything geometric — corner radius, element
  spacing and text sizes — so the two sections never overlap.
"""

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import (
    QDialog, QLabel, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFrame, QSlider, QWidget, QListWidget, QScrollArea, QStackedWidget,
    QToolButton, QButtonGroup,
    QSpinBox, QFormLayout, QComboBox, QPushButton, QFileDialog, QMessageBox,
)

from .icons import logo_pixmap, monochrome_icon
from .appearance_dialog import AppearanceForm, _ColorButton
from .theme import Theme, SYSTEM_FONT_FAMILY, CHROME
from . import user_fonts

# Right-edge section rail (the "tab pages, but icons" nav).
RAIL_WIDTH = 48
RAIL_BUTTON_SIZE = 36
RAIL_ICON_SIZE = 20

RADIUS_MIN = 0
RADIUS_MAX = 32
GAP_MIN = 0
GAP_MAX = 48
BORDER_WIDTH_MIN = 0
BORDER_WIDTH_MAX = 8
CANVAS_DIM_MIN = 320
CANVAS_DIM_MAX = 8000

# Export/print region presets: (label, width, height). "Custom…" is appended in
# code; editing a spinner flips the combo to it.
CANVAS_PRESETS = [
    ("16:9 — 1280 × 720", 1280, 720),
    ("16:9 — 1920 × 1080", 1920, 1080),
    ("16:10 — 1280 × 800", 1280, 800),
    ("4:3 — 1024 × 768", 1024, 768),
    ("A4 Landscape — 1754 × 1240", 1754, 1240),
    ("A4 Portrait — 1240 × 1754", 1240, 1754),
    ("Letter Landscape — 1650 × 1275", 1650, 1275),
]
CUSTOM_LABEL = "Custom…"

# Project description, rendered as rich text in the About panel.
ABOUT_HTML = """
<p style="margin:0 0 10px 0;">&ldquo;Are there any <i>free</i> dashboards in
QGIS that can be connected to the map we make?&rdquo; my friend Edgar asked.</p>
<p style="margin:0 0 10px 0;">That simple question actually pointed out a pretty
big missing piece in QGIS. When you look around for options, you quickly realize
you either have to pay for a premium platform or go through the hassle of
exporting your data into a completely separate web app. Nothing just worked
natively inside the software for free. So, the <b>QGIS&nbsp;Dashboard</b> plugin
was built to fix exactly that.</p>
<p style="margin:0 0 10px 0;">It lets you create interactive dashboard layouts
that live right inside your QGIS project, using the vector layers you already
have set up. You can just drop in data-driven tiles like charts, lists,
indicators, selectors, and even a live map. The coolest part is that everything
is connected, so when you click a value in one tile, it instantly filters all
the other tiles in real time.</p>
<p style="margin:0;">On top of that, the whole layout saves automatically inside
your QGIS project file so you don't lose anything, and since it's completely
free and open-source, anyone can use it.</p>
"""


class SettingsPanel(QWidget):
    """The gear-button settings hub, hosted in the right inspector panel.

    Each section is its **own page** in a :class:`QStackedWidget`, switched by a
    slim **icon rail pinned to the panel's right edge** (tab pages, but icons):
    *Themes* (``appearance`` glyph — canvas colors, chart palette, fonts),
    *Layout* (``layout`` glyph — canvas size, shape, border, transparency,
    spacing, text sizes) and *About* (``info`` glyph). Only the active page
    scrolls, so reaching About no longer means scrolling past the whole theme
    editor and Layout stack. The active button tints to the CHROME accent. The
    host inspector is width-resizable (drag its left edge) and never covers the
    whole canvas, so theme / font / layout edits preview live behind it.

    Every control applies live through the callbacks: *on_appearance* ``f(Theme)``;
    *on_radius* / *on_gap* / *on_opacity* / *on_border_width* ``f(int)``;
    *on_border_color* ``f(hex)``; *on_size* ``f(key, int)``; *on_canvas_size*
    ``f(w, h)``. *gap* seeds the spacing slider, *canvas_size* the page-size
    controls, and *theme* every theme-derived control.
    """

    def __init__(self, parent=None, theme=None, on_appearance=None,
                 on_radius=None, on_gap=None, on_size=None,
                 on_canvas_size=None, on_opacity=None, on_border_width=None,
                 on_border_color=None, gap=0, canvas_size=None):
        super().__init__(parent)
        self._theme = theme
        self._on_appearance = on_appearance
        self._on_radius = on_radius
        self._on_gap = on_gap
        self._on_size = on_size
        self._on_canvas_size = on_canvas_size
        self._on_opacity = on_opacity
        self._on_border_width = on_border_width
        self._on_border_color = on_border_color
        self._gap = int(gap)
        cw, ch = canvas_size or (CANVAS_PRESETS[0][1], CANVAS_PRESETS[0][2])
        self._canvas_w, self._canvas_h = int(cw), int(ch)
        # guard so programmatic spinner/combo updates don't re-enter the
        # callback
        self._canvas_syncing = False

        # Settings is CHROME: hints read from the fixed CHROME palette so a dark
        # preset never recolors them. Theme-derived controls (radius, border,
        # transparency, text sizes) seed from the live theme.
        self._muted = CHROME["muted"]
        th = theme if theme is not None else Theme.default()
        radius = int(th.radius)
        self._seed_opacity = int(getattr(th, "tile_opacity", 100))
        self._seed_border_width = int(getattr(th, "border_width", 1))
        self._seed_border_color = th.border

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # content (left) + section icon rail (right). Each section is its own
        # page in the stack; only the active one scrolls.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._wrap_scroll(self._themes_page()))
        self._stack.addWidget(self._wrap_scroll(
            self._layout_page(radius, self._gap, self._muted)))
        self._stack.addWidget(self._wrap_scroll(self._about_page()))
        body.addWidget(self._stack, 1)
        body.addWidget(self._build_rail())
        root.addLayout(body, 1)

        # open on the first section (also tints its rail glyph to the accent)
        self._rail_buttons[0][0].setChecked(True)
        self._stack.setCurrentIndex(0)

    # ---- section nav (right icon rail) ----------------------------------

    def _wrap_scroll(self, page):
        """Put one section page in its own vertical scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_rail(self):
        """A slim right-edge icon rail — one checkable button per section."""
        rail = QFrame()
        rail.setObjectName("settingsRail")
        rail.setFixedWidth(RAIL_WIDTH)
        rail.setStyleSheet("""
#settingsRail {{ background:transparent; border-left:1px solid {border}; }}
QToolButton#settingsRailButton {{
    border:none; background:transparent; border-radius:8px;
}}
QToolButton#settingsRailButton:hover {{ background:{brand_soft}; }}
QToolButton#settingsRailButton:checked {{ background:{brand_soft}; }}
""".format(border=CHROME["border"], brand_soft=CHROME["brand_soft"]))

        col = QVBoxLayout(rail)
        col.setContentsMargins(6, 8, 6, 8)
        col.setSpacing(8)

        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        self._rail_buttons = []          # list of (QToolButton, icon_key)
        # (icon key, section label) — order matches the stack pages above.
        sections = [("appearance", "Themes"),
                    ("layout", "Layout"),
                    ("info", "About")]
        for idx, (icon_key, label) in enumerate(sections):
            btn = QToolButton(rail)
            btn.setObjectName("settingsRailButton")
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setAccessibleName(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            btn.setFixedSize(RAIL_BUTTON_SIZE, RAIL_BUTTON_SIZE)
            btn.setIconSize(QSize(RAIL_ICON_SIZE, RAIL_ICON_SIZE))
            icon = monochrome_icon(icon_key, CHROME["text"])
            if icon.isNull():
                # graceful fallback if QtSvg is missing
                btn.setText(label[:2])
            else:
                btn.setIcon(icon)
            btn.clicked.connect(
                lambda _c=False, i=idx: self._stack.setCurrentIndex(i))
            self._rail_group.addButton(btn, idx)
            self._rail_buttons.append((btn, icon_key))
            col.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(1)
        # active section's glyph follows the accent; the rest stay neutral.
        self._rail_group.buttonToggled.connect(
            lambda *_a: self._sync_rail_icons())
        return rail

    def _sync_rail_icons(self):
        """Tint the checked section's glyph to the accent, the others to text."""
        for btn, icon_key in self._rail_buttons:
            tint = CHROME["accent"] if btn.isChecked() else CHROME["text"]
            icon = monochrome_icon(icon_key, tint)
            if not icon.isNull():
                btn.setIcon(icon)

    # ---- pages ----------------------------------------------------------

    def _page_shell(self, title):
        """A blank detail page with a bold caption; returns (page, layout)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)
        caption = QLabel(title)
        caption.setStyleSheet("font-size:16px; font-weight:600;")
        lay.addWidget(caption)
        return page, lay

    def _themes_page(self):
        page, lay = self._page_shell("Themes")

        hint = QLabel(
            "Theme the dashboard <b>canvas</b> — background, text, accent, "
            "fonts and the chart color palette. Pick a ready-made preset or "
            "fine-tune every color by hand. Changes apply live as you edit.")
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % self._muted)
        lay.addWidget(hint)

        # Make the canvas-only scope explicit: the surrounding plugin interface
        # always uses the fixed System font, never the theme's fonts.
        sys_note = QLabel(
            "The theme fonts style the dashboard elements only. The plugin "
            "interface uses a fixed <b>System font</b> ({}) that can't be "
            "changed.".format(SYSTEM_FONT_FAMILY))
        sys_note.setTextFormat(Qt.TextFormat.RichText)
        sys_note.setWordWrap(True)
        sys_note.setStyleSheet("color:%s; font-size:11px;" % self._muted)
        lay.addWidget(sys_note)

        # The whole-dashboard theme editor lives inline here (no extra dialog),
        # applying each edit live via on_appearance.
        theme = self._theme if self._theme is not None else Theme.default()
        # scrollable=False: the panel's own outer scroll handles overflow, so the
        # theme rows are never trapped in a tiny nested scroll area.
        self._appearance_form = AppearanceForm(
            theme, mode="global", on_apply=self._on_appearance, scrollable=False)
        lay.addWidget(self._appearance_form)

        # Custom fonts: upload your own .ttf/.otf. They install per-profile (so
        # every project/dashboard on this PC can use them) and are embedded into
        # shared .qdash files and HTML exports. The pickers above list them once
        # added (reload_fonts refreshes the QFontComboBoxes in place).
        self._build_custom_fonts(lay)
        return page

    # ---- custom fonts ---------------------------------------------------

    def _build_custom_fonts(self, lay):
        self._add_subheading(lay, "Custom fonts")
        hint = QLabel(
            "Add your own <b>.ttf</b> / <b>.otf</b> fonts. They stay available "
            "in every dashboard on this computer, and are embedded into shared "
            "<b>.qdash</b> files and HTML exports. Pick them in the Body / "
            "Heading font lists above.")
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s; font-size:11px;" % self._muted)
        lay.addWidget(hint)

        self._font_list = QListWidget()
        self._font_list.setFixedHeight(96)
        lay.addWidget(self._font_list)

        row = QHBoxLayout()
        row.setSpacing(8)
        add_btn = QPushButton("Add font…")
        add_btn.setProperty("variant", "secondary")
        add_btn.clicked.connect(self._on_add_font)
        remove_btn = QPushButton("Remove selected")
        remove_btn.setProperty("variant", "secondary")
        remove_btn.clicked.connect(self._on_remove_font)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self._refresh_font_list()

    def _refresh_font_list(self):
        self._font_list.clear()
        for family in user_fonts.custom_families():
            self._font_list.addItem(family)

    def _on_add_font(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add font", "", "Fonts (*.ttf *.otf)")
        if not path:
            return
        added = user_fonts.add_font(path)
        if not added:
            QMessageBox.warning(
                self, "Couldn't add font",
                "That file couldn't be added. Make sure it is a valid "
                ".ttf or .otf font file.")
            return
        self._refresh_font_list()
        self._appearance_form.reload_fonts()

    def _on_remove_font(self):
        item = self._font_list.currentItem()
        if item is None:
            return
        family = item.text()
        confirm = QMessageBox.question(
            self, "Remove font",
            "Remove the custom font \"{}\"? Dashboards still using it will "
            "fall back to the default font.".format(family))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        user_fonts.remove_font(family)
        self._refresh_font_list()
        self._appearance_form.reload_fonts()

    def _layout_page(self, radius, gap, muted):
        page, lay = self._page_shell("Layout")

        intro = QLabel(
            "Page size, shape, border, transparency, spacing and text sizes. "
            "Every control previews live on the canvas beside this panel.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:%s;" % muted)
        lay.addWidget(intro)

        # --- Canvas size (the export/print region) -------------------------
        self._add_subheading(lay, "Canvas size")
        canvas_hint = QLabel(
            "The page your dashboard is laid out on — shown as a framed "
            "rectangle on the canvas and the exact area that exports to "
            "PNG/PDF. Reset Zoom fits this page to the view.")
        canvas_hint.setWordWrap(True)
        canvas_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(canvas_hint)
        self._build_canvas_size_controls(lay, muted)

        # --- Corner radius -------------------------------------------------
        self._add_subheading(lay, "Shape")
        radius_hint = QLabel("Corner roundness of every dashboard element.")
        radius_hint.setWordWrap(True)
        radius_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(radius_hint)

        self._radius_slider, self._radius_value = self._slider_row(
            lay, "Corner radius", radius, RADIUS_MIN, RADIUS_MAX,
            page_step=2, muted=muted, on_change=self._on_radius_changed)

        # --- Border (line color + thickness) -------------------------------
        self._add_subheading(lay, "Border")
        border_hint = QLabel(
            "Outline drawn around every dashboard element. Set its color and "
            "thickness (0 px hides it).")
        border_hint.setWordWrap(True)
        border_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(border_hint)

        color_row = QHBoxLayout()
        color_row.setSpacing(10)
        color_row.addWidget(QLabel("Border color"))
        self._border_color_btn = _ColorButton(self._seed_border_color)
        self._border_color_btn.changed.connect(self._on_border_color_changed)
        color_row.addWidget(self._border_color_btn)
        color_row.addStretch(1)
        lay.addLayout(color_row)

        self._border_width_slider, self._border_width_value = self._slider_row(
            lay, "Border thickness", self._seed_border_width,
            BORDER_WIDTH_MIN, BORDER_WIDTH_MAX, page_step=1, muted=muted,
            on_change=self._on_border_width_changed)

        # --- Transparency (element opacity) --------------------------------
        self._add_subheading(lay, "Transparency")
        opacity_hint = QLabel(
            "Opacity of every dashboard element — tiles, charts and tables. At "
            "100% they are solid; lower it to let the canvas show through. The "
            "canvas background itself is unaffected.")
        opacity_hint.setWordWrap(True)
        opacity_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(opacity_hint)

        self._opacity_slider, self._opacity_value = self._slider_row(
            lay, "Element opacity", self._seed_opacity, 0, 100,
            page_step=10, muted=muted, on_change=self._on_opacity_changed,
            unit="%")

        # --- Spacing: one unified value for gap *and* page margin -----------
        self._add_subheading(lay, "Spacing")
        gap_hint = QLabel(
            "One value for the whole dashboard: the gap between elements and "
            "the margin from the page edge to the outer elements are kept equal. "
            "At 0 px cards sit edge to edge and reach the page edge; raise it "
            "for an even, consistent inset everywhere — between cards and around "
            "all four edges — no matter how you arrange them.")
        gap_hint.setWordWrap(True)
        gap_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(gap_hint)

        self._gap_slider, self._gap_value = self._slider_row(
            lay, "Gap & margin", int(gap), GAP_MIN, GAP_MAX,
            page_step=4, muted=muted, on_change=self._on_gap_changed)

        # --- Text sizes ----------------------------------------------------
        self._add_subheading(lay, "Text size")
        sizes_hint = QLabel("Type sizes used inside every dashboard element.")
        sizes_hint.setWordWrap(True)
        sizes_hint.setStyleSheet("color:%s; font-size:11px;" % muted)
        lay.addWidget(sizes_hint)

        theme = self._theme if self._theme is not None else Theme.default()
        sizes = QFormLayout()
        sizes.setContentsMargins(0, 0, 0, 0)
        sizes.setHorizontalSpacing(12)
        self._base_size_spin = self._size_spin(
            theme.font_size, 6, 48, "font_size")
        sizes.addRow("Base text", self._base_size_spin)
        self._title_size_spin = self._size_spin(
            theme.title_size, 8, 48, "title_size")
        sizes.addRow("Element title", self._title_size_spin)
        self._value_size_spin = self._size_spin(
            theme.value_size, 10, 96, "value_size")
        sizes.addRow("Indicator value", self._value_size_spin)
        lay.addLayout(sizes)

        lay.addStretch(1)
        return page

    # ---- layout-control builders ---------------------------------------

    def _add_subheading(self, lay, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight:600; margin-top:6px;")
        lay.addWidget(label)

    def _slider_row(self, lay, label, value, lo, hi, page_step, muted,
                    on_change, unit="px"):
        """Build a labelled slider + live "N <unit>" readout; returns (slider, lbl)."""
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel(label))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(max(lo, min(hi, int(value))))
        slider.setSingleStep(1)
        slider.setPageStep(page_step)
        row.addWidget(slider, 1)
        readout = QLabel("%d %s" % (int(value), unit))
        readout.setMinimumWidth(42)
        readout.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter)
        readout.setStyleSheet("color:%s;" % muted)
        row.addWidget(readout)
        lay.addLayout(row)
        slider.valueChanged.connect(on_change)
        return slider, readout

    def _size_spin(self, value, lo, hi, key):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(int(value))
        spin.setSuffix(" px")
        spin.valueChanged.connect(lambda v, k=key: self._on_size_changed(k, v))
        return spin

    def _build_canvas_size_controls(self, lay, muted):
        """Preset combo + width/height spinners for the export/print region."""
        self._canvas_combo = QComboBox()
        for label, _w, _h in CANVAS_PRESETS:
            self._canvas_combo.addItem(label)
        self._canvas_combo.addItem(CUSTOM_LABEL)
        self._canvas_combo.currentIndexChanged.connect(self._on_canvas_preset)
        lay.addWidget(self._canvas_combo)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._canvas_w_spin = QSpinBox()
        self._canvas_w_spin.setRange(CANVAS_DIM_MIN, CANVAS_DIM_MAX)
        self._canvas_w_spin.setSuffix(" px")
        self._canvas_w_spin.setValue(self._canvas_w)
        self._canvas_h_spin = QSpinBox()
        self._canvas_h_spin.setRange(CANVAS_DIM_MIN, CANVAS_DIM_MAX)
        self._canvas_h_spin.setSuffix(" px")
        self._canvas_h_spin.setValue(self._canvas_h)
        row.addWidget(QLabel("Width"))
        row.addWidget(self._canvas_w_spin, 1)
        sep = QLabel("×")
        sep.setStyleSheet("color:%s;" % muted)
        row.addWidget(sep)
        row.addWidget(QLabel("Height"))
        row.addWidget(self._canvas_h_spin, 1)
        lay.addLayout(row)

        self._canvas_w_spin.valueChanged.connect(self._on_canvas_spin)
        self._canvas_h_spin.valueChanged.connect(self._on_canvas_spin)
        self._sync_canvas_combo()   # preselect the matching preset (or Custom)

    def _about_page(self):
        page, lay = self._page_shell("About QGIS Dashboard")

        logo = QLabel()
        logo.setPixmap(logo_pixmap(48))
        lay.addWidget(logo)

        story = QLabel(ABOUT_HTML)
        story.setTextFormat(Qt.TextFormat.RichText)
        story.setWordWrap(True)
        story.setOpenExternalLinks(True)
        lay.addWidget(story)

        lay.addStretch(1)
        return page

    # ---- callbacks ------------------------------------------------------

    def _on_radius_changed(self, value):
        self._radius_value.setText("%d px" % value)
        if callable(self._on_radius):
            self._on_radius(value)

    def _on_gap_changed(self, value):
        self._gap_value.setText("%d px" % value)
        if callable(self._on_gap):
            self._on_gap(value)

    def _on_opacity_changed(self, value):
        self._opacity_value.setText("%d %%" % value)
        if callable(self._on_opacity):
            self._on_opacity(value)

    def _on_border_width_changed(self, value):
        self._border_width_value.setText("%d px" % value)
        if callable(self._on_border_width):
            self._on_border_width(value)

    def _on_border_color_changed(self):
        if callable(self._on_border_color):
            self._on_border_color(self._border_color_btn.color())

    def _on_size_changed(self, key, value):
        if callable(self._on_size):
            self._on_size(key, value)

    # ---- canvas-size (export/print region) callbacks --------------------

    def _sync_canvas_combo(self):
        """Preselect the preset matching the current size, else ``Custom…``."""
        idx = next((i for i, (_l, w, h) in enumerate(CANVAS_PRESETS)
                    if w == self._canvas_w and h == self._canvas_h),
                   self._canvas_combo.count() - 1)   # last item is Custom…
        self._canvas_syncing = True
        self._canvas_combo.setCurrentIndex(idx)
        self._canvas_syncing = False

    def _on_canvas_preset(self, index):
        """A preset was picked — push its size into the spinners and apply."""
        if self._canvas_syncing or index < 0 or index >= len(CANVAS_PRESETS):
            return   # Custom… (or a programmatic sync) makes no size change
        _label, w, h = CANVAS_PRESETS[index]
        self._canvas_syncing = True
        self._canvas_w_spin.setValue(w)
        self._canvas_h_spin.setValue(h)
        self._canvas_syncing = False
        self._apply_canvas_size()

    def _on_canvas_spin(self, _value):
        """A width/height edit — flip the combo to Custom… and apply."""
        if self._canvas_syncing:
            return
        self._sync_canvas_combo()
        self._apply_canvas_size()

    def _apply_canvas_size(self):
        self._canvas_w = int(self._canvas_w_spin.value())
        self._canvas_h = int(self._canvas_h_spin.value())
        if callable(self._on_canvas_size):
            self._on_canvas_size(self._canvas_w, self._canvas_h)


class SettingsDialog(QDialog):
    """Standalone modal wrapper around :class:`SettingsPanel`.

    The live dashboard hosts the settings in the right inspector panel (see
    ``DashboardWindow.open_settings``); this wrapper is kept for standalone /
    test use so the same controls can open as a regular dialog.
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(460, 640)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.panel = SettingsPanel(parent=self, **kwargs)
        root.addWidget(self.panel, 1)
        footer = QFrame()
        footer.setStyleSheet("border-top:1px solid %s;" % CHROME["border"])
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(22, 10, 22, 12)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        frow.addStretch(1)
        frow.addWidget(buttons)
        root.addWidget(footer)
