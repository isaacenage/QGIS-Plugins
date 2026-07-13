# -*- coding: utf-8 -*-
"""Shared visual theme for Title Plotter PH.

A single source of truth for the plugin's look, ported from the sibling
``qgis_dashboards`` plugin's design system: neutral white chrome, 1px hairline
borders (``#e2e6ec`` — never heavy dark outlines), the Century Gothic system
font stack, soft 8-10px radii, and slim rounded scrollbars.

The one deliberate departure from the dashboards palette is the **accent**: this
plugin keeps its survey-teal ``#14575b`` as its single brand color (buttons,
focus rings, selected tabs), while adopting everything else from the dashboards
chrome. Everything is funneled through :func:`dialog_qss` so all three dialogs
stay consistent instead of each carrying its own copy of a stylesheet.
"""

# The chrome font stack is fixed (matches qgis_dashboards SYSTEM_FONT_STACK).
SYSTEM_FONT_STACK = (
    '"Century Gothic", "Questrial", "Segoe UI", '
    '"Helvetica Neue", Arial, sans-serif'
)

# Neutral chrome palette + teal accent. Keys mirror the dashboards CHROME dict
# so the ported QSS below reads identically.
PALETTE = {
    "bg": "#ffffff",                          # window / dialog background
    "surface": "#ffffff",                     # inputs / tables / menus
    "text": "#252b33",                        # primary foreground
    "muted": "#55606d",                       # secondary foreground
    "accent": "#14575b",                      # survey teal — the single accent
    "accent_hover": "#114a4e",                # teal * ~0.86 (hover / pressed)
    "brand_soft": "rgba(20, 87, 91, 0.10)",   # 10% teal tint for hover fills
    "border": "#e2e6ec",                      # hairline dividers / edges (1px)
    "selection": "#e5e7eb",                   # selected row / pressed fill
    "zebra": "#f6f8fb",                        # table header / alternating row
}


def dialog_qss():
    """Return the full stylesheet for a Title Plotter dialog and its children."""
    return """
* {{ font-family:{system_font}; }}
QDialog, QMainWindow {{ background:{bg}; }}
QWidget {{ color:{text}; }}
QFrame {{ border:none; background:transparent; }}
QLabel {{ color:{text}; background:transparent; }}
QLabel[role="muted"] {{ color:{muted}; }}

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
QDialogButtonBox QPushButton:hover {{ border-color:{accent}; background:{brand_soft}; }}
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
QToolButton {{ color:{text}; background:transparent; border:1px solid transparent;
    border-radius:8px; }}
QToolButton:hover {{ background:{brand_soft}; border-color:{border}; }}
QToolButton:pressed {{ background:{selection}; }}
QToolButton:checked {{ background:{brand_soft}; border-color:{accent}; }}
QCheckBox, QRadioButton {{ color:{text}; background:transparent; }}

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

/* Scroll areas + tables + lists ------------------------------------------ */
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
    border:none; border-right:1px solid {border}; border-bottom:1px solid {border};
    font-weight:600;
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
QScrollBar::handle:vertical {{ background:{selection}; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{muted}; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{selection}; border-radius:5px; min-width:30px; }}
QScrollBar::handle:horizontal:hover {{ background:{muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

/* Splitter, menus, tooltip ----------------------------------------------- */
QSplitter::handle {{ background:{border}; }}
QMenu {{ background:{surface}; color:{text}; border:1px solid {border};
    border-radius:8px; padding:4px; }}
QMenu::item {{ padding:6px 18px; border-radius:6px; color:{text}; }}
QMenu::item:selected {{ background:{brand_soft}; color:{accent}; }}
QToolTip {{
    background:#111827; color:#ffffff; border:none; border-radius:6px;
    padding:5px 8px; font-size:11px;
}}
""".format(system_font=SYSTEM_FONT_STACK, **PALETTE)


def apply(widget):
    """Apply the shared theme stylesheet to *widget* (a dialog/window)."""
    widget.setStyleSheet(dialog_qss())
