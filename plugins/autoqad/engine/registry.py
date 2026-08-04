# -*- coding: utf-8 -*-
"""The command registry — name and alias resolution.

Pure module: no Qt, no QGIS.

Commands register themselves here; the runner, the command line's
autocompletion, the icon rail and the scripting API all read from the same
table, so a newly added command appears everywhere at once.

Alias resolution follows AutoCAD: an exact name wins, then an exact alias, then
a unique case-insensitive prefix. That last rule is why typing ``REC`` reaches
``RECTANG`` without it being declared as an alias.

:meth:`CommandRegistry.suggest` is the same knowledge served differently — a
ranked list for the as-you-type suggestion box, where being *nearly* right
still has to surface something. Keeping it here rather than in the widget is
what lets the ranking be unit-tested without a canvas.
"""

import difflib

from collections import namedtuple

#: One row of the suggestion list. *hint* is the alias that matched, or "".
Suggestion = namedtuple("Suggestion", "name hint description rank")

#: Ranking tiers, best first. An exact alias wins outright because typing
#: ``PL`` and meaning anything other than PLINE is not a thing a CAD user
#: does; everything below it is degrees of "you might have meant".
RANK_ALIAS_EXACT = 0
RANK_NAME_PREFIX = 1
RANK_ALIAS_PREFIX = 2
RANK_CONTAINS = 3
RANK_FUZZY = 4

#: How alike a name has to be before it is offered as a near miss.
FUZZY_THRESHOLD = 0.6


class CommandRegistry(object):
    """Holds every known command class, keyed by name and alias."""

    def __init__(self):
        self._commands = {}       # NAME -> class
        self._aliases = {}        # ALIAS -> NAME
        self._order = []          # registration order

    # ---- registration ----

    def register(self, command_class):
        """Register *command_class*. Returns it, so it can be used as a decorator."""
        name = str(command_class.name or "").upper()
        if not name:
            raise ValueError("Command class has no name: {0!r}".format(
                command_class))
        if name not in self._commands:
            self._order.append(name)
        self._commands[name] = command_class
        for alias in getattr(command_class, "aliases", ()):
            self._aliases[str(alias).upper()] = name
        return command_class

    def register_all(self, command_classes):
        for command_class in command_classes:
            self.register(command_class)
        return self

    # ---- lookup ----

    def resolve(self, name):
        """Return the command class for *name*, or ``None``.

        Tries exact name, exact alias, then a unique prefix.
        """
        if not name:
            return None
        key = str(name).strip().upper()
        if not key:
            return None

        if key in self._commands:
            return self._commands[key]
        if key in self._aliases:
            return self._commands[self._aliases[key]]

        matches = [n for n in self._order if n.startswith(key)]
        if len(matches) == 1:
            return self._commands[matches[0]]
        return None

    def resolve_name(self, name):
        """Return the canonical command name for *name*, or ``None``."""
        command_class = self.resolve(name)
        return command_class.name if command_class else None

    def __contains__(self, name):
        return self.resolve(name) is not None

    def __len__(self):
        return len(self._commands)

    # ---- enumeration ----

    def names(self):
        """Every command name, in registration order."""
        return list(self._order)

    def aliases_for(self, name):
        canonical = str(name).upper()
        return sorted(a for a, target in self._aliases.items()
                      if target == canonical)

    def commands(self):
        """Every registered class, in registration order."""
        return [self._commands[n] for n in self._order]

    def by_group(self, group):
        return [c for c in self.commands() if c.group == group]

    def groups(self):
        seen = []
        for command in self.commands():
            if command.group not in seen:
                seen.append(command.group)
        return seen

    def completions(self, prefix):
        """Names and aliases starting with *prefix*, for command-line hints."""
        key = str(prefix or "").strip().upper()
        if not key:
            return []
        hits = [n for n in self._order if n.startswith(key)]
        hits.extend(a for a in sorted(self._aliases) if a.startswith(key)
                    and self._aliases[a] not in hits)
        return hits

    # ---- as-you-type suggestions ----

    def _rank(self, name, aliases, key):
        """How well *key* matches this command, or ``None`` for not at all."""
        if key in aliases:
            return (RANK_ALIAS_EXACT, key)
        if name.startswith(key):
            return (RANK_NAME_PREFIX, "")
        for alias in aliases:
            if alias.startswith(key):
                return (RANK_ALIAS_PREFIX, alias)
        if key in name:
            return (RANK_CONTAINS, "")
        ratio = difflib.SequenceMatcher(None, name, key).ratio()
        if ratio >= FUZZY_THRESHOLD:
            return (RANK_FUZZY, "")
        return None

    def suggest(self, prefix, limit=8):
        """Return ranked :class:`Suggestion` rows for a partly typed command.

        Matching widens as it goes: exact alias, then names starting with what
        was typed, then aliases starting with it, then names *containing* it —
        so ``POL`` offers ``POLYGON`` and would offer an ``MPOLYGON`` too —
        and finally near misses, which is what makes a typo recoverable
        instead of silently matching nothing.
        """
        key = str(prefix or "").strip().upper()
        if not key:
            return []

        rows = []
        for name in self._order:
            command = self._commands[name]
            aliases = sorted(a for a, target in self._aliases.items()
                             if target == name)
            scored = self._rank(name, aliases, key)
            if scored is None:
                continue
            rank, hint = scored
            rows.append(Suggestion(name, hint,
                                   command.description or "", rank))

        rows.sort(key=lambda row: (row.rank, row.name))
        return rows[:limit] if limit else rows

    def best_completion(self, prefix):
        """Return the name to finish *prefix* with inline, or ``""``.

        Only ever *extends* what was typed — a completion that rewrote the
        first letters would fight the user's own keystrokes.
        """
        key = str(prefix or "").strip().upper()
        if not key:
            return ""
        for row in self.suggest(key, limit=0):
            if row.name.startswith(key):
                return row.name
        return ""

    def describe(self, name):
        """Return ``(name, aliases, description)`` for *name*, or ``None``."""
        command_class = self.resolve(name)
        if command_class is None:
            return None
        return (command_class.name,
                list(getattr(command_class, "aliases", ())),
                command_class.description or "")

    def reference(self):
        """Return a list of dicts describing every command (used by the API)."""
        return [{
            "name": c.name,
            "aliases": list(getattr(c, "aliases", ())),
            "group": c.group,
            "description": c.description or "",
            "modifies": bool(c.modifies),
        } for c in self.commands()]
