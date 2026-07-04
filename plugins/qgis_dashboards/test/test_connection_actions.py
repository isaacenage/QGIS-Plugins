# coding=utf-8
"""Pure tests for the connection action-set helpers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection_actions import (
    ACTIONS, LOCATION_ACTIONS, DEFAULT_ACTIONS, MAP_DEFAULT_ACTIONS,
    has_filter, location_part, serialize, deserialize, edge_action_set,
    upgrade_legacy_map_edges,
)


class PredicateTest(unittest.TestCase):
    def test_has_filter(self):
        self.assertTrue(has_filter({"filter", "zoom"}))
        self.assertFalse(has_filter({"zoom", "flash"}))

    def test_location_part(self):
        self.assertEqual(location_part({"filter", "zoom", "flash"}), {"zoom", "flash"})
        self.assertEqual(location_part({"filter"}), set())


class SerializeTest(unittest.TestCase):
    def test_filter_only_source_emits_list_shape(self):
        adj = {"s": {"t1", "t2"}}
        actions = {("s", "t1"): {"filter"}, ("s", "t2"): {"filter"}}
        self.assertEqual(serialize(adj, actions), {"s": ["t1", "t2"]})

    def test_action_bearing_source_emits_dict_shape(self):
        adj = {"s": {"m"}}
        actions = {("s", "m"): {"filter", "zoom", "flash"}}
        self.assertEqual(serialize(adj, actions),
                         {"s": {"m": ["filter", "flash", "zoom"]}})

    def test_empty_source_dropped(self):
        self.assertEqual(serialize({"s": set()}, {}), {})


class DeserializeTest(unittest.TestCase):
    def test_list_shape_is_filter_edges(self):
        adj, actions = deserialize({"s": ["t1", "t2"]})
        self.assertEqual(adj, {"s": {"t1", "t2"}})
        self.assertEqual(actions[("s", "t1")], {"filter"})
        self.assertEqual(actions[("s", "t2")], {"filter"})

    def test_dict_shape_keeps_actions(self):
        adj, actions = deserialize({"s": {"m": ["filter", "zoom"]}})
        self.assertEqual(adj, {"s": {"m"}})
        self.assertEqual(actions[("s", "m")], {"filter", "zoom"})

    def test_round_trip_mixed(self):
        adj = {"s": {"t", "m"}}
        actions = {("s", "t"): {"filter"}, ("s", "m"): {"filter", "zoom"}}
        adj2, actions2 = deserialize(serialize(adj, actions))
        self.assertEqual(adj2, adj)
        self.assertEqual(actions2[("s", "m")], {"filter", "zoom"})
        self.assertEqual(actions2[("s", "t")], {"filter"})


class EdgeActionSetTest(unittest.TestCase):
    def test_explicit_wins(self):
        actions = {("s", "m"): {"flash"}}
        self.assertEqual(edge_action_set(actions, "s", "m", True), {"flash"})

    def test_map_default_when_absent(self):
        self.assertEqual(edge_action_set({}, "s", "m", True), set(MAP_DEFAULT_ACTIONS))

    def test_nonmap_default_when_absent(self):
        self.assertEqual(edge_action_set({}, "s", "t", False), set(DEFAULT_ACTIONS))


class UpgradeLegacyTest(unittest.TestCase):
    def test_implicit_map_edge_gets_bundle(self):
        adj = {"s": {"m", "t"}}
        actions = {}                       # legacy: nothing explicit
        out = upgrade_legacy_map_edges(actions, adj, {"m"})
        self.assertEqual(out[("s", "m")], set(MAP_DEFAULT_ACTIONS))
        self.assertNotIn(("s", "t"), out)  # non-map edge left implicit (filter)

    def test_explicit_map_edge_untouched(self):
        adj = {"s": {"m"}}
        actions = {("s", "m"): {"flash"}}
        out = upgrade_legacy_map_edges(actions, adj, {"m"})
        self.assertEqual(out[("s", "m")], {"flash"})


if __name__ == "__main__":
    unittest.main()
