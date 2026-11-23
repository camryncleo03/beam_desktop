import unittest

from beam_calculations import (
    LUMBER_SECTIONS,
    STEEL_SECTIONS,
    PointLoad,
    UniformLoad,
    analyze_beam,
    check_section,
)


class BeamCalculationTests(unittest.TestCase):
    def test_uniform_load_simply_supported(self):
        result = analyze_beam(
            "Simply Supported",
            20,
            [],
            [UniformLoad(1.0, 0.0, 20.0)],
            STEEL_SECTIONS[2],
        )
        self.assertAlmostEqual(result.left_reaction_kips, 10.0, places=6)
        self.assertAlmostEqual(result.right_reaction_kips, 10.0, places=6)
        self.assertAlmostEqual(result.max_moment_kipft, 50.0, places=2)
        self.assertAlmostEqual(result.max_moment_location_ft, 10.0, places=2)
        self.assertAlmostEqual(result.max_deflection_in, 0.609, delta=0.01)

        check = check_section(
            "Simply Supported",
            20,
            [],
            [UniformLoad(1.0, 0.0, 20.0)],
            STEEL_SECTIONS[2],
            "L/360",
        )
        self.assertAlmostEqual(check.bending_stress_ksi, 17.96, places=2)
        self.assertTrue(check.bending_pass)
        self.assertTrue(check.deflection_pass)

    def test_point_load_simply_supported(self):
        result = analyze_beam(
            "Simply Supported",
            20,
            [PointLoad(10.0, 5.0)],
            [],
            STEEL_SECTIONS[2],
        )
        self.assertAlmostEqual(result.left_reaction_kips, 7.5, places=6)
        self.assertAlmostEqual(result.right_reaction_kips, 2.5, places=6)
        self.assertAlmostEqual(result.max_moment_kipft, 37.5, places=2)
        self.assertAlmostEqual(result.max_moment_location_ft, 5.0, places=2)
        self.assertAlmostEqual(result.max_deflection_in, 0.340, delta=0.01)

    def test_cantilever_point_load(self):
        result = analyze_beam(
            "Cantilever",
            10,
            [PointLoad(5.0, 10.0)],
            [],
            STEEL_SECTIONS[2],
        )
        self.assertAlmostEqual(result.left_reaction_kips, 5.0, places=6)
        self.assertAlmostEqual(result.fixed_end_moment_kipft, 50.0, places=6)
        self.assertAlmostEqual(result.max_deflection_in, 0.487, delta=0.01)

    def test_lumber_uniform_load(self):
        result = analyze_beam(
            "Simply Supported",
            12,
            [],
            [UniformLoad(0.05, 0.0, 12.0)],
            LUMBER_SECTIONS[1],
        )
        self.assertAlmostEqual(result.max_moment_kipft, 0.90, places=2)
        check = check_section(
            "Simply Supported",
            12,
            [],
            [UniformLoad(0.05, 0.0, 12.0)],
            LUMBER_SECTIONS[1],
            "L/360",
        )
        self.assertAlmostEqual(check.bending_stress_ksi, 0.505, places=3)
        self.assertTrue(check.bending_pass)
        self.assertTrue(check.deflection_pass)

    def test_partial_uniform_load_validation(self):
        result = analyze_beam(
            "Simply Supported",
            30,
            [],
            [UniformLoad(2.0, 0.0, 15.0)],
            STEEL_SECTIONS[5],
        )
        self.assertAlmostEqual(result.left_reaction_kips, 22.5, places=6)
        self.assertAlmostEqual(result.right_reaction_kips, 7.5, places=6)
        self.assertAlmostEqual(result.max_moment_kipft, 126.6, places=1)
        self.assertAlmostEqual(result.max_moment_location_ft, 11.25, places=2)


if __name__ == "__main__":
    unittest.main()
