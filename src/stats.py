import time, threading
from collections import deque, Counter

class Stats():
  # counters shared between the bot loop and the overlay thread
  def __init__(self, window=20):
    self.lock = threading.Lock()
    self.start_time = time.time()
    self.casts = 0
    self.bites = 0
    self.catches = 0
    self.recent = deque(maxlen=max(1, int(window)))   # (caught, seconds from cast to result)
    self.catch_times = deque(maxlen=max(2, int(window)))
    self.items = Counter()
    self.last_loot = []

  def record_cast(self, result, secs):
    # result is one of bob_finder's CAUGHT / MISSED / NO_BITE
    with self.lock:
      self.casts += 1
      if result != "no_bite":
        self.bites += 1
      caught = result == "caught"
      if caught:
        self.catches += 1
        self.catch_times.append(time.time())
      self.recent.append((caught, secs))

  def record_loot(self, names):
    with self.lock:
      self.last_loot = list(names)
      self.items.update(names)

  def snapshot(self):
    with self.lock:
      hours = max(1e-6, (time.time() - self.start_time) / 3600)
      recent_rate = sum(c for c, _ in self.recent) / len(self.recent) if self.recent else None
      recent_catch_secs = [s for c, s in self.recent if c]
      if len(self.catch_times) >= 2:
        span = self.catch_times[-1] - self.catch_times[0]
        recent_per_hour = (len(self.catch_times) - 1) / span * 3600 if span > 0 else None
      else:
        recent_per_hour = None
      return {
        "elapsed": time.time() - self.start_time,
        "casts": self.casts,
        "bites": self.bites,
        "catches": self.catches,
        "catch_rate": self.catches / self.casts if self.casts else None,
        "recent_catch_rate": recent_rate,
        "recent_n": len(self.recent),
        "per_hour": self.catches / hours,
        "recent_per_hour": recent_per_hour,
        "avg_catch_secs": sum(recent_catch_secs) / len(recent_catch_secs) if recent_catch_secs else None,
        "last_loot": list(self.last_loot),
        "top_items": self.items.most_common(5),
      }
