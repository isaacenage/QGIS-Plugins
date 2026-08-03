# -*- coding: utf-8 -*-
"""Tests for the pure symbology modules — ACI, linetypes, lineweights, hatches.

Runs without QGIS. From the plugin directory::

    python test/test_style.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style import aci, hatches, linetypes, lineweights   # noqa: E402


class TestAci(unittest.TestCase):

    def test_table_is_complete(self):
        self.assertEqual(len(aci.TABLE), 256)

    def test_standard_colours(self):
        self.assertEqual(aci.rgb(1), (255, 0, 0))
        self.assertEqual(aci.rgb(2), (255, 255, 0))
        self.assertEqual(aci.rgb(3), (0, 255, 0))
        self.assertEqual(aci.rgb(4), (0, 255, 255))
        self.assertEqual(aci.rgb(5), (0, 0, 255))
        self.assertEqual(aci.rgb(6), (255, 0, 255))

    def test_generated_ramp_matches_reference(self):
        # Anchors from the published AutoCAD Color Index.
        self.assertEqual(aci.rgb(10), (255, 0, 0))
        self.assertEqual(aci.rgb(11), (255, 127, 127))
        self.assertEqual(aci.rgb(12), (165, 0, 0))
        self.assertEqual(aci.rgb(13), (165, 82, 82))
        self.assertEqual(aci.rgb(19), (38, 19, 19))
        self.assertEqual(aci.rgb(30), (255, 127, 0))
        self.assertEqual(aci.rgb(90), (0, 255, 0))
        self.assertEqual(aci.rgb(170), (0, 0, 255))
        self.assertEqual(aci.rgb(250), (51, 51, 51))
        self.assertEqual(aci.rgb(255), (255, 255, 255))

    def test_index_seven_follows_background(self):
        self.assertEqual(aci.display_rgb(7, background_is_dark=False),
                         (0, 0, 0))
        self.assertEqual(aci.display_rgb(7, background_is_dark=True),
                         (255, 255, 255))

    def test_out_of_range_falls_back(self):
        self.assertEqual(aci.rgb(9999), aci.TABLE[7])
        self.assertEqual(aci.rgb("nonsense"), aci.TABLE[7])

    def test_nearest_index_round_trips_by_colour(self):
        # The palette contains genuine duplicates — ACI 3 and ACI 90 are both
        # pure green — so a round trip is only required to preserve the
        # *colour*, not the index. nearest_index returns the lowest matching
        # index, which is the canonical one.
        for index in (1, 3, 5, 30, 90, 150, 210):
            colour = aci.rgb(index)
            self.assertEqual(aci.rgb(aci.nearest_index(*colour)), colour)

    def test_nearest_index_prefers_the_canonical_low_index(self):
        self.assertEqual(aci.nearest_index(0, 255, 0), 3)

    def test_nearest_index_handles_off_palette_colour(self):
        self.assertEqual(aci.nearest_index(250, 8, 8), 1)


class TestLineweights(unittest.TestCase):

    def test_ladder_is_the_autocad_set(self):
        self.assertEqual(len(lineweights.LADDER), 24)
        self.assertIn(35, lineweights.LADDER)
        self.assertIn(211, lineweights.LADDER)

    def test_hundredths_convert_to_mm(self):
        self.assertAlmostEqual(lineweights.to_mm(35), 0.35)
        self.assertAlmostEqual(lineweights.to_mm(211), 2.11)

    def test_zero_is_a_hairline_not_invisible(self):
        self.assertAlmostEqual(lineweights.to_mm(0),
                               lineweights.HAIRLINE_MM)

    def test_off_ladder_values_snap(self):
        self.assertEqual(lineweights.snap_to_ladder(36), 35)
        self.assertEqual(lineweights.snap_to_ladder(1), 0)
        self.assertEqual(lineweights.snap_to_ladder(lineweights.BYLAYER),
                         lineweights.BYLAYER)

    def test_bylayer_resolves_against_layer(self):
        self.assertAlmostEqual(
            lineweights.resolve(lineweights.BYLAYER, 50), 0.50)
        self.assertAlmostEqual(lineweights.resolve(70, 50), 0.70)

    def test_display_off_forces_hairline(self):
        self.assertAlmostEqual(
            lineweights.resolve(200, 200, display_enabled=False),
            lineweights.HAIRLINE_MM)

    def test_labels(self):
        self.assertEqual(lineweights.label(35), "0.35 mm")
        self.assertEqual(lineweights.label(lineweights.BYLAYER), "ByLayer")


class TestLinetypes(unittest.TestCase):

    def test_standard_table_loaded(self):
        for expected in ("CONTINUOUS", "HIDDEN", "CENTER", "DASHED",
                         "PHANTOM", "DASHDOT", "DIVIDE", "DOT", "BORDER"):
            self.assertIn(expected, linetypes.STANDARD)

    def test_continuous_has_no_dashes(self):
        self.assertTrue(linetypes.get("CONTINUOUS").is_continuous)
        self.assertEqual(linetypes.to_dash_vector("CONTINUOUS"), [])

    def test_dashed_pattern_values(self):
        self.assertEqual(linetypes.get("DASHED").elements, [0.5, -0.25])
        self.assertEqual(linetypes.to_dash_vector("DASHED"), [0.5, 0.25])

    def test_center_alternates_long_short(self):
        self.assertEqual(linetypes.to_dash_vector("CENTER"),
                         [1.25, 0.25, 0.25, 0.25])

    def test_ltscale_multiplies(self):
        self.assertEqual(linetypes.to_dash_vector("DASHED", ltscale=2.0),
                         [1.0, 0.5])
        self.assertEqual(
            linetypes.to_dash_vector("DASHED", ltscale=2.0, celtscale=0.5),
            [0.5, 0.25])

    def test_dot_becomes_a_short_dash(self):
        vector = linetypes.to_dash_vector("DOT")
        self.assertEqual(len(vector), 2)
        self.assertAlmostEqual(vector[0], linetypes.DOT_LENGTH)
        self.assertAlmostEqual(vector[1], 0.25)

    def test_dash_vectors_are_always_well_formed(self):
        # Every pattern must alternate dash/gap, be even-length, and be > 0.
        for name in linetypes.names():
            vector = linetypes.to_dash_vector(name)
            if not vector:
                continue
            self.assertEqual(len(vector) % 2, 0,
                             "{0} has an odd dash vector".format(name))
            for value in vector:
                self.assertGreater(value, 0.0,
                                   "{0} has a non-positive element".format(name))

    def test_leading_gap_is_padded(self):
        table = linetypes.parse_lin("*LEADGAP,starts with a gap\nA,-.25,.5\n")
        vector = table["LEADGAP"].dash_vector()
        self.assertEqual(len(vector) % 2, 0)
        self.assertAlmostEqual(vector[0], linetypes.DOT_LENGTH)
        self.assertAlmostEqual(vector[1], 0.25)

    def test_complex_linetype_is_flagged_not_dropped(self):
        table = linetypes.parse_lin(
            '*GAS_LINE,Gas ----GAS----GAS----\n'
            'A,.5,-.2,["GAS",STANDARD,S=.1,R=0.0,X=-0.1,Y=-.05],-.25\n')
        pattern = table["GAS_LINE"]
        self.assertTrue(pattern.is_complex)
        self.assertEqual(len(pattern.embedded), 1)
        # The dash part still parses so it degrades to a plain dashed line.
        self.assertEqual(pattern.elements, [0.5, -0.2, -0.25])

    def test_bylayer_resolution(self):
        self.assertEqual(linetypes.resolve("BYLAYER", "HIDDEN"), "HIDDEN")
        self.assertEqual(linetypes.resolve("CENTER", "HIDDEN"), "CENTER")
        self.assertEqual(linetypes.resolve("BYLAYER", "BYLAYER"), "CONTINUOUS")

    def test_unknown_name_falls_back_to_continuous(self):
        self.assertEqual(linetypes.get("NOT_A_REAL_LINETYPE").name,
                         "CONTINUOUS")

    def test_paper_millimetre_conversion(self):
        # DASHED at 1:100 in metres: 0.5 m -> 5 mm on paper.
        vector = linetypes.to_dash_vector_mm(
            "DASHED", scale_denominator=100.0, units_per_metre=1.0)
        self.assertAlmostEqual(vector[0], 5.0)
        self.assertAlmostEqual(vector[1], 2.5)

    def test_malformed_stanza_is_skipped_not_fatal(self):
        table = linetypes.parse_lin(
            "*GOOD,fine\nA,.5,-.25\n"
            "garbage line with no star\n"
            "*ALSOGOOD,fine too\nA,.25,-.25\n")
        self.assertIn("GOOD", table)
        self.assertIn("ALSOGOOD", table)


class TestHatches(unittest.TestCase):

    def test_standard_table_loaded(self):
        for expected in ("SOLID", "ANSI31", "ANSI37", "NET", "BRICK",
                         "EARTH", "GRAVEL", "HONEY", "STEEL"):
            self.assertIn(expected, hatches.STANDARD)

    def test_ansi31_is_one_family_at_45(self):
        pattern = hatches.get("ANSI31")
        self.assertEqual(len(pattern.families), 1)
        family = pattern.families[0]
        self.assertAlmostEqual(family.angle, 45.0)
        self.assertAlmostEqual(family.spacing, 0.125)
        self.assertFalse(family.is_dashed)

    def test_ansi37_is_a_cross_hatch(self):
        pattern = hatches.get("ANSI37")
        self.assertEqual(len(pattern.families), 2)
        angles = sorted(f.angle for f in pattern.families)
        self.assertEqual(angles, [45.0, 135.0])

    def test_net_is_orthogonal(self):
        angles = sorted(f.angle for f in hatches.get("NET").families)
        self.assertEqual(angles, [0.0, 90.0])

    def test_dashed_family_parses_its_dashes(self):
        family = hatches.get("EARTH").families[0]
        self.assertTrue(family.is_dashed)
        self.assertEqual(family.dashes, [0.25, -0.125])

    def test_stagger_is_flagged(self):
        # BRICK relies on delta-x, which QGIS line fills cannot express.
        self.assertTrue(hatches.get("BRICK").needs_stagger)
        self.assertFalse(hatches.get("ANSI31").needs_stagger)

    def test_family_geometry_applies_scale_and_angle(self):
        family = hatches.get("ANSI31").families[0]
        angle, spacing, _offset = hatches.family_geometry(
            family, pattern_scale=2.0, pattern_angle=45.0)
        self.assertAlmostEqual(angle, 90.0)
        self.assertAlmostEqual(spacing, 0.25)

    def test_solid_is_marked(self):
        self.assertTrue(hatches.get("SOLID").is_solid)
        self.assertFalse(hatches.get("ANSI31").is_solid)

    def test_every_family_has_usable_spacing(self):
        for name in hatches.names():
            for family in hatches.get(name).families:
                self.assertGreater(family.spacing, 0.0,
                                   "{0} has zero spacing".format(name))

    def test_dash_vectors_are_well_formed(self):
        for name in hatches.names():
            for family in hatches.get(name).families:
                vector = family.dash_vector()
                if not vector:
                    continue
                self.assertEqual(len(vector) % 2, 0)
                for value in vector:
                    self.assertGreater(value, 0.0)

    def test_unknown_pattern_falls_back_to_solid(self):
        self.assertEqual(hatches.get("NOT_A_PATTERN").name, "SOLID")

    def test_user_pat_file_parses(self):
        table = hatches.parse_pat(
            "*MYPAT, custom\n"
            "0, 0,0, 0,.5\n"
            "90, 0,0, 0,.5, .25,-.25\n")
        pattern = table["MYPAT"]
        self.assertEqual(len(pattern.families), 2)
        self.assertEqual(pattern.families[1].dashes, [0.25, -0.25])


if __name__ == "__main__":
    unittest.main(verbosity=2)
