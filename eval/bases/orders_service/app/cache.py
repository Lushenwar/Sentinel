import time


class TTLCache:
    def __init__(self, ttl_s: float, max_entries: int):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._data: dict = {}

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key, value):
        if len(self._data) >= self.max_entries:
            self._data.pop(next(iter(self._data)))
        self._data[key] = (value, time.monotonic() + self.ttl_s)
