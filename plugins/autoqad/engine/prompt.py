# -*- coding: utf-8 -*-
"""Prompt types — what a command asks the user for.

Pure module: no Qt, no QGIS.

A command is a generator that yields prompts and receives answers. Each prompt
declares what kind of answer it wants, which keyword options it accepts, and
what to preview while the user decides. The runner reads those declarations to
decide how to interpret typed text, what to show on the command line, and which
rubber-band preview to drive — so a command never touches the UI itself.

Every prompt can be answered with a keyword instead of a value. AutoCAD shows
options in brackets and matches on the capitalised prefix (``Close`` matches
``C``); :meth:`Prompt.match_keyword` reproduces that, which is most of what
makes the command line feel right.
"""


class _Sentinel(object):
    """A distinguishable non-value answer."""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<{0}>".format(self.name)

    def __bool__(self):
        return False

    __nonzero__ = __bool__                    # Python 2 style guard, harmless


#: The user pressed Escape, or the command was aborted.
CANCEL = _Sentinel("CANCEL")
#: The user pressed Enter with no input — "accept the default / finish".
ENTER = _Sentinel("ENTER")


class Prompt(object):
    """Base prompt. *message* is shown without its trailing colon."""

    #: What the runner should try to parse typed text as.
    kind = "text"

    #: Whether a space belongs *in* the answer. At almost every prompt a
    #: space submits, as it does at AutoCAD's command line — but the one
    #: asking for the contents of a TEXT entity obviously cannot work that
    #: way, so prompts declare it rather than the widget guessing.
    literal_space = False

    def __init__(self, message, options=None, default=None,
                 allow_enter=True, rubber=None, base_point=None):
        self.message = message
        #: Keyword options, in display order (e.g. ``["Close", "Undo"]``).
        self.options = list(options or [])
        self.default = default
        #: Whether a bare Enter is meaningful here.
        self.allow_enter = allow_enter
        #: Preview descriptor the runner hands to the rubber-band manager.
        self.rubber = rubber
        #: Anchor for relative input, ortho and polar tracking.
        self.base_point = base_point

    # ---- display ----

    def format(self):
        """Render the prompt the way AutoCAD's command line shows it."""
        text = self.message
        if self.options:
            text += " [{0}]".format("/".join(self.options))
        if self.default is not None:
            text += " <{0}>".format(self.default)
        return text + ": "

    # ---- keyword matching ----

    @staticmethod
    def _keyword_prefix(option):
        """Return the abbreviation for *option* — its leading capitals.

        ``"Close"`` -> ``"C"``, ``"CEnter"`` -> ``"CE"``. Falls back to the
        whole word when an option carries no capitals.
        """
        prefix = ""
        for char in option:
            if char.isupper():
                prefix += char
            elif prefix:
                break
        return (prefix or option).upper()

    def match_keyword(self, text):
        """Return the matching option for *text*, or ``None``.

        Matches the capitalised abbreviation first, then a unique
        case-insensitive prefix of the full word — the same order AutoCAD uses.
        """
        if not text:
            return None
        value = str(text).strip().upper()
        if not value:
            return None

        for option in self.options:
            if self._keyword_prefix(option) == value:
                return option

        matches = [o for o in self.options if o.upper().startswith(value)]
        if len(matches) == 1:
            return matches[0]
        return None

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<{0} {1!r}>".format(type(self).__name__, self.message)


class PointPrompt(Prompt):
    """Ask for a point. Answered by a canvas click or a typed coordinate."""

    kind = "point"


class DistancePrompt(Prompt):
    """Ask for a distance. A canvas click measures from :attr:`base_point`."""

    kind = "distance"


class AnglePrompt(Prompt):
    """Ask for an angle in drawing angle units."""

    kind = "angle"


class IntegerPrompt(Prompt):
    """Ask for a whole number (segment counts, array rows …)."""

    kind = "integer"

    def __init__(self, message, minimum=None, maximum=None, **kwargs):
        super().__init__(message, **kwargs)
        self.minimum = minimum
        self.maximum = maximum

    def clamp(self, value):
        """Return *value* if within bounds, else ``None``."""
        if value is None:
            return None
        if self.minimum is not None and value < self.minimum:
            return None
        if self.maximum is not None and value > self.maximum:
            return None
        return value


class StringPrompt(Prompt):
    """Ask for free text (TEXT contents, layer names …)."""

    kind = "string"
    literal_space = True


class KeywordPrompt(Prompt):
    """Ask for one of a fixed set of options and nothing else."""

    kind = "keyword"

    def __init__(self, message, options, default=None, **kwargs):
        super().__init__(message, options=options, default=default, **kwargs)


class SelectionPrompt(Prompt):
    """Ask the user to select entities.

    Answered with a list of ``(table_name, feature_id)`` pairs. *single* stops
    at the first pick instead of collecting until Enter.

    A multi-pick prompt advertises ``ALL`` by default, because selecting the
    whole drawing is how a CAD user erases or transforms it wholesale and there
    is otherwise no way to say it. The runner intercepts the word before
    keyword matching, so it never reaches the command as a literal string.
    """

    kind = "selection"

    #: The keyword the runner expands into "every entity in the drawing".
    ALL = "ALL"

    def __init__(self, message="Select objects", single=False,
                 filter_types=None, **kwargs):
        if not single and not kwargs.get("options"):
            kwargs["options"] = [self.ALL]
        super().__init__(message, **kwargs)
        self.single = single
        #: Restrict picking to these entity types, or ``None`` for any.
        self.filter_types = list(filter_types) if filter_types else None


# --- rubber-band preview descriptors ----------------------------------------
#
# Plain data. The runner translates these into canvas items; commands stay free
# of any Qt dependency.

class Rubber(object):
    """Base preview descriptor."""

    __slots__ = ()


class RubberLine(Rubber):
    """A line from *anchor* to the cursor."""

    __slots__ = ("anchor",)

    def __init__(self, anchor):
        self.anchor = anchor


class RubberPolyline(Rubber):
    """A committed run of *points* plus a live segment to the cursor."""

    __slots__ = ("points", "closed")

    def __init__(self, points, closed=False):
        self.points = list(points)
        self.closed = closed


class RubberRectangle(Rubber):
    """An axis-aligned rectangle from *anchor* to the cursor."""

    __slots__ = ("anchor",)

    def __init__(self, anchor):
        self.anchor = anchor


class RubberCircle(Rubber):
    """A circle centred on *center*, radius following the cursor."""

    __slots__ = ("center", "radius")

    def __init__(self, center, radius=None):
        self.center = center
        self.radius = radius


class RubberArc(Rubber):
    """A three-point arc; the third point follows the cursor."""

    __slots__ = ("start", "second")

    def __init__(self, start, second=None):
        self.start = start
        self.second = second


class RubberGeometry(Rubber):
    """An arbitrary preview geometry, optionally translated by the cursor.

    Used by MOVE/COPY/ROTATE, which preview the actual selection.
    """

    __slots__ = ("geometries", "anchor", "mode")

    def __init__(self, geometries, anchor=None, mode="translate"):
        self.geometries = list(geometries)
        self.anchor = anchor
        #: ``"translate"``, ``"rotate"``, ``"scale"`` or ``"static"``.
        self.mode = mode
