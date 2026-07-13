# -*- coding: utf-8 -*-
"""Recent-dashboard list, persisted in ``QSettings``.

Mirrors how QGIS surfaces recent projects (and the Summarizer plugin's
``DashboardProjectStore``): a small, deduped, capped list of the ``.qdash``
files the user has saved or opened, used to populate the Start screen's cards.

The list-manipulation core (:func:`prune_missing`, :func:`dedupe_insert`) is
**pure** so it can be unit-tested without QGIS; :class:`RecentStore` is the thin
``QSettings`` wrapper that the window actually uses.
"""

import json
import os

MAX_RECENTS = 8
RECENTS_KEY = "QgisDashboard/recent_projects"
LAST_DIR_KEY = "QgisDashboard/last_dir"


# ---- pure helpers (no Qt) --------------------------------------------------

def prune_missing(items, exists=os.path.exists):
    """Return a new list with entries whose ``path`` no longer exists removed."""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if path and exists(path):
            out.append(item)
    return out


def dedupe_insert(items, entry, max_items=MAX_RECENTS):
    """Insert *entry* at the front, dropping any same-path entry, capped.

    Returns a **new** list; *items* is not mutated. Comparison is by absolute,
    case-folded path so the same file recorded twice collapses to one card.
    """
    key = _path_key(entry.get("path"))
    kept = [it for it in (items or [])
            if isinstance(it, dict) and _path_key(it.get("path")) != key]
    return ([entry] + kept)[:max_items]


def _path_key(path):
    return os.path.normcase(os.path.abspath(str(path or "").strip()))


# ---- QSettings-backed store ------------------------------------------------

class RecentStore:
    """Persist the recents list + last-used directory in ``QSettings``."""

    def __init__(self, settings=None):
        # Imported lazily so the pure helpers above stay QGIS-free for testing.
        if settings is None:
            from qgis.PyQt.QtCore import QSettings
            settings = QSettings()
        self._settings = settings

    def load_recents(self):
        """Return the stored recents, pruned of missing files (and capped).

        If pruning changed the list, the trimmed version is written back so the
        stored state stays clean.
        """
        raw = self._settings.value(RECENTS_KEY, "", type=str)
        try:
            items = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            items = []
        if not isinstance(items, list):
            items = []
        pruned = prune_missing(items)[:MAX_RECENTS]
        if len(pruned) != len(items):
            self._write(pruned)
        return pruned

    def record(self, path, name=None):
        """Move *path* to the front of the recents list with a fresh timestamp."""
        entry = {
            "path": os.path.abspath(str(path)),
            "name": str(name or _name_from_path(path)),
            "updated_at": _now_iso(),
        }
        self._write(dedupe_insert(self.load_recents(), entry))

    def clear(self):
        self._write([])

    def default_directory(self):
        configured = self._settings.value(LAST_DIR_KEY, "", type=str)
        if configured and os.path.isdir(configured):
            return configured
        documents = os.path.join(os.path.expanduser("~"), "Documents")
        return documents if os.path.isdir(
            documents) else os.path.expanduser("~")

    def remember_dir(self, path):
        directory = os.path.dirname(os.path.abspath(str(path)))
        if directory:
            self._settings.setValue(LAST_DIR_KEY, directory)

    def _write(self, items):
        try:
            self._settings.setValue(
                RECENTS_KEY, json.dumps(items, ensure_ascii=False))
        except (ValueError, TypeError):
            self._settings.setValue(RECENTS_KEY, "[]")


def _name_from_path(path):
    base = os.path.basename(str(path or ""))
    return os.path.splitext(base)[0] or "Dashboard"


def _now_iso():
    """Current local time as an ISO string (kept out of the pure helpers)."""
    from qgis.PyQt.QtCore import QDateTime, Qt
    return QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
