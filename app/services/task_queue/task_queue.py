from abc import ABC, abstractmethod
from typing import Callable


class TaskQueue(ABC):
    """Interface for scheduling work to run in the background.

    Application code depends only on this class, so the backend (in-process
    threads, Google Cloud Tasks, ...) can be swapped through configuration.

    Delivery on real backends is at-least-once, so handlers must be
    idempotent: the same task may run more than once.
    """

    @abstractmethod
    def enqueue(self, handler: Callable[[dict], bool], payload: dict, path: str) -> None:
        """Schedule a task for asynchronous execution and return immediately.

        The task's result is not returned. Report outcomes through a separate
        channel, such as a job store keyed by a job id in ``payload``.

        Each backend uses a different subset of the arguments, so callers
        must always provide both ``handler`` and ``path``:

        * Backends that run code in-process (``LocalQueue``) call ``handler``
          and ignore ``path``.
        * Backends that call back over HTTP (``CloudTaskQueue``) POST
          ``payload`` to ``path`` and ignore ``handler``. The route at
          ``path`` is expected to call the same function as ``handler``.

        Args:
            handler: Function that does the work. It receives ``payload`` and
                returns ``True`` when the task is finished (success or
                permanent failure) or ``False`` to request a retry.
            payload: JSON-serializable dict passed to the handler. Keep it
                small (Cloud Tasks limits bodies to 100 KB): pass identifiers
                and load large data from storage inside the handler.
            path: URL path of the worker route that executes the task, e.g.
                ``"/tasks/process_metadata"``. Must start with ``/``.

        """
