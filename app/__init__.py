from flask import Flask
from flask_cors import CORS

from app.security.security import secure_app


def create_app(config_object="config.Config"):
    app = Flask(__name__)

    app.config.from_object(config_object)

    # CORS settings
    CORS(app)
    cors = CORS(app, resources={r"/": {"origins": "*"}})

    # Set up security
    secure_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    return app
