"""Unit tests for cache.py — no Blender required."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_mesh_doctor.cache import MeasurementCache, content_key, CACHE_VERSION


class TestContentKey(unittest.TestCase):

    def test_determinism(self):
        k1 = content_key('ns', {'a': 1, 'b': 2})
        k2 = content_key('ns', {'a': 1, 'b': 2})
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 64)

    def test_different_inputs_different_keys(self):
        k1 = content_key('ns', {'a': 1})
        k2 = content_key('ns', {'a': 2})
        self.assertNotEqual(k1, k2)

    def test_different_namespace_different_keys(self):
        k1 = content_key('ns1', {'a': 1})
        k2 = content_key('ns2', {'a': 1})
        self.assertNotEqual(k1, k2)


class TestMeasurementCache(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = MeasurementCache(self.tmpdir)

    def test_put_and_get_complete(self):
        key = content_key('test', {'x': 1})
        payload = {'status': 'complete', 'data': {'value': 42}}
        ok = self.cache.put(key, payload)
        self.assertTrue(ok)
        got = self.cache.get(key)
        self.assertIsNotNone(got)
        self.assertEqual(got['data']['value'], 42)
        self.assertEqual(self.cache.hits, 1)
        self.assertEqual(self.cache.misses, 0)

    def test_get_missing_returns_none(self):
        got = self.cache.get('00' * 32)
        self.assertIsNone(got)
        self.assertEqual(self.cache.misses, 1)

    def test_put_incomplete_returns_false(self):
        key = content_key('test', {'x': 2})
        payload = {'status': 'partial', 'reason': 'budget exceeded'}
        ok = self.cache.put(key, payload)
        self.assertFalse(ok)
        # put() does not increment misses; only get() does
        self.assertEqual(self.cache.misses, 0)
        got = self.cache.get(key)
        self.assertIsNone(got)

    def test_corrupted_checksum_rejected(self):
        key = content_key('test', {'x': 3})
        payload = {'status': 'complete', 'data': {'value': 99}}
        self.cache.put(key, payload)
        # Corrupt the file
        path = Path(self.tmpdir) / f'{key}.json'
        entry = json.loads(path.read_text())
        entry['checksum'] = '0' * 64
        path.write_text(json.dumps(entry))
        got = self.cache.get(key)
        self.assertIsNone(got)
        self.assertEqual(self.cache.misses, 1)

    def test_wrong_status_rejected(self):
        key = content_key('test', {'x': 4})
        payload = {'status': 'skipped_limit', 'reason': 'too many vertices'}
        self.cache.put(key, payload)  # returns False, not stored
        got = self.cache.get(key)
        self.assertIsNone(got)

    def test_cache_version_mismatch_rejected(self):
        key = content_key('test', {'x': 5})
        payload = {'status': 'complete', 'data': {'value': 5}}
        self.cache.put(key, payload)
        path = Path(self.tmpdir) / f'{key}.json'
        entry = json.loads(path.read_text())
        entry['version'] = CACHE_VERSION + 1
        path.write_text(json.dumps(entry))
        got = self.cache.get(key)
        self.assertIsNone(got)

    def test_invalid_key_format_returns_none(self):
        # get() catches ValueError internally and returns None
        got = self.cache.get('not-a-valid-hex-key')
        self.assertIsNone(got)
        got = self.cache.get('too-short')
        self.assertIsNone(got)

    def test_oversize_entry_rejected(self):
        key = content_key('test', {'x': 6})
        path = Path(self.tmpdir) / f'{key}.json'
        path.write_text('x' * (17 * 1024 * 1024))  # > 16MB
        got = self.cache.get(key)
        self.assertIsNone(got)


if __name__ == '__main__':
    unittest.main()