# -*- coding: utf-8 -*-
"""The command registry — name and alias resolution.

Pure module: no Qt, no QGIS.

Commands register themselves here; the runner, the command line's
autocompletion, the icon rail and the scripting API all read from the same
table, so a newly added command appears everywhere at once.

Alias resolution follows AutoCAD: an exact name wins, then an exact alias, then
a unique case-insensitive prefix. That last rule is why typing ``REC`` reaches
``RECTANG`` without it being declared as an alias.
"""


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
