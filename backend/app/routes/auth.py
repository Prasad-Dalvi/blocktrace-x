from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from pydantic import ValidationError
from app import db
from app.models import User, AuditLog
from app.schemas.validation import LoginSchema

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    try:
        payload = LoginSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    user = User.query.filter_by(email=payload.email.strip().lower()).first()
    if not user or not user.check_password(payload.password):
        return jsonify({"error": "Invalid email or password"}), 401

    role_name = user.role.name if user.role else "Viewer"
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": role_name, "email": user.email},
    )
    db.session.add(AuditLog(actor_email=user.email, action="LOGIN", details=f"Role={role_name}"))
    db.session.commit()

    return jsonify({"access_token": token, "user": user.to_dict()})


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()})
