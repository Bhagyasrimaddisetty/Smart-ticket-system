from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from app import db, mongo_db
from app.models import Ticket, User, Status, Priority, Category
from sqlalchemy import func, case
from datetime import datetime, timedelta

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def get_dashboard():
    claims = get_jwt()
    if claims.get("role") not in ["admin", "agent"]:
        return jsonify({"error": "Insufficient permissions"}), 403

    # ── Overview counts ──────────────────────────────────────────────────
    total = Ticket.query.count()
    open_count = Ticket.query.filter_by(status=Status.OPEN).count()
    in_progress = Ticket.query.filter_by(status=Status.IN_PROGRESS).count()
    resolved = Ticket.query.filter_by(status=Status.RESOLVED).count()
    closed = Ticket.query.filter_by(status=Status.CLOSED).count()
    unassigned = Ticket.query.filter(Ticket.assigned_to.is_(None),
                                     Ticket.status == Status.OPEN).count()

    # ── By priority ──────────────────────────────────────────────────────
    priority_counts = db.session.query(
        Ticket.priority, func.count(Ticket.id)
    ).group_by(Ticket.priority).all()

    # ── By category ─────────────────────────────────────────────────────
    category_counts = db.session.query(
        Ticket.category, func.count(Ticket.id)
    ).group_by(Ticket.category).all()

    # ── Avg resolution time (hours) ──────────────────────────────────────
    resolved_tickets = Ticket.query.filter(
        Ticket.resolved_at.isnot(None)
    ).with_entities(Ticket.created_at, Ticket.resolved_at).all()

    avg_resolution_hours = None
    if resolved_tickets:
        total_hours = sum(
            (t.resolved_at - t.created_at).total_seconds() / 3600
            for t in resolved_tickets
        )
        avg_resolution_hours = round(total_hours / len(resolved_tickets), 2)

    # ── Tickets last 30 days (daily trend) ───────────────────────────────
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_trend = db.session.query(
        func.date(Ticket.created_at).label("date"),
        func.count(Ticket.id).label("count")
    ).filter(Ticket.created_at >= thirty_days_ago).group_by(
        func.date(Ticket.created_at)
    ).order_by(func.date(Ticket.created_at)).all()

    # ── Top agents by resolved tickets ───────────────────────────────────
    top_agents = db.session.query(
        User.id, User.name, func.count(Ticket.id).label("resolved_count")
    ).join(Ticket, Ticket.assigned_to == User.id).filter(
        Ticket.status == Status.RESOLVED
    ).group_by(User.id, User.name).order_by(
        func.count(Ticket.id).desc()
    ).limit(5).all()

    # ── SLA breach (overdue open tickets) ────────────────────────────────
    overdue = Ticket.query.filter(
        Ticket.due_date < datetime.utcnow(),
        Ticket.status.in_([Status.OPEN, Status.IN_PROGRESS])
    ).count()

    return jsonify({
        "overview": {
            "total": total,
            "open": open_count,
            "in_progress": in_progress,
            "resolved": resolved,
            "closed": closed,
            "unassigned": unassigned,
            "overdue": overdue,
        },
        "by_priority": {p.value: c for p, c in priority_counts},
        "by_category": {cat.value: c for cat, c in category_counts},
        "avg_resolution_hours": avg_resolution_hours,
        "daily_trend": [
            {"date": str(row.date), "count": row.count}
            for row in daily_trend
        ],
        "top_agents": [
            {"id": a.id, "name": a.name, "resolved_count": a.resolved_count}
            for a in top_agents
        ],
    }), 200


@dashboard_bp.route("/dashboard/agent/<int:agent_id>", methods=["GET"])
@jwt_required()
def agent_dashboard(agent_id):
    claims = get_jwt()
    user_id = int(claims.get("sub", 0))
    if claims.get("role") not in ["admin", "agent"] and user_id != agent_id:
        return jsonify({"error": "Insufficient permissions"}), 403

    agent = User.query.get_or_404(agent_id)
    assigned = Ticket.query.filter_by(assigned_to=agent_id)

    return jsonify({
        "agent": agent.to_dict(),
        "stats": {
            "total_assigned": assigned.count(),
            "open": assigned.filter_by(status=Status.OPEN).count(),
            "in_progress": assigned.filter_by(status=Status.IN_PROGRESS).count(),
            "resolved": assigned.filter_by(status=Status.RESOLVED).count(),
        },
        "recent_tickets": [
            t.to_dict() for t in assigned.order_by(Ticket.updated_at.desc()).limit(10).all()
        ],
    }), 200


@dashboard_bp.route("/dashboard/analytics", methods=["GET"])
@jwt_required()
def mongo_analytics():
    """
    Extended analytics stored in MongoDB (event logs, view counts, etc.)
    Falls back to empty data if MongoDB unavailable.
    """
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    if mongo_db is None:
        return jsonify({"error": "MongoDB not connected", "data": []}), 200

    try:
        events = list(mongo_db.ticket_events.find({}, {"_id": 0}).sort("ts", -1).limit(100))
        return jsonify({"events": events}), 200
    except Exception as e:
        return jsonify({"error": str(e), "data": []}), 200
