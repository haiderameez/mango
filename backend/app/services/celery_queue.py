import time

import redis

from app.core.config import settings

INVESTIGATION_QUEUE_NAME = "investigations"


class CeleryInvestigationQueue:
    """Small adapter preserving the queue interface used by the HTTP service and tests."""

    def __init__(self, task):
        self.task = task
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._local_results = []

    @property
    def depth(self) -> int:
        try:
            return int(self.redis.llen(INVESTIGATION_QUEUE_NAME))
        except redis.RedisError:
            return 0

    def submit(self, run_id: int) -> int:
        result = self.task.apply_async(args=(run_id,), queue=INVESTIGATION_QUEUE_NAME)
        self._local_results.append(result)
        self._local_results = [item for item in self._local_results if not item.ready()]
        return self.depth

    def wait_idle(self, timeout: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._local_results = [item for item in self._local_results if not item.ready()]
            if not self._local_results:
                return True
            time.sleep(0.05)
        return False
