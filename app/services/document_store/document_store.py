from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Any


class DocumentStore(ABC):
    """Minimal interface for a document-oriented database.

    The application code talks only to this interface, so switching databases
    means writing a new subclass rather than touching the call sites.

    Terminology:
        collection: A named group of documents (a table, roughly).
        doc_id: The unique string key of a document within its collection.
        doc: A plain dict of JSON-serializable values.
    """

    @abstractmethod
    def add(self, collection: str, doc: dict) -> None:
        """Insert a document with a database-generated ID.
        Use for append-only records such as audit logs.
        """

    @abstractmethod
    def set(self, collection: str, doc_id: str, doc: dict) -> None:
        """Create or fully replace the document at `doc_id` (upsert).
        Any fields not in `doc` are removed from an existing document.
        """

    @abstractmethod
    def update(self, collection: str, doc_id: str, fields: dict) -> None:
        """Merge `fields` into an existing document, leaving other fields untouched.
        """

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> dict | None:
        """Return the document as a dict, or None if it does not exist."""

    @abstractmethod
    def get_by_filter(self, collection, filters: dict) -> dict | None:
        """Return the first document matching all `filters`, or None.

        Args:
            filters: Mapping of attribute name to required value, e.g.
                {"status": "active", "address.city": "Edinburgh"}.

        If multiple documents match, a MultipleDocumentsFound exception is raised.
        """

    @abstractmethod
    def find_by_filter(self, collection, filters: dict) -> list[dict]:
        """Return all documents matching all `filters`.

            Returns an empty list if there are no matches.
        """

    @abstractmethod
    def update_by_filter(self, collection, filters: dict, fields: dict) -> int:
        """Apply `fields` to every document matching all `filters`.

        Args:
            filters: Mapping of attribute name to required value.
            fields: Fields to update, with the same semantics as `update`
                (dotted keys update nested fields).

        Returns:
            The number of documents updated (0 if nothing matched).
        """


@dataclass(frozen=True)
class Not:
    value: Any


class MultipleDocumentsFound(Exception):
    """Raised when a single-document lookup matches more than one document."""
