import logging
import time
from concurrent.futures import ThreadPoolExecutor
from flask import current_app

from .task_queue import TaskQueue

logger = logging.getLogger(__name__)


class LocalTaskQueue(TaskQueue):
    """In-process queue for development and tests.

    Runs handlers on a background thread pool inside the web app's process,
    wrapped in a Flask application context. It needs no external service and
    emulates Cloud Tasks retries: when a handler returns ``False`` or raises,
    it is run again with exponential backoff, up to ``max_attempts`` runs.

    Attributes:
        app: Flask application used to open an app context for each run.
        max_attempts: Total runs allowed per task, first try included.
        backoff: Base of the exponential delay; the wait after attempt ``n``
            is ``backoff ** n`` seconds.
        executor: Thread pool that executes the tasks.
    """

    def __init__(self, max_attempts=3, backoff_seconds=2, workers=2):
        """Create the queue and start its thread pool.

        Args:
            app: The real ``Flask`` instance, not the ``current_app`` proxy,
                so an app context can be opened from worker threads.
            max_attempts: Maximum number of runs per task. Must be >= 1.
            backoff_seconds: Base in seconds for the retry delay.
            workers: Number of worker threads. Use 1 if your handlers or
                services are not thread-safe.
        """
        self.max_attempts = max_attempts
        self.backoff = backoff_seconds
        self.executor = ThreadPoolExecutor(max_workers=workers)

    def enqueue(self, handler, payload: dict, path: str):
        """Submit ``handler(payload)`` to the thread pool and return at once.

        ``path`` is accepted for interface compatibility and ignored. Errors
        raised by the handler never reach the caller; they are logged.
        """
        app = current_app._get_current_object()  # real app, usable from another thread
        self.executor.submit(self._run, app, handler, payload)

    def _run(self, app, handler, payload):
        """Run the handler with retries, inside an app context.

        Per attempt, the task stops if the handler returns ``True``. If it
        returns ``False`` or raises, a warning is logged, the thread sleeps
        ``backoff ** attempt`` seconds, and the handler runs again. After
        ``max_attempts`` unsuccessful runs the task is dropped and an error
        is logged.

        Note that raising is treated like returning ``False`` here, which
        matches the earlier version of this class. Cloud Tasks behaves
        similarly, since an unhandled exception in the route becomes a 500.
        """
        for attempt in range(1, self.max_attempts + 1):
            with app.app_context():
                try:
                    done = handler(payload)
                except Exception:
                    logger.exception("Local task crashed (attempt %s)", attempt)
                    done = False
            if done:
                return
            logger.warning("Local task will retry (attempt %s/%s)", attempt, self.max_attempts)
            time.sleep(self.backoff ** attempt)
        logger.error("Local task gave up after %s attempts: %s", self.max_attempts, payload)
