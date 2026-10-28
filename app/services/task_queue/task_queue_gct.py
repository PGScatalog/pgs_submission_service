import json
import logging

from pydantic import validate_call
from google.cloud import tasks_v2

from .task_queue import TaskQueue


logger = logging.getLogger(__name__)


class CloudTaskQueue(TaskQueue):
    """Queue backed by Google Cloud Tasks (HTTP push).

    ``enqueue`` creates a Cloud Tasks task that POSTs the payload as JSON to
    ``{base_url}{path}``. The route at that path does the work and answers:

    * 2xx: the task is complete.
    * any other status (typically 500): Cloud Tasks retries according to the
      queue's retry configuration.

    Attributes:
        project: GCP project id.
        location: Queue region, e.g. ``"europe-west1"``.
        queue_name: Name of the Cloud Tasks queue.
        base_url: Public URL at which Cloud Tasks can reach this app.
    """

    @validate_call
    def __init__(self, project: str, location: str, queue_name: str, base_url: str):
        """Store the queue configuration. No network call is made here.

        Args:
            project: GCP project id.
            location: Region of the queue.
            queue_name: Name of an existing queue.
            base_url: Externally reachable base URL of this app, without a
                trailing slash (``path`` is appended directly).

        """
        self.project = project
        self.location = location
        self.queue_name = queue_name
        self.base_url = base_url

        self.client = tasks_v2.CloudTasksClient()
        self.parent = self.client.queue_path(self.project, self.location, self.queue_name)

        logger.info("Initializing CloudTaskQueue: %s", self.queue_name)

    def enqueue(self, handler, payload: dict, path: str):
        """Create a Cloud Tasks task that will POST ``payload`` to ``path``.

        Returns as soon as Cloud Tasks accepts the task. The work runs later,
        in a separate HTTP request, possibly on another instance. ``handler``
        is accepted for interface compatibility and ignored.

        Args:
            handler: Unused.
            payload: JSON-serializable dict sent as the request body. Must
                serialize to less than 100 KB.
            path: Route to call, starting with ``/``. The worker route should
                verify that the request really came from Cloud Tasks.

        Raises:
            google.api_core.exceptions.GoogleAPICallError: If the task could
                not be created (queue not found, permission denied, payload
                too large, service unavailable).
            TypeError: If ``payload`` is not JSON-serializable.
        """
        logger.info(f"Enqueuing CloudTaskQueue: {path} - payload: {payload}")

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.base_url}{path}",
                "headers": {"Content-type": "application/json"},
                "body": json.dumps(payload).encode(),
            }
        }
        self.client.create_task(request={"parent": self.parent, "task": task})
