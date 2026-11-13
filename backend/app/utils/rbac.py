from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt


def roles_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_role = claims.get("role")
            if user_role not in allowed_roles and user_role != "Admin":
                return (
                    jsonify(
                        {
                            "error": "Forbidden: insufficient role permissions",
                            "required_roles": list(allowed_roles),
                            "current_role": user_role,
                        }
                    ),
                    403,
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
