"""Unit tests for planning.py — no Blender required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_mesh_doctor.planning import validate_plan, deterministic_plan, OPERATIONS


class TestOperations(unittest.TestCase):

    def test_operations_registry(self):
        self.assertIn('recalculate_normals', OPERATIONS)
        self.assertIn('merge_vertices', OPERATIONS)
        self.assertIn('remove_loose', OPERATIONS)
        self.assertIn('fit_plane', OPERATIONS)
        self.assertIn('smooth_local', OPERATIONS)
        self.assertIn('relax_local', OPERATIONS)


class TestValidatePlan(unittest.TestCase):

    def _base_report(self):
        return {
            'objects': [{
                'id': 'obj-1',
                'type': 'MESH',
                'base': {
                    'status': 'complete',
                    'fingerprint': 'abc123',
                    'vertices': 8,
                },
            }],
        }

    def test_valid_recalculate_normals_plan(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1, 2],
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': 'Measured winding inconsistency on face 0',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        result = validate_plan(plan, report)
        self.assertEqual(result['id'], 'obj-1')

    def test_valid_merge_vertices_plan(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1],
            'operation': 'merge_vertices',
            'parameters': {'distance': 0.001},
            'reason': 'Duplicate vertices detected within tolerance',
            'constraints': {
                'max_displacement': 0.01,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        result = validate_plan(plan, report)
        self.assertEqual(result['id'], 'obj-1')

    def test_invalid_unknown_operation(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0],
            'operation': 'unknown_op',
            'parameters': {},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_missing_required_field(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0],
            'operation': 'recalculate_normals',
            'parameters': {},
            # missing 'reason' and 'constraints'
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_empty_reason_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0],
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': '   ',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_fingerprint_mismatch_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'wrong-fingerprint',
            'region': [0],
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_region_out_of_bounds_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1, 999],  # 999 >= 8 vertices
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_region_exceeds_budget_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': list(range(10001)),
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_protected_vertices_overlap_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1],
            'operation': 'recalculate_normals',
            'parameters': {},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [1],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)

    def test_fit_plane_valid_vectors(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1, 2],
            'operation': 'fit_plane',
            'parameters': {'origin': [0, 0, 0], 'normal': [0, 0, 1], 'strength': 0.5},
            'reason': 'Measured plane deviation on region',
            'constraints': {
                'max_displacement': 0.01,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        result = validate_plan(plan, report)
        self.assertEqual(result['id'], 'obj-1')

    def test_fit_plane_zero_normal_rejected(self):
        plan = {
            'target_id': 'obj-1',
            'fingerprint': 'abc123',
            'region': [0, 1, 2],
            'operation': 'fit_plane',
            'parameters': {'origin': [0, 0, 0], 'normal': [0, 0, 0], 'strength': 0.5},
            'reason': 'test',
            'constraints': {
                'max_displacement': 0.0,
                'max_dimension_delta': 0.0,
                'max_topology_delta': 0,
                'protected_vertices': [],
            },
        }
        report = self._base_report()
        with self.assertRaises(ValueError):
            validate_plan(plan, report)


class TestDeterministicPlan(unittest.TestCase):

    def test_deterministic_output(self):
        record = {'id': 'obj-1', 'base': {'fingerprint': 'fp1'}}
        p1 = deterministic_plan(record, 'recalculate_normals', [0, 1], {}, {'max_displacement': 0.0, 'max_dimension_delta': 0.0, 'max_topology_delta': 0, 'protected_vertices': []}, 'test reason')
        p2 = deterministic_plan(record, 'recalculate_normals', [0, 1], {}, {'max_displacement': 0.0, 'max_dimension_delta': 0.0, 'max_topology_delta': 0, 'protected_vertices': []}, 'test reason')
        self.assertEqual(p1, p2)
        self.assertEqual(p1['target_id'], 'obj-1')
        self.assertEqual(p1['fingerprint'], 'fp1')
        self.assertEqual(p1['operation'], 'recalculate_normals')


if __name__ == '__main__':
    unittest.main()