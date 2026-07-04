# -*- coding: utf-8 -*-
"""Per-edge dashboard-action logic (pure, no Qt/QGIS).

ArcGIS wires source -> action -> target. This module holds the action-set logic
for the connection graph so the bus stays a thin signal/store layer and the
rules are unit-testable with plain Python (like ``zoom_fit`` / ``layout_util``).

An edge is ``(source_id, target_id)``; its value is a set of action names drawn
from :data:`ACTIONS`. Only *map* targets honor location actions; every other
target only ever filters.

Persistence is **hybrid** for backward compatibility: a source whose every edge
is the plain ``{"filter"}`` still serializes as the legacy ``{src: [tgt,...]}``
list, so a filter-only dashboard saved by this version stays byte-compatible
with the pre-action plugin; only action-bearing edges use the richer
``{src: {tgt: [actions]}}`` shape.
"""

ACTIONS = frozenset({"filter", "zoom", "pan", "flash", "show_popup"})
LOCATION_ACTIONS = frozenset({"zoom", "pan", "flash", "show_popup"})
DEFAULT_ACTIONS = frozenset({"filter"})
MAP_DEFAULT_ACTIONS = frozenset({"filter", "zoom", "flash"})


def has_filter(actions):
    return "filter" in (actions or ())


def location_part(actions):
    return set(actions or ()) & set(LOCATION_ACTIONS)


def serialize(adjacency, actions):
    """{src:set(tgt)} + {(src,tgt):set} -> hybrid persist dict.

    Filter-only sources emit the legacy ``{src: [tgt,...]}`` list; any source
    with an action-bearing edge emits ``{src: {tgt: [actions]}}``.
    """
    out = {}
    for src, tgts in adjacency.items():
        tgts = [t for t in tgts if t]
        if not tgts:
            continue
        edge_sets = {t: set(actions.get((src, t), DEFAULT_ACTIONS)) for t in tgts}
        if all(s == set(DEFAULT_ACTIONS) for s in edge_sets.values()):
            out[src] = sorted(edge_sets)
        else:
            out[src] = {t: sorted(s) for t, s in sorted(edge_sets.items())}
    return out


def deserialize(data):
    """Hybrid persist dict -> ({src:set(tgt)}, {(src,tgt):set})."""
    adjacency = {}
    actions = {}
    if not isinstance(data, dict):
        return adjacency, actions
    for src, val in data.items():
        if isinstance(val, dict):
            tgts = {t for t, a in val.items() if a is not None}
            for t, a in val.items():
                actions[(src, t)] = set(a) if a else set(DEFAULT_ACTIONS)
        else:                                  # legacy list -> filter edges
            tgts = {t for t in (val or []) if t}
            for t in tgts:
                actions[(src, t)] = set(DEFAULT_ACTIONS)
        if tgts:
            adjacency[src] = tgts
    return adjacency, actions


def edge_action_set(actions, src, tgt, is_map):
    """Effective actions for one edge: explicit, else type-based default."""
    explicit = actions.get((src, tgt))
    if explicit:
        return set(explicit)
    return set(MAP_DEFAULT_ACTIONS if is_map else DEFAULT_ACTIONS)


def upgrade_legacy_map_edges(actions, adjacency, map_ids):
    """Give every implicit edge into a map the classic {filter,zoom,flash}.

    Preserves legacy fly-to behavior on load. Explicit entries are untouched.
    Returns a new dict (does not mutate the input).
    """
    out = dict(actions)
    map_ids = set(map_ids or ())
    for src, tgts in adjacency.items():
        for tgt in tgts:
            if tgt in map_ids and (src, tgt) not in out:
                out[(src, tgt)] = set(MAP_DEFAULT_ACTIONS)
    return out
