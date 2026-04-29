import pydantic
from flask import Flask
from flask_cors import CORS
from pydantic_settings import BaseSettings

import config
from app.security.security import secure_app




def create_app(config_object: BaseSettings = config.Config()):
    app = Flask(__name__)

    app.config.from_object(config_object)

    # CORS settings
    CORS(app, resources={r"/": {"origins": "*"}})

    # Set up security
    secure_app(app)

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

    return app
