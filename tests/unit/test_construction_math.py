"""Unit tests for construction_math.py — no Blender required."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_mesh_doctor.construction_math import through_cut_interval, segments_for_sagitta


class TestThroughCutInterval(unittest.TestCase):

    def test_basic_interval(self):
        lower, upper = through_cut_interval(0.0, 10.0)
        self.assertLess(lower, 0.0)
        self.assertGreater(upper, 10.0)

    def test_margin_relative_to_span(self):
        l1, u1 = through_cut_interval(0.0, 100.0)
        l2, u2 = through_cut_interval(0.0, 10.0)
        # Larger span should produce proportionally larger margin
        margin1 = (u1 - l1) - 100.0
        margin2 = (u2 - l2) - 10.0
        self.assertGreater(margin1, margin2)

    def test_tolerance_effect(self):
        # With a tiny interval, the tolerance*8 term can dominate the margin.
        l1, u1 = through_cut_interval(0.0, 0.001, tolerance=1e-7)
        l2, u2 = through_cut_interval(0.0, 0.001, tolerance=1e-4)
        # Larger tolerance -> larger or equal margin
        self.assertGreaterEqual((u2 - l2), (u1 - l1))

    def test_lower_must_be_less_than_upper(self):
        with self.assertRaises(ValueError):
            through_cut_interval(10.0, 0.0)
        with self.assertRaises(ValueError):
            through_cut_interval(5.0, 5.0)

    def test_non_finite_rejected(self):
        with self.assertRaises(ValueError):
            through_cut_interval(float('nan'), 10.0)
        with self.assertRaises(ValueError):
            through_cut_interval(0.0, float('inf'))

    def test_tolerance_must_be_positive(self):
        with self.assertRaises(ValueError):
            through_cut_interval(0.0, 10.0, tolerance=0)
        with self.assertRaises(ValueError):
            through_cut_interval(0.0, 10.0, tolerance=-1e-7)


class TestSegmentsForSagitta(unittest.TestCase):

    def test_basic(self):
        n = segments_for_sagitta(radius=1.0, error=0.01)
        self.assertIsInstance(n, int)
        self.assertGreaterEqual(n, 16)

    def test_smaller_error_requires_more_segments(self):
        n1 = segments_for_sagitta(radius=1.0, error=0.1)
        n2 = segments_for_sagitta(radius=1.0, error=0.01)
        self.assertGreater(n2, n1)

    def test_minimum_respected(self):
        n = segments_for_sagitta(radius=1.0, error=1.0, minimum=32)
        self.assertGreaterEqual(n, 32)

    def test_maximum_respected(self):
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=1.0, error=1e-12, maximum=16)

    def test_radius_and_error_must_be_positive(self):
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=0.0, error=0.01)
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=1.0, error=0.0)
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=-1.0, error=0.01)
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=1.0, error=float('nan'))

    def test_min_max_must_be_valid(self):
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=1.0, error=0.01, minimum=2)
        with self.assertRaises(ValueError):
            segments_for_sagitta(radius=1.0, error=0.01, minimum=10, maximum=5)


if __name__ == '__main__':
    unittest.main()