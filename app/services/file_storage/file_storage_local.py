import logging
import shutil
from os import PathLike
from pathlib import Path

from app.services.file_storage.file_storage import StorageService

logger = logging.getLogger(__name__)


class LocalFileStorageService(StorageService):
    """Stores files on the local filesystem under ``local_dir`` (default ``/tmp``).
    File names are resolved relative to ``local_dir``.
    """

    def __init__(self, local_dir: PathLike | str):
        self.local_dir = Path(local_dir)
        if not self.local_dir.exists() or not self.local_dir.is_dir():
            raise FileNotFoundError(f"Local directory {self.local_dir} for file storage doesn't exist")

    def _resolve(self, file_name: str) -> Path:
        """Resolve a file name to a path inside local_dir, rejecting traversal."""
        base = self.local_dir.resolve()
        path = (base / file_name).resolve()
        if base != path and base not in path.parents:
            raise ValueError(f"Invalid file name: {file_name!r}")
        return path

    def store(self, file, file_name: str) -> None:
        path = self._resolve(file_name)

        if isinstance(file, (bytes, bytearray)):
            path.write_bytes(file)
        elif isinstance(file, str):
            path.write_text(file)
        elif hasattr(file, "read"):
            with path.open("wb") as dest:
                shutil.copyfileobj(file, dest)
        else:
            raise TypeError(f"Unsupported file type: {type(file).__name__}")

    def retrieve(self, file_name: str) -> bytes:
        path = self._resolve(file_name)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_name}")
        return path.read_bytes()

    def delete(self, file_name: str) -> None:
        path = self._resolve(file_name)
        try:
            path.unlink()
        except FileNotFoundError:
            logger.error(f"Could not delete file. File not found: {file_name}")
