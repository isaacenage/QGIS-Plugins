# -*- coding: utf-8 -*-
"""The CAD layer model — AutoCAD layer semantics over a QGIS attribute.

Pure module: no Qt, no QGIS.

A CAD layer is *not* a QGIS layer here. Every entity carries an ``aq_layer``
attribute naming its CAD layer, and the renderer builds one rule per CAD layer.
That keeps the QGIS layer count at three (lines, points, polygons) no matter
how many CAD layers a drawing has, which is what keeps the spatial index and
the snapping locator fast.

A layer owns the ByLayer defaults every entity inherits — colour, linetype,
lineweight — plus the four states AutoCAD gives it:

``on``
    Off layers are not drawn but are still snapped and selected.
``frozen``
    Frozen layers are not drawn, not snapped and not selected — the state that
    actually buys performance on a big drawing.
``locked``
    Locked layers draw and snap but cannot be edited.
``plottable``
    Excluded from plotted/exported output only.
"""

from . import aci, linetypes, lineweights

#: The layer every drawing has and which cannot be deleted or renamed.
DEFAULT_LAYER = "0"

# Characters AutoCAD forbids in a layer name.
_INVALID = set('<>/\\":;?*|,=`')


def is_valid_name(name):
    """True when *name* is usable as a CAD layer name."""
    if not name or not str(name).strip():
        return False
    return not any(ch in _INVALID for ch in str(name))


def sanitize_name(name):
    """Return *name* with forbidden characters replaced by underscores."""
    cleaned = "".join("_" if ch in _INVALID else ch for ch in str(name or ""))
    cleaned = cleaned.strip()
    return cleaned or DEFAULT_LAYER


class CadLayer(object):
    """One CAD layer's definition and state."""

    __slots__ = ("name", "color", "linetype", "lineweight", "on", "frozen",
                 "locked", "plottable", "transparency", "description")

    def __init__(self, name, color=7, linetype=linetypes.CONTINUOUS,
                 lineweight=lineweights.DEFAULT, on=True, frozen=False,
                 locked=False, plottable=True, transparency=0,
                 description=""):
        self.name = str(name)
        #: ACI index. A layer's colour is always concrete — never ByLayer.
        self.color = int(color)
        self.linetype = str(linetype).upper()
        self.lineweight = int(lineweight)
        self.on = bool(on)
        self.frozen = bool(frozen)
        self.locked = bool(locked)
        self.plottable = bool(plottable)
        #: 0-100; AutoCAD's layer transparency.
        self.transparency = int(transparency)
        self.description = str(description)

    # ---- derived state ----

    @property
    def is_visible(self):
        """True when entities on this layer are drawn."""
        return self.on and not self.frozen

    @property
    def is_selectable(self):
        """True when entities on this layer can be snapped to or picked.

        Off layers stay selectable — that is the whole difference between Off
        and Frozen in AutoCAD.
        """
        return not self.frozen

    @property
    def is_editable(self):
        return self.is_selectable and not self.locked

    @property
    def is_default(self):
        return self.name == DEFAULT_LAYER

    def rgb(self, background_is_dark=False):
        return aci.display_rgb(self.color, background_is_dark)

    def hex_color(self, background_is_dark=False):
        return aci.hex_color(self.color, background_is_dark)

    def width_mm(self, display_enabled=True):
        """Resolve this layer's plot width in millimetres."""
        return lineweights.resolve(self.lineweight, self.lineweight,
                                   display_enabled)

    def opacity(self):
        """Return 0..1 opacity from the layer transparency percentage."""
        return max(0.0, min(1.0, 1.0 - (self.transparency / 100.0)))

    # ---- entity resolution (the ByLayer contract) ----

    def resolve_color(self, entity_color, background_is_dark=False):
        """Resolve an entity's ACI colour against this layer."""
        value = int(entity_color if entity_color is not None else aci.BYLAYER)
        if value in (aci.BYLAYER, aci.BYBLOCK):
            value = self.color
        return aci.display_rgb(value, background_is_dark)

    def resolve_linetype(self, entity_linetype):
        return linetypes.resolve(entity_linetype, self.linetype)

    def resolve_lineweight(self, entity_lineweight, display_enabled=True):
        return lineweights.resolve(
            entity_lineweight if entity_lineweight is not None
            else lineweights.BYLAYER,
            self.lineweight, display_enabled)

    # ---- serialisation ----

    def to_dict(self):
        return {
            "name": self.name,
            "color": self.color,
            "linetype": self.linetype,
            "lineweight": self.lineweight,
            "on": self.on,
            "frozen": self.frozen,
            "locked": self.locked,
            "plottable": self.plottable,
            "transparency": self.transparency,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        return cls(
            name=data.get("name", DEFAULT_LAYER),
            color=data.get("color", 7),
            linetype=data.get("linetype", linetypes.CONTINUOUS),
            lineweight=data.get("lineweight", lineweights.DEFAULT),
            on=data.get("on", True),
            frozen=data.get("frozen", False),
            locked=data.get("locked", False),
            plottable=data.get("plottable", True),
            transparency=data.get("transparency", 0),
            description=data.get("description", ""))

    def copy(self):
        return CadLayer.from_dict(self.to_dict())

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<CadLayer {0}>".format(self.name)


class LayerTable(object):
    """The drawing's ordered collection of CAD layers.

    Always contains layer ``"0"``, which cannot be removed or renamed — the
    same guarantee AutoCAD makes.
    """

    def __init__(self, layers=None, current=DEFAULT_LAYER):
        self._layers = {}
        self._order = []
        self.add(CadLayer(DEFAULT_LAYER))
        for layer in (layers or []):
            self.add(layer)
        self._current = current if current in self._layers else DEFAULT_LAYER

    # ---- collection ----

    def __contains__(self, name):
        return str(name) in self._layers

    def __len__(self):
        return len(self._order)

    def __iter__(self):
        return iter(self.all())

    def all(self):
        """Return every layer, in creation order with ``"0"`` first."""
        return [self._layers[n] for n in self._order]

    def names(self):
        return list(self._order)

    def get(self, name):
        """Return the named layer, or ``None``."""
        return self._layers.get(str(name))

    def get_or_create(self, name):
        """Return the named layer, creating it with defaults if absent."""
        key = sanitize_name(name)
        if key not in self._layers:
            self.add(CadLayer(key))
        return self._layers[key]

    def add(self, layer):
        """Add or replace *layer*. Returns it."""
        key = layer.name
        if key not in self._layers:
            self._order.append(key)
        self._layers[key] = layer
        return layer

    def remove(self, name):
        """Delete a layer. Returns False for layer ``"0"`` or an unknown name."""
        key = str(name)
        if key == DEFAULT_LAYER or key not in self._layers:
            return False
        del self._layers[key]
        self._order.remove(key)
        if self._current == key:
            self._current = DEFAULT_LAYER
        return True

    def rename(self, old, new):
        """Rename a layer, preserving its position. Returns the new name or None."""
        old_key = str(old)
        if old_key == DEFAULT_LAYER or old_key not in self._layers:
            return None
        new_key = sanitize_name(new)
        if not is_valid_name(new_key) or new_key in self._layers:
            return None
        layer = self._layers.pop(old_key)
        layer.name = new_key
        self._layers[new_key] = layer
        self._order[self._order.index(old_key)] = new_key
        if self._current == old_key:
            self._current = new_key
        return new_key

    # ---- current layer ----

    @property
    def current(self):
        """The layer new entities are created on."""
        return self._layers[self._current]

    @property
    def current_name(self):
        return self._current

    def set_current(self, name):
        """Make *name* current. A frozen layer cannot be made current."""
        key = str(name)
        layer = self._layers.get(key)
        if layer is None or layer.frozen:
            return False
        self._current = key
        return True

    # ---- bulk state ----

    def visible_names(self):
        return [n for n in self._order if self._layers[n].is_visible]

    def selectable_names(self):
        return [n for n in self._order if self._layers[n].is_selectable]

    def editable_names(self):
        return [n for n in self._order if self._layers[n].is_editable]

    # ---- serialisation ----

    def to_dict(self):
        return {"current": self._current,
                "layers": [self._layers[n].to_dict() for n in self._order]}

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        table = cls()
        for entry in data.get("layers", []):
            table.add(CadLayer.from_dict(entry))
        table.set_current(data.get("current", DEFAULT_LAYER))
        return table
