from .document_store import DocumentStore, Not, MultipleDocumentsFound
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


class FirestoreStore(DocumentStore):
    """DocumentStore backed by Google Cloud Firestore.

    Args:
        project: Google Cloud project ID.
        database: Firestore database ID (use "(default)" for the default database).

    Notes:
        - Credentials are resolved by google-cloud-firestore via Application
          Default Credentials.
        - `update` raises `google.api_core.exceptions.NotFound` for missing documents.
    """

    def __init__(self, project, database):
        self._db = firestore.Client(project=project, database=database)

    def add(self, collection, doc):
        self._db.collection(collection).add(doc)

    def set(self, collection, doc_id, doc):
        self._db.collection(collection).document(doc_id).set(doc)

    def update(self, collection, doc_id, fields):
        self._db.collection(collection).document(doc_id).update(fields)

    def get(self, collection, doc_id) -> dict | None:
        snap = self._db.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def _query_by_filter(self, collection, filters):
        if not filters:
            raise ValueError("At least one attribute filter is required.")

        query = self._db.collection(collection)
        for field, condition in filters.items():
            if isinstance(condition, Not):
                op, value = "!=", condition.value
            else:
                op, value = "==", condition
            query = query.where(filter=FieldFilter(field, op, value))
        return query

    def get_by_filter(self, collection, filters: dict) -> dict | None:
        """Return the single document matching all `filters`, or None.

        Raises:
            MultipleDocumentsFound: if more than one document matches.
        """
        # Fetch at most 2: enough to detect ambiguity without reading everything.
        snaps = list(self._query_by_filter(collection, filters).limit(2).stream())
        if len(snaps) > 1:
            raise MultipleDocumentsFound(
                f"Multiple documents in {collection!r} match filter on "
                f"{sorted(filters)}."
            )
        return snaps[0].to_dict() if snaps else None

    def find_by_filter(self, collection, filters: dict) -> list[dict]:
        return [
            snap.to_dict()
            for snap in self._query_by_filter(collection, filters).stream()
        ]

    def update_by_filter(self, collection, filters: dict, fields: dict) -> int:
        # Firestore allows at most 500 writes per batch.
        batch_size = 500

        # select([]) fetches document references only, not their contents.
        snaps = list(self._query_by_filter(collection, filters).select([]).stream())

        for i in range(0, len(snaps), batch_size):
            batch = self._db.batch()
            for snap in snaps[i: i + batch_size]:
                batch.update(snap.reference, fields)
            batch.commit()

        return len(snaps)
