from abc import ABC, abstractmethod


class StorageService(ABC):
    """Abstract interface for storing, retrieving, and deleting files by name.
    """
    @abstractmethod
    def store(self, file, file_name: str) -> None: ...

    @abstractmethod
    def retrieve(self, file_name: str) -> bytes: ...

    @abstractmethod
    def delete(self, file_name: str) -> None: ...
