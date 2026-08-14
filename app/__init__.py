from flask import Flask

from app.extensions import db, migrate
from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.courses import courses_bp
from app.routes.errors import register_error_handlers
from app.routes.instructors import instructors_bp
from app.routes.students import students_bp


def create_app(config_object: str | None = None) -> Flask:
    app = Flask(__name__)

    if config_object:
        app.config.from_object(config_object)
    else:
        app.config.from_object("config.Config")

    db.init_app(app)
    migrate.init_app(app, db)

    register_blueprints(app)
    register_error_handlers(app)

    return app


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(instructors_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(students_bp)

    @app.get("/api/health")
    def health_check():
        return {
            "success": True,
            "message": "CODEx Academy API is running",
            "data": {"service": "codex-academy-backend"},
        }
