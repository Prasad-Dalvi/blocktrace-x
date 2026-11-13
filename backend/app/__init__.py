import logging
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "blocktrace-x-dev-secret")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "blocktrace-x-jwt-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///blocktrace_dev.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if test_config:
        app.config.update(test_config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.manufacturing import mfg_bp
    from app.routes.blockchain import bc_bp
    from app.routes.stage2_routes import s2_bp
    from app.routes.stage3_routes import s3_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(mfg_bp, url_prefix="/api/manufacturing")
    app.register_blueprint(bc_bp, url_prefix="/api/blockchain")
    app.register_blueprint(s2_bp, url_prefix="/api")
    app.register_blueprint(s3_bp, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "blocktrace-x-final"})

    @app.errorhandler(ValueError)
    def handle_value_error(err):
        return jsonify({"error": str(err)}), 400

    @app.errorhandler(404)
    def handle_not_found(err):
        return jsonify({"error": "Resource not found"}), 404

    with app.app_context():
        db.create_all()

    return app
