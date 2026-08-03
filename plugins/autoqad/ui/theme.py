# -*- coding: utf-8 -*-
"""AutoQAD's visual theme — the shared byZenterra chrome.

The same design system the sibling ``qgis_dashboards`` and ``titleplotter``
plugins use: neutral white chrome, 1px ``#e2e6ec`` hairline borders (never
heavy dark outlines), the Century Gothic system stack, soft 8-10px radii and
slim rounded scrollbars.

The one deliberate departure is the accent — AutoQAD carries a technical steel
blue, distinct from Title Plotter's survey teal and Dashboards' brighter blue
while staying obviously part of the same family.

Two palettes, and the split matters:

* :data:`PALETTE` is the **chrome** — docks, dialogs, the command line, the
  rail. Fixed, light, and never affected by anything the user draws.
* :data:`CANVAS` holds the few colours that belong to the **drawing model**
  (the model-space background), which decides how ACI 7 resolves — white on a
  dark background, black on a light one.
"""

SYSTEM_FONT_STACK = (
    '"Century Gothic", "Questrial", "Segoe UI", '
    '"Helvetica Neue", Arial, sans-serif'
)

#: A monospaced stack for the command line, where column alignment matters.
MONO_FONT_STACK = (
    '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", monospace'
)

PALETTE = {
    "bg": "#ffffff",
    "surface": "#ffffff",
    "text": "#252b33",
    "muted": "#55606d",
    "accent": "#2f5d8c",                        # technical steel blue
    "accent_hover": "#284f78",                  # accent * ~0.86
    "brand_soft": "rgba(47, 93, 140, 0.10)",
    "border": "#e2e6ec",
    "selection": "#e5e7eb",
    "zebra": "#f6f8fb",
    "console": "#1e242b",                       # command history background
    "console_text": "#dfe5ec",
    "warn": "#b3541e",
}

#: Drawing-model colours. ``background`` decides how ACI 7 resolves.
CANVAS = {
    "background": "#ffffff",
    "is_dark": False,
}


def background_is_dark():
    """True when model space uses a dark background (ACI 7 draws white)."""
    return bool(CANVAS["is_dark"])


def dialog_qss():
    """Return the stylesheet for AutoQAD dialogs, docks and their children."""
    return """
* {{ font-family:{system_font}; }}
QDialog, QMainWindow {{ background:{bg}; }}
QWidget {{ color:{text}; }}
QFrame {{ border:none; background:transparent; }}
QLabel {{ color:{text}; background:transparent; }}
QLabel[role="muted"] {{ color:{muted}; }}
QLabel[role="heading"] {{ font-weight:600; font-size:13px; }}

/* Buttons ---------------------------------------------------------------- */
QPushButton {{
    min-height:32px; padding:7px 16px; border-radius:10px;
    border:1px solid transparent; font-weight:600;
    background:{accent}; color:#ffffff;
}}
QPushButton:hover {{ background:{accent_hover}; }}
QPushButton:pressed {{ background:{accent_hover}; border-color:{accent_hover}; }}
QPushButton:disabled {{ background:{border}; color:{muted}; }}
QPushButton[variant="secondary"] {{
    background:{surface}; border:1px solid {border}; color:{text};
}}
QPushButton[variant="secondary"]:hover {{
    border-color:{accent}; background:{brand_soft};
}}
QPushButton[variant="ghost"] {{
    background:transparent; border:none; color:{accent};
}}
QPushButton[variant="ghost"]:hover {{ background:{brand_soft}; }}
QDialogButtonBox QPushButton {{
    background:{surface}; border:1px solid {border}; color:{text};
}}
QDialogButtonBox QPushButton:hover {{
    border-color:{accent}; background:{brand_soft};
}}
QDialogButtonBox QPushButton:default {{
    background:{accent}; border-color:{accent}; color:#ffffff;
}}
QDialogButtonBox QPushButton:default:hover {{
    background:{accent_hover}; border-color:{accent_hover};
}}

/* Inputs ----------------------------------------------------------------- */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background:{surface}; border:1px solid {border}; border-radius:8px;
    color:{text}; padding:5px 9px; min-height:28px;
    selection-background-color:{selection}; selection-color:{text};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{ border:1px solid {accent}; }}
QLineEdit:disabled, QComboBox:disabled {{ background:{zebra}; color:{muted}; }}
QComboBox::drop-down {{ width:22px; border:none; background:transparent; }}
QComboBox QAbstractItemView {{
    background:{surface}; color:{text}; border:1px solid {border};
    selection-background-color:{selection}; selection-color:{text};
}}
QCheckBox, QRadioButton {{ color:{text}; background:transparent; }}

/* Tool buttons ----------------------------------------------------------- */
QToolButton {{
    color:{text}; background:transparent; border:1px solid transparent;
    border-radius:8px;
}}
QToolButton:hover {{ background:{brand_soft}; border-color:{border}; }}
QToolButton:pressed {{ background:{selection}; }}
QToolButton:checked {{ background:{brand_soft}; border-color:{accent}; }}

/* Group boxes ------------------------------------------------------------ */
QGroupBox {{
    background:{surface}; border:1px solid {border}; border-radius:10px;
    margin-top:14px; padding:14px 12px 10px 12px; font-weight:600; color:{text};
}}
QGroupBox::title {{
    subcontrol-origin:margin; subcontrol-position:top left; left:12px;
    padding:0 6px; color:{muted}; background:{bg};
}}

/* Tabs ------------------------------------------------------------------- */
QTabWidget::pane {{ border:1px solid {border}; border-radius:10px; top:-1px; }}
QTabBar {{ background:transparent; }}
QTabBar::tab {{
    background:transparent; color:{muted}; padding:8px 16px; margin-right:2px;
    border:none; border-bottom:3px solid transparent; font-weight:500;
}}
QTabBar::tab:hover {{ color:{text}; }}
QTabBar::tab:selected {{
    color:{accent}; font-weight:600; border-bottom:3px solid {accent};
    background:{brand_soft};
    border-top-left-radius:8px; border-top-right-radius:8px;
}}

/* Tables and lists ------------------------------------------------------- */
QScrollArea {{ background:transparent; border:none; }}
QTableWidget, QTableView {{
    background:{surface}; color:{text}; gridline-color:{border};
    border:1px solid {border}; border-radius:10px;
    selection-background-color:{selection}; selection-color:{text};
    alternate-background-color:{zebra};
}}
QTableView::item {{ padding:4px 8px; }}
QListView, QTreeView, QListWidget, QTreeWidget {{
    background:{surface}; color:{text}; border:1px solid {border};
    border-radius:10px; alternate-background-color:{zebra};
}}
QListWidget::item, QTreeWidget::item {{ padding:5px 8px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background:{selection}; color:{text};
}}
QHeaderView::section {{
    background:{zebra}; color:{text}; padding:6px 10px;
    border:none; border-right:1px solid {border};
    border-bottom:1px solid {border}; font-weight:600;
}}
QTableCornerButton::section {{ background:{zebra}; border:none; }}

/* Sliders ---------------------------------------------------------------- */
QSlider::groove:horizontal {{ height:4px; border-radius:2px; background:{border}; }}
QSlider::sub-page:horizontal {{ background:{accent}; border-radius:2px; }}
QSlider::handle:horizontal {{
    background:{accent}; border:2px solid {bg}; width:14px; height:14px;
    margin:-6px 0; border-radius:9px;
}}
QSlider::handle:horizontal:hover {{ background:{accent_hover}; }}

/* Scrollbars (slim, rounded) --------------------------------------------- */
QScrollBar:vertical {{ background:transparent; width:12px; margin:2px; }}
QScrollBar::handle:vertical {{
    background:{selection}; border-radius:5px; min-height:30px;
}}
QScrollBar::handle:vertical:hover {{ background:{muted}; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:2px; }}
QScrollBar::handle:horizontal {{
    background:{selection}; border-radius:5px; min-width:30px;
}}
QScrollBar::handle:horizontal:hover {{ background:{muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

/* Splitter, menus, tooltip ----------------------------------------------- */
QSplitter::handle {{ background:{border}; }}
QMenu {{
    background:{surface}; color:{text}; border:1px solid {border};
    border-radius:8px; padding:4px;
}}
QMenu::item {{ padding:6px 18px; border-radius:6px; color:{text}; }}
QMenu::item:selected {{ background:{brand_soft}; color:{accent}; }}
QToolTip {{
    background:#111827; color:#ffffff; border:none; border-radius:6px;
    padding:5px 8px; font-size:11px;
}}

/* AutoQAD-specific chrome ------------------------------------------------ */
QDockWidget {{ color:{text}; titlebar-close-icon:none; }}
QDockWidget::title {{
    background:{bg}; padding:6px 10px; border-bottom:1px solid {border};
    font-weight:600;
}}
#aqRail {{ background:{bg}; border-right:1px solid {border}; }}
#aqRailSep {{ background:{border}; border:none; }}
#aqCommandHistory {{
    background:{console}; color:{console_text}; border:none;
    border-bottom:1px solid {border}; padding:6px 8px;
    font-family:{mono_font}; font-size:12px;
}}
#aqCommandInput {{
    background:{surface}; border:none; border-top:1px solid {border};
    border-radius:0; padding:7px 10px; min-height:30px;
    font-family:{mono_font}; font-size:13px; color:{text};
}}
#aqCommandInput:focus {{ border-top:1px solid {accent}; }}
#aqPromptLabel {{
    color:{accent}; font-family:{mono_font}; font-weight:600;
    padding:0 2px 0 10px;
}}
#aqStatusBar {{ background:{bg}; border-top:1px solid {border}; }}
#aqStatusToggle {{
    border:1px solid transparent; border-radius:6px; padding:3px 9px;
    color:{muted}; font-size:11px; font-weight:600;
}}
#aqStatusToggle:hover {{ background:{brand_soft}; border-color:{border}; }}
#aqStatusToggle:checked {{
    background:{brand_soft}; border-color:{accent}; color:{accent};
}}
#aqSwatch {{ border:1px solid {border}; border-radius:4px; }}
""".format(system_font=SYSTEM_FONT_STACK, mono_font=MONO_FONT_STACK, **PALETTE)


def apply(widget):
    """Apply the AutoQAD theme to *widget* and its children."""
    widget.setStyleSheet(dialog_qss())
