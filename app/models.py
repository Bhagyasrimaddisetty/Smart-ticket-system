from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import enum


class Role(str, enum.Enum):
    ADMIN = "admin"
    AGENT = "agent"
    USER = "user"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Category(str, enum.Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    GENERAL = "general"
    FEATURE_REQUEST = "feature_request"
    BUG = "bug"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(Role), default=Role.USER, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    avatar_url = db.Column(db.String(512), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    raised_tickets = db.relationship("Ticket", foreign_keys="Ticket.created_by", backref="creator", lazy="dynamic")
    assigned_tickets = db.relationship("Ticket", foreign_keys="Ticket.assigned_to", backref="assignee", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active,
            "department": self.department,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat(),
        }


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(Status), default=Status.OPEN, nullable=False, index=True)
    priority = db.Column(db.Enum(Priority), default=Priority.MEDIUM, nullable=False, index=True)
    category = db.Column(db.Enum(Category), default=Category.GENERAL, nullable=False)
    tags = db.Column(db.JSON, default=list)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    due_date = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    comments = db.relationship("Comment", backref="ticket", lazy="dynamic", cascade="all, delete-orphan")
    attachments = db.relationship("FileAttachment", backref="ticket", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_comments=False):
        data = {
            "id": self.id,
            "ticket_number": self.ticket_number,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "category": self.category.value,
            "tags": self.tags or [],
            "created_by": self.creator.to_dict() if self.creator else None,
            "assigned_to": self.assignee.to_dict() if self.assignee else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "comment_count": self.comments.count(),
            "attachments": [a.to_dict() for a in self.attachments],
        }
        if include_comments:
            data["comments"] = [c.to_dict() for c in self.comments.order_by(Comment.created_at.asc())]
        return data


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)  # Agent-only notes
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "is_internal": self.is_internal,
            "ticket_id": self.ticket_id,
            "author": self.author.to_dict() if self.author else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FileAttachment(db.Model):
    __tablename__ = "file_attachments"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.original_filename,
            "file_url": self.file_url,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "created_at": self.created_at.isoformat(),
        }
