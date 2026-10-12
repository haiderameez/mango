"""A single-worker queue for investigations.

Two incidents arriving at once must not mean two investigations calling the LLM at once:
on a free tier that is the fastest way to a 429. Everything goes through one FIFO worker,
which also refuses to start a run the day's remaining budget cannot cover.
"""
import logging
import queue
import threading

from app.ai import quota
from app.ai.graph import LLM_CALLS_PER_RUN

logger = logging.getLogger(__name__)

# How long the worker sleeps before re-checking an exhausted daily budget.
MAX_WAIT_SECONDS = 300


class InvestigationQueue:
    def __init__(
        self,
        runner,
        calls_per_run: int = LLM_CALLS_PER_RUN,
        recheck_seconds: float = MAX_WAIT_SECONDS,
    ):
        self._runner = runner
        self._calls_per_run = calls_per_run
        self._recheck_seconds = recheck_seconds
        self._queue: queue.Queue[int] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._stopping = threading.Event()

    @property
    def depth(self) -> int:
        """Runs waiting for the worker, not counting one already in progress."""
        return self._queue.qsize()

    def submit(self, run_id: int) -> int:
        """Queue a run and return the queue depth. Starts the worker on first use."""
        with self._lock:
            self._queue.put(run_id)
            self._idle.clear()
            depth = self._queue.qsize()

        self._ensure_worker()

        return depth

    def wait_idle(self, timeout: float = 60.0) -> bool:
        """Block until nothing is queued or running. Used by tests and by shutdown."""
        return self._idle.wait(timeout)

    def stop(self) -> None:
        """Interrupt a worker that is waiting for the daily budget to reset."""
        self._stopping.set()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._stopping.clear()
                self._worker = threading.Thread(
                    target=self._work, name="investigation-worker", daemon=True
                )
                self._worker.start()

    def _mark_idle_if_drained(self) -> None:
        with self._lock:
            if self._queue.empty():
                self._idle.set()

    def _wait_for_budget(self) -> None:
        """Hold the run in the worker until it is safe to send: the provider is not asking
        us to back off, and today's budget can cover a whole run."""
        while True:
            if quota.is_cooling_down():
                wait = min(quota.cooldown_remaining(), self._recheck_seconds)
                logger.warning(
                    "Provider cooldown active. Holding the investigation queue for %.0fs.", wait
                )
            elif not quota.has_capacity(self._calls_per_run):
                wait = min(quota.seconds_until_reset(), self._recheck_seconds)
                logger.warning(
                    "Daily LLM budget spent (%s requests used). Holding the investigation "
                    "queue for %.0fs; it resets in %.1f hours.",
                    quota.used_today(),
                    wait,
                    quota.seconds_until_reset() / 3600,
                )
            else:
                return

            if self._stopping.wait(wait):
                return

    def _work(self) -> None:
        while not self._stopping.is_set():
            try:
                run_id = self._queue.get(timeout=1.0)
            except queue.Empty:
                self._mark_idle_if_drained()
                continue

            try:
                self._wait_for_budget()
                self._runner(run_id)
            except Exception:
                # The runner records its own failures. This is the last line of defence, so
                # that one bad run cannot kill the worker and strand the queue.
                logger.exception("Investigation %s could not be run", run_id)
            finally:
                self._queue.task_done()
                self._mark_idle_if_drained()
