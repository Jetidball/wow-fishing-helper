from queue import Queue, Empty, Full
from threading import Lock
from typing import Generic, TypeVar
T = TypeVar("T")

class LatestQueue(Queue, Generic[T]):
    """Bounded freshness queue. Drop oldest on overload; never block capture/GUI producers.

    For replaceable frames/status only, never ordered key down/up or reliable control messages.
    """
    def __init__(self, maxsize=1):
        if maxsize < 1:
            raise ValueError("queue capacity must be positive")
        super().__init__(maxsize)
        self._writers = Lock()
        self.dropped = 0

    def put(self, item, block=True, timeout=None):
        with self._writers:
            while True:
                try:
                    super().put(item, block=False)
                    return
                except Full:
                    try:
                        self.get_nowait()
                        self.task_done()
                        self.dropped += 1
                    except Empty:
                        pass
