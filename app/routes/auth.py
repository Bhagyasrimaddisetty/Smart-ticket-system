from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt
)
from app import db
from app.models import User, Role
from datetime import datetime

auth_bp = Blueprint("auth", __name__)

# Simple token blocklist (in-memory; use Redis in prod)
blocklist = set()


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    required = ["name", "email", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    if User.query.filter_by(email=data["email"].lower()).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        name=data["name"],
        email=data["email"].lower(),
        role=Role(data.get("role", "user")) if data.get("role") in [r.value for r in Role] else Role.USER,
        department=data.get("department"),
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role.value})
    return jsonify({"message": "User registered", "token": token, "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=data["email"].lower()).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401
    if not user.is_active:
        return jsonify({"error": "Account deactivated"}), 403

    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role.value})
    return jsonify({"message": "Login successful", "token": token, "user": user.to_dict()}), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    blocklist.add(jti)
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict()), 200


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if "name" in data:
        user.name = data["name"]
    if "department" in data:
        user.department = data["department"]
    if "avatar_url" in data:
        user.avatar_url = data["avatar_url"]
    if "password" in data and data["password"]:
        user.set_password(data["password"])

    db.session.commit()
    return jsonify({"message": "Profile updated", "user": user.to_dict()}), 200


@auth_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    claims = get_jwt()
    if claims.get("role") not in ["admin", "agent"]:
        return jsonify({"error": "Insufficient permissions"}), 403
    users = User.query.filter_by(is_active=True).all()
    return jsonify([u.to_dict() for u in users]), 200


@auth_bp.route("/users/<int:user_id>/deactivate", methods=["PUT"])
@jwt_required()
def deactivate_user(user_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    return jsonify({"message": f"User {user.email} deactivated"}), 200
