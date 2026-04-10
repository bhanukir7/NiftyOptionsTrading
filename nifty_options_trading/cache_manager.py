import time

class CacheManager:
    """
    Manages in-memory caching with TTL (Time-to-Live) tracking to reduce redundant API calls.
    """
    def __init__(self):
        self._cache = {}

    def get(self, key: str):
        """Retrieves an item from the cache if it exists and has not expired."""
        if key in self._cache:
            data, timestamp, ttl = self._cache[key]
            if time.time() - timestamp < ttl:
                return data
            else:
                # Expired
                del self._cache[key]
        return None

    def set(self, key: str, data, ttl: int):
        """Stores an item in the cache with the given TTL in seconds."""
        self._cache[key] = (data, time.time(), ttl)

    def invalidate(self, key: str):
        """Removes a specific item from the cache."""
        if key in self._cache:
            del self._cache[key]
            
    def clear(self):
        """Clears all cached items."""
        self._cache.clear()
