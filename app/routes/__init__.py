from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.courses import courses_bp
from app.routes.instructors import instructors_bp
from app.routes.students import students_bp

__all__ = ["admin_bp", "auth_bp", "courses_bp", "instructors_bp", "students_bp"]
