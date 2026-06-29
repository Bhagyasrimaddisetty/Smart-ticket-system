from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
from app import db
from app.models import Ticket, User, FileAttachment, Status, Priority, Category, Role
from app.tasks import send_ticket_notification, send_assignment_notification
from datetime import datetime
import os
import uuid

tickets_bp = Blueprint("tickets", __name__)


def generate_ticket_number():
    count = Ticket.query.count() + 1
    return f"TKT-{count:05d}"


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", set())


def save_file(file):
    """Save file locally (fallback when AWS not configured)."""
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(upload_folder, unique_name)
    file.save(path)
    return unique_name, f"/uploads/{unique_name}", os.path.getsize(path)


@tickets_bp.route("/tickets", methods=["POST"])
@jwt_required()
def create_ticket():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data.get("title") or not data.get("description"):
        return jsonify({"error": "Title and description required"}), 400

    ticket = Ticket(
        ticket_number=generate_ticket_number(),
        title=data["title"],
        description=data["description"],
        priority=Priority(data.get("priority", "medium")),
        category=Category(data.get("category", "general")),
        tags=data.get("tags", []),
        created_by=user_id,
        due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
    )

    if data.get("assigned_to"):
        assignee = User.query.get(data["assigned_to"])
        if assignee:
            ticket.assigned_to = assignee.id

    db.session.add(ticket)
    db.session.commit()

    # Background email notification
    try:
        send_ticket_notification.delay(ticket.id, "created")
    except Exception:
        pass

    return jsonify({"message": "Ticket created", "ticket": ticket.to_dict()}), 201


@tickets_bp.route("/tickets", methods=["GET"])
@jwt_required()
def get_tickets():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    role = claims.get("role")

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    query = Ticket.query

    # Non-admins/agents see only their tickets
    if role == "user":
        query = query.filter(Ticket.created_by == user_id)

    # Filters
    if request.args.get("status"):
        query = query.filter(Ticket.status == Status(request.args.get("status")))
    if request.args.get("priority"):
        query = query.filter(Ticket.priority == Priority(request.args.get("priority")))
    if request.args.get("category"):
        query = query.filter(Ticket.category == Category(request.args.get("category")))
    if request.args.get("assigned_to"):
        query = query.filter(Ticket.assigned_to == int(request.args.get("assigned_to")))
    if request.args.get("search"):
        term = f"%{request.args.get('search')}%"
        query = query.filter(
            db.or_(Ticket.title.ilike(term), Ticket.description.ilike(term),
                   Ticket.ticket_number.ilike(term))
        )

    # Sorting
    sort_by = request.args.get("sort_by", "created_at")
    sort_order = request.args.get("sort_order", "desc")
    sort_col = getattr(Ticket, sort_by, Ticket.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "tickets": [t.to_dict() for t in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "current_page": page,
        "per_page": per_page,
    }), 200


@tickets_bp.route("/tickets/<int:ticket_id>", methods=["GET"])
@jwt_required()
def get_ticket(ticket_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    ticket = Ticket.query.get_or_404(ticket_id)

    if claims.get("role") == "user" and ticket.created_by != user_id:
        return jsonify({"error": "Access denied"}), 403

    return jsonify(ticket.to_dict(include_comments=True)), 200


@tickets_bp.route("/tickets/<int:ticket_id>", methods=["PUT"])
@jwt_required()
def update_ticket(ticket_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    ticket = Ticket.query.get_or_404(ticket_id)
    role = claims.get("role")

    # Users can only update their own open tickets
    if role == "user":
        if ticket.created_by != user_id:
            return jsonify({"error": "Access denied"}), 403
        if ticket.status not in [Status.OPEN, Status.PENDING]:
            return jsonify({"error": "Cannot edit a ticket in progress or resolved"}), 400

    data = request.get_json()

    if "title" in data:
        ticket.title = data["title"]
    if "description" in data:
        ticket.description = data["description"]
    if "priority" in data and role in ["admin", "agent"]:
        ticket.priority = Priority(data["priority"])
    if "category" in data:
        ticket.category = Category(data["category"])
    if "tags" in data:
        ticket.tags = data["tags"]
    if "due_date" in data:
        ticket.due_date = datetime.fromisoformat(data["due_date"]) if data["due_date"] else None
    if "status" in data and role in ["admin", "agent"]:
        new_status = Status(data["status"])
        ticket.status = new_status
        if new_status == Status.RESOLVED and not ticket.resolved_at:
            ticket.resolved_at = datetime.utcnow()
    if "assigned_to" in data and role in ["admin", "agent"]:
        old_assignee = ticket.assigned_to
        ticket.assigned_to = data["assigned_to"]
        if data["assigned_to"] and data["assigned_to"] != old_assignee:
            try:
                send_assignment_notification.delay(ticket.id, data["assigned_to"])
            except Exception:
                pass

    db.session.commit()

    try:
        send_ticket_notification.delay(ticket.id, "updated")
    except Exception:
        pass

    return jsonify({"message": "Ticket updated", "ticket": ticket.to_dict()}), 200


@tickets_bp.route("/tickets/<int:ticket_id>", methods=["DELETE"])
@jwt_required()
def delete_ticket(ticket_id):
    claims = get_jwt()
    if claims.get("role") not in ["admin"]:
        return jsonify({"error": "Admin only"}), 403

    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket)
    db.session.commit()
    return jsonify({"message": f"Ticket {ticket.ticket_number} deleted"}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/assign", methods=["PUT"])
@jwt_required()
def assign_ticket(ticket_id):
    claims = get_jwt()
    if claims.get("role") not in ["admin", "agent"]:
        return jsonify({"error": "Insufficient permissions"}), 403

    ticket = Ticket.query.get_or_404(ticket_id)
    data = request.get_json()
    agent_id = data.get("agent_id")

    if agent_id:
        agent = User.query.get(agent_id)
        if not agent or agent.role not in [Role.ADMIN, Role.AGENT]:
            return jsonify({"error": "Invalid agent"}), 400
        ticket.assigned_to = agent_id
        ticket.status = Status.IN_PROGRESS
        try:
            send_assignment_notification.delay(ticket.id, agent_id)
        except Exception:
            pass
    else:
        ticket.assigned_to = None
        ticket.status = Status.OPEN

    db.session.commit()
    return jsonify({"message": "Ticket assigned", "ticket": ticket.to_dict()}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/upload", methods=["POST"])
@jwt_required()
def upload_file(ticket_id):
    user_id = int(get_jwt_identity())
    ticket = Ticket.query.get_or_404(ticket_id)

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    filename, file_url, file_size = save_file(file)

    attachment = FileAttachment(
        filename=filename,
        original_filename=secure_filename(file.filename),
        file_url=file_url,
        file_size=file_size,
        mime_type=file.content_type,
        ticket_id=ticket_id,
        uploaded_by=user_id,
    )
    db.session.add(attachment)
    db.session.commit()

    return jsonify({"message": "File uploaded", "attachment": attachment.to_dict()}), 201


@tickets_bp.route("/tickets/<int:ticket_id>/status", methods=["PUT"])
@jwt_required()
def update_status(ticket_id):
    claims = get_jwt()
    if claims.get("role") not in ["admin", "agent"]:
        return jsonify({"error": "Insufficient permissions"}), 403

    ticket = Ticket.query.get_or_404(ticket_id)
    data = request.get_json()

    if not data.get("status"):
        return jsonify({"error": "status required"}), 400

    ticket.status = Status(data["status"])
    if ticket.status == Status.RESOLVED:
        ticket.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Status updated", "ticket": ticket.to_dict()}), 200
