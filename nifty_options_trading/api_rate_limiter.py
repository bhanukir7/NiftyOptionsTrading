import time
from collections import deque

class RateLimiter:
    """
    Manages API Rate Limits for ICICI Breeze.
    Tracks requests per minute and per day to prevent limits (100/min, 5000/day).
    """
    def __init__(self, max_per_min=100, max_per_day=5000):
        self.max_per_min = max_per_min
        self.max_per_day = max_per_day
        self.call_timestamps = deque()
        self.daily_calls = 0
        self.current_day = time.localtime().tm_yday
        
    def _reset_if_needed(self):
        """Resets the daily counter if the day has crossed."""
        now_day = time.localtime().tm_yday
        if now_day != self.current_day:
            self.daily_calls = 0
            self.call_timestamps.clear()
            self.current_day = now_day
            
    def _cleanup_minute_queue(self, current_time: float):
        """Evicts timestamps older than 60 seconds from the deque."""
        while self.call_timestamps and current_time - self.call_timestamps[0] >= 60.0:
            self.call_timestamps.popleft()

    def can_call(self) -> bool:
        """Returns whether an API call can be safely made right now."""
        self._reset_if_needed()
        now = time.time()
        self._cleanup_minute_queue(now)
            
        if len(self.call_timestamps) >= self.max_per_min:
            return False
            
        if self.daily_calls >= self.max_per_day:
            return False
            
        return True

    def wait_if_needed(self):
        """Blocks execution until an API call is safe to make."""
        self._reset_if_needed()
        self._cleanup_minute_queue(time.time())
        
        # If daily limit reached, throw exception as waiting won't help
        if self.daily_calls >= self.max_per_day:
            raise Exception("Critical: Daily API call limit of {} reached.".format(self.max_per_day))
            
        while not self.can_call():
            time.sleep(0.5)

    def record_call(self):
        """Records a successful API call execution."""
        self._reset_if_needed()
        self.call_timestamps.append(time.time())
        self.daily_calls += 1
