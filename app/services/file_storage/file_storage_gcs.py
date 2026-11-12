import logging
from typing import Optional

from google.api_core.exceptions import NotFound
from google.cloud import storage

from .file_storage import StorageService

logger = logging.getLogger(__name__)


class GCSStorageService(StorageService):
    """Stores files as objects in a Google Cloud Storage bucket.

    Credentials come from Application Default Credentials unless a
    preconfigured ``storage.Client`` is passed in. An optional ``prefix``
    namespaces all objects under a "folder" in the bucket.
    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        client: Optional[storage.Client] = None,
    ) -> None:
        self._client = client or storage.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._prefix = prefix.strip("/")

    def _blob(self, file_name: str) -> storage.Blob:
        name = file_name.lstrip("/")
        if not name:
            raise ValueError("file_name must not be empty")
        if self._prefix:
            name = f"{self._prefix}/{name}"
        return self._bucket.blob(name)

    def store(self, file, file_name: str) -> None:
        blob = self._blob(file_name)

        if isinstance(file, (bytes, bytearray)):
            blob.upload_from_string(bytes(file))
        elif isinstance(file, str):
            blob.upload_from_string(file)
        elif hasattr(file, "read"):
            blob.upload_from_file(file)
        else:
            raise TypeError(f"Unsupported file type: {type(file).__name__}")

    def retrieve(self, file_name: str) -> bytes:
        try:
            return self._blob(file_name).download_as_bytes()
        except NotFound:
            raise FileNotFoundError(f"File not found: {file_name}") from None

    def delete(self, file_name: str) -> None:
        try:
            pass
            self._blob(file_name).delete()
        except NotFound:
            logger.error(f"Could not delete file. File not found: {file_name}")
