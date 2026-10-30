from abc import abstractmethod, ABC


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
