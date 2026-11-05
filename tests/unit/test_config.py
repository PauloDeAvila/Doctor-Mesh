"""Unit tests for InspectionConfig (config.py) — no Blender required."""
import math
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_mesh_doctor.config import InspectionConfig


class TestInspectionConfig(unittest.TestCase):

    def test_defaults_are_valid(self):
        cfg = InspectionConfig()
        self.assertEqual(cfg.distance_tolerance, 1e-6)
        self.assertEqual(cfg.area_tolerance, 1e-12)
        self.assertEqual(cfg.max_vertices, 250_000)
        self.assertEqual(cfg.max_region_indices, 512)
        self.assertEqual(cfg.max_duplicate_pairs, 1000)
        self.assertEqual(cfg.inspect_evaluated, True)
        self.assertEqual(cfg.max_seconds, 120.0)

    def test_valid_custom_values(self):
        cfg = InspectionConfig(
            distance_tolerance=1e-5,
            area_tolerance=1e-10,
            max_vertices=100_000,
            max_region_indices=256,
            max_duplicate_pairs=500,
            inspect_evaluated=False,
            max_seconds=60.0,
        )
        self.assertEqual(cfg.distance_tolerance, 1e-5)
        self.assertEqual(cfg.inspect_evaluated, False)

    def test_distance_tolerance_must_be_positive(self):
        with self.assertRaises(ValueError):
            InspectionConfig(distance_tolerance=0)
        with self.assertRaises(ValueError):
            InspectionConfig(distance_tolerance=-1e-6)
        with self.assertRaises(ValueError):
            InspectionConfig(distance_tolerance=float('nan'))
        with self.assertRaises(ValueError):
            InspectionConfig(distance_tolerance=float('inf'))

    def test_area_tolerance_must_be_positive(self):
        with self.assertRaises(ValueError):
            InspectionConfig(area_tolerance=0)
        with self.assertRaises(ValueError):
            InspectionConfig(area_tolerance=float('nan'))

    def test_max_seconds_must_be_positive(self):
        with self.assertRaises(ValueError):
            InspectionConfig(max_seconds=0)
        with self.assertRaises(ValueError):
            InspectionConfig(max_seconds=float('inf'))

    def test_max_vertices_must_be_positive_int(self):
        with self.assertRaises(ValueError):
            InspectionConfig(max_vertices=0)
        with self.assertRaises(ValueError):
            InspectionConfig(max_vertices=-1)
        with self.assertRaises(ValueError):
            InspectionConfig(max_vertices=1.5)

    def test_max_region_indices_must_be_positive_int(self):
        with self.assertRaises(ValueError):
            InspectionConfig(max_region_indices=0)

    def test_max_duplicate_pairs_must_be_positive_int(self):
        with self.assertRaises(ValueError):
            InspectionConfig(max_duplicate_pairs=0)

    def test_to_dict(self):
        cfg = InspectionConfig(distance_tolerance=2e-6, max_seconds=30.0)
        d = cfg.to_dict()
        self.assertEqual(d['distance_tolerance'], 2e-6)
        self.assertEqual(d['max_seconds'], 30.0)
        self.assertEqual(d['max_vertices'], 250_000)


if __name__ == '__main__':
    unittest.main()