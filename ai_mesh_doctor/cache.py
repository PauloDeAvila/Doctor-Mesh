"""Content-addressed measurement cache. Incomplete results are never reused."""
import hashlib
import json
from pathlib import Path
from .reporting import atomic_json

CACHE_VERSION = 1


def content_key(namespace, inputs):
    payload = json.dumps([CACHE_VERSION, namespace, inputs], sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class MeasurementCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.hits = self.misses = 0

    def _path(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError("Invalid content key")
        return self.directory / f'{key}.json'

    def get(self, key):
        try:
            path = self._path(key)
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Oversize cache entry")
            entry = json.loads(path.read_text(encoding='utf-8'))
            payload = entry['payload']
            if (not isinstance(payload,dict) or entry['version'] != CACHE_VERSION or entry['key'] != key
                    or payload.get('status') != 'complete'
                    or content_key('payload', payload) != entry['checksum']):
                raise ValueError("Stale or damaged cache entry")
        except (OSError, ValueError, KeyError, TypeError):
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def put(self, key, payload):
        if payload.get('status') != 'complete':
            return False
        atomic_json(self._path(key), {'version': CACHE_VERSION, 'key': key,
                    'checksum': content_key('payload', payload), 'payload': payload})
        return True
