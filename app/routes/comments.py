from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import Comment, Ticket

comments_bp = Blueprint("comments", __name__)


@comments_bp.route("/comments", methods=["POST"])
@jwt_required()
def create_comment():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    data = request.get_json()

    if not data.get("ticket_id") or not data.get("content"):
        return jsonify({"error": "ticket_id and content required"}), 400

    ticket = Ticket.query.get_or_404(data["ticket_id"])

    # Only agents/admins can post internal notes
    is_internal = data.get("is_internal", False)
    if is_internal and claims.get("role") not in ["admin", "agent"]:
        is_internal = False

    comment = Comment(
        content=data["content"],
        is_internal=is_internal,
        ticket_id=ticket.id,
        user_id=user_id,
    )
    db.session.add(comment)
    db.session.commit()

    return jsonify({"message": "Comment added", "comment": comment.to_dict()}), 201


@comments_bp.route("/tickets/<int:ticket_id>/comments", methods=["GET"])
@jwt_required()
def get_comments(ticket_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    role = claims.get("role")

    Ticket.query.get_or_404(ticket_id)

    query = Comment.query.filter_by(ticket_id=ticket_id)

    # Users can't see internal notes
    if role == "user":
        query = query.filter_by(is_internal=False)

    comments = query.order_by(Comment.created_at.asc()).all()
    return jsonify([c.to_dict() for c in comments]), 200


@comments_bp.route("/comments/<int:comment_id>", methods=["PUT"])
@jwt_required()
def update_comment(comment_id):
    user_id = int(get_jwt_identity())
    comment = Comment.query.get_or_404(comment_id)

    if comment.user_id != user_id:
        return jsonify({"error": "Cannot edit another user's comment"}), 403

    data = request.get_json()
    if "content" in data:
        comment.content = data["content"]
    db.session.commit()

    return jsonify({"message": "Comment updated", "comment": comment.to_dict()}), 200


@comments_bp.route("/comments/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    comment = Comment.query.get_or_404(comment_id)

    if comment.user_id != user_id and claims.get("role") != "admin":
        return jsonify({"error": "Access denied"}), 403

    db.session.delete(comment)
    db.session.commit()
    return jsonify({"message": "Comment deleted"}), 200
