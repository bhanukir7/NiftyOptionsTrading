import time
import os
import json
from collections import deque

class RateLimiter:
    """
    Manages API Rate Limits for ICICI Breeze.
    Tracks requests per minute and per day to prevent limits (100/min, 5000/day).
    Persists data to disk so limits are respected across script runs.
    """
    def __init__(self, max_per_min=100, max_per_day=5000, file_path=None):
        self.max_per_min = max_per_min
        self.max_per_day = max_per_day
        if file_path is None:
            # Point to logs/ in the project root (relative to this file's parent's parent)
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logs_dir = os.path.join(root_dir, 'logs')
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir, exist_ok=True)
            self.file_path = os.path.join(logs_dir, 'api_usage.json')
        else:
            self.file_path = file_path
            
        self.call_timestamps = deque()
        self.daily_calls = 0
        self.current_day = time.localtime().tm_yday
        self._load_state()
        
    def _load_state(self):
        """Loads rate limit state from disk."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    state = json.load(f)
                    if state.get('current_day') == self.current_day:
                        self.daily_calls = state.get('daily_calls', 0)
                        timestamps = state.get('call_timestamps', [])
                        # Load only valid valid minute timestamps
                        now = time.time()
                        self.call_timestamps = deque([ts for ts in timestamps if now - ts < 60.0])
                    else:
                        # File state is from yesterday, override with fresh state
                        self._save_state()
            except Exception:
                pass
                
    def _save_state(self):
        """Saves current rate limit state to disk."""
        try:
            state = {
                'current_day': self.current_day,
                'daily_calls': self.daily_calls,
                'call_timestamps': list(self.call_timestamps)
            }
            with open(self.file_path, 'w') as f:
                json.dump(state, f)
        except Exception:
            pass
        
    def _reset_if_needed(self):
        """Resets the daily counter if the day has crossed."""
        now_day = time.localtime().tm_yday
        if now_day != self.current_day:
            self.daily_calls = 0
            self.call_timestamps.clear()
            self.current_day = now_day
            self._save_state()
            
    def _cleanup_minute_queue(self, current_time: float):
        """Evicts timestamps older than 60 seconds from the deque."""
        dirty = False
        while self.call_timestamps and current_time - self.call_timestamps[0] >= 60.0:
            self.call_timestamps.popleft()
            dirty = True
        return dirty

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
        self._save_state()
