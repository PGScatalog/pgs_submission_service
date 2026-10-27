from .document_store import DocumentStore


class FirestoreStore(DocumentStore):
    """DocumentStore backed by Google Cloud Firestore.

    Args:
        project: Google Cloud project ID.
        database: Firestore database ID (use "(default)" for the default database).

    Notes:
        - Credentials are resolved by google-cloud-firestore via Application
          Default Credentials.
        - `update` raises `google.api_core.exceptions.NotFound` for missing documents.
        - The `google.cloud.firestore` import is deferred so projects using
          another backend don't need the package installed.
    """

    def __init__(self, project, database):
        from google.cloud import firestore
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
