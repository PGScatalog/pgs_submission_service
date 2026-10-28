import os

import pydantic
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from pydantic_settings import BaseSettings

import config
from app.security.security import secure_app
from app.services.document_store import FirestoreStore
from app.services.file_storage import LocalFileStorageService, GCSStorageService
from app.services.task_queue import LocalTaskQueue, CloudTaskQueue

# Initialize the rate limiter.
# We use a lambda function to provide a key function that always returns the same value ("global"),
# which means the limit will be applied globally across all clients.
# This is defined at the module level so that it can be imported and used in the routes for fine-tuning.
limiter = Limiter(
        lambda: "global",
        default_limits=["60 per hour"],
    )


def create_app(config_object: BaseSettings = config.Config()):
    """Create and configure the Flask application.
    The config_object type should be a subclass of BaseSettings, so that Pydantic can load environment variables properly."""
    app = Flask(__name__)

    app.config.from_object(config_object)

    # CORS settings
    CORS(app, resources={r"/": {"origins": "*"}})

    # Rate limiting settings
    limiter.init_app(app)

    # Set up security
    secure_app(app)

    # Setting up services as extensions, depending on the environment.
    if os.getenv("GAE_ENV"):  # Google App Engine
        app.extensions["storage"] = GCSStorageService(bucket_name=app.config["GCS_BUCKET_NAME"])
        app.extensions["task_queue"] = CloudTaskQueue(
            project=app.config["GCP_PROJECT_NAME"],
            location=app.config["GCT_LOCATION"],
            queue_name=app.config["GCT_QUEUE_NAME"],
            base_url=app.config["BASE_URL"],
        )
    else:  # Local server
        app.extensions["storage"] = LocalFileStorageService(local_dir="/tmp")
        app.extensions["task_queue"] = LocalTaskQueue()

    # Setting up DB document store
    app.extensions["document_store"] = FirestoreStore(
        project=app.config["FIRESTORE_PROJECT_ID"],
        database=app.config["FIRESTORE_DATABASE_ID"]
    )

    # Globus config
    try:
        globus_cfg = config.GlobusConfig()
        app.extensions["globus"] = globus_cfg
    except pydantic.ValidationError as e:
        missing = [err["loc"][0] for err in e.errors()]
        app.logger.error(f"Missing Globus configuration variables: {', '.join(missing)}")
        raise RuntimeError(e)

    from .routes import bp
    app.register_blueprint(bp)

    # TODO: refactor
    from .routes_aync.metadata import bp as metadata_bp
    app.register_blueprint(metadata_bp)

    return app
