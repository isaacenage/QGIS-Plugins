# -*- coding: utf-8 -*-
"""Header (brand banner) element.

A presentational banner — no data binding, no cross-filtering — that acts as
the dashboard's brand chrome. It carries a styled title (custom font family /
size / alignment chosen from the installed QGIS/Qt fonts) and a single logo
image in an anchored slot (left / right / above / below the title).

It **is** wrapped in a :class:`~dashboard_canvas.GridTile` like every other
tile — the canvas hosts it free-form (drag / resize / snap) and the tile
provides the move/resize/menu chrome and the Build/Use lock — so this element
only renders its title + logo. ``anchor``/``thickness`` are no longer used (a
tile has free geometry).

``config`` keys: ``title``, ``font_family``, ``font_size``, ``align``,
``logo_path`` (a file path *or* pasted raw ``<svg>`` markup), ``logo_slot``,
``logo_size``, ``logo_gap`` (px between the logo and the title).
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QLabel, QBoxLayout

from .base import DashboardElement
from .header_layout import inner_box_direction
from .media import icon_pixmap

_DIRECTION = {
    "h": QBoxLayout.Direction.LeftToRight,
    "v": QBoxLayout.Direction.TopToBottom,
}


class HeaderElement(DashboardElement):
    type_name = "header"
    is_filter_source = False
    accepts_filter = False

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        # the banner is its own content — drop the base title / description
        # chrome
        self.title_label.hide()
        self.desc_label.hide()
        self._has_base_title = False   # the banner's own title carries styling

        self._logo = QLabel("")
        self._logo.setObjectName("headerLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel("")
        self._title.setObjectName("headerTitle")
        self._title.setWordWrap(False)

        self._inner = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._inner.setContentsMargins(0, 0, 0, 0)
        self._inner.setSpacing(12)
        self.body.addLayout(self._inner, 1)

        self.apply_theme()
        self.refresh()

    # ---- content ----

    def refresh(self):
        cfg = self.config
        size = int(self.style_get("logo_size", 40) or 40)
        raw = (cfg.get("logo_path") or "").strip()
        pm = icon_pixmap(raw, size) if raw else None
        if pm is not None:
            self._logo.setPixmap(pm)
            self._logo.show()
        else:
            self._logo.clear()
            self._logo.hide()
        self._title.setText(cfg.get("title", "") or "")
        self._inner.setSpacing(int(cfg.get("logo_gap", 12) or 0))
        self._rebuild_inner(self.style_get("logo_slot", "left"))
        self._restyle()

    def _rebuild_inner(self, slot):
        lay = self._inner
        lay.removeWidget(self._logo)
        lay.removeWidget(self._title)
        orient, logo_first = inner_box_direction(slot)
        lay.setDirection(_DIRECTION[orient])
        if logo_first:
            lay.addWidget(self._logo, 0)
            lay.addWidget(self._title, 1)
        else:
            lay.addWidget(self._title, 1)
            lay.addWidget(self._logo, 0)

    def _restyle(self):
        # the banner title is a full text role (font / size / color / weight /
        # italic / alignment), all from the Tile Appearance panel.
        th = self.effective_theme()
        self.apply_text_role(self._title, "title", color=th.text,
                             font=th.font_family, size=22, weight=700,
                             align="left")
