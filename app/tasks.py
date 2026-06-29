from celery import Celery
from flask_mail import Message
import os

# Standalone Celery app (separate from Flask app context)
celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)


def make_flask_app():
    """Import here to avoid circular imports."""
    from app import create_app
    return create_app()


@celery_app.task(name="tasks.send_ticket_notification", bind=True, max_retries=3)
def send_ticket_notification(self, ticket_id, event_type):
    """Send email notification when a ticket is created or updated."""
    try:
        app = make_flask_app()
        with app.app_context():
            from app import mail, mongo_db
            from app.models import Ticket

            ticket = Ticket.query.get(ticket_id)
            if not ticket:
                return

            # Log event to MongoDB if available
            try:
                if mongo_db is not None:
                    from datetime import datetime
                    mongo_db.ticket_events.insert_one({
                        "ticket_id": ticket_id,
                        "ticket_number": ticket.ticket_number,
                        "event": event_type,
                        "ts": datetime.utcnow(),
                    })
            except Exception:
                pass

            # Email to ticket creator
            if ticket.creator and ticket.creator.email:
                subject = f"[{ticket.ticket_number}] Ticket {event_type.title()}"
                body = (
                    f"Hi {ticket.creator.name},\n\n"
                    f"Your ticket '{ticket.title}' ({ticket.ticket_number}) has been {event_type}.\n"
                    f"Current Status: {ticket.status.value.upper()}\n"
                    f"Priority: {ticket.priority.value.upper()}\n\n"
                    f"Thank you,\nSupport Team"
                )
                try:
                    msg = Message(subject, recipients=[ticket.creator.email], body=body)
                    mail.send(msg)
                except Exception:
                    pass  # Email optional; don't crash the task

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.send_assignment_notification", bind=True, max_retries=3)
def send_assignment_notification(self, ticket_id, agent_id):
    """Notify an agent when a ticket is assigned to them."""
    try:
        app = make_flask_app()
        with app.app_context():
            from app import mail
            from app.models import Ticket, User

            ticket = Ticket.query.get(ticket_id)
            agent = User.query.get(agent_id)
            if not ticket or not agent:
                return

            subject = f"[ASSIGNED] {ticket.ticket_number}: {ticket.title}"
            body = (
                f"Hi {agent.name},\n\n"
                f"You have been assigned ticket {ticket.ticket_number}.\n\n"
                f"Title: {ticket.title}\n"
                f"Priority: {ticket.priority.value.upper()}\n"
                f"Category: {ticket.category.value.upper()}\n\n"
                f"Please review and take action.\n\nSupport Team"
            )
            try:
                msg = Message(subject, recipients=[agent.email], body=body)
                mail.send(msg)
            except Exception:
                pass

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.send_bulk_reminders")
def send_bulk_reminders():
    """Scheduled task: remind agents about overdue tickets (call via celery beat)."""
    from datetime import datetime, timedelta
    app = make_flask_app()
    with app.app_context():
        from app import mail
        from app.models import Ticket, User, Status

        overdue = Ticket.query.filter(
            Ticket.due_date < datetime.utcnow(),
            Ticket.status.in_([Status.OPEN, Status.IN_PROGRESS]),
            Ticket.assigned_to.isnot(None),
        ).all()

        for ticket in overdue:
            agent = ticket.assignee
            if agent and agent.email:
                try:
                    msg = Message(
                        f"[OVERDUE] {ticket.ticket_number}: Action Required",
                        recipients=[agent.email],
                        body=(
                            f"Hi {agent.name},\n\n"
                            f"Ticket {ticket.ticket_number} is overdue.\n"
                            f"Due: {ticket.due_date}\n\n"
                            f"Please resolve ASAP.\n\nSupport Team"
                        ),
                    )
                    mail.send(msg)
                except Exception:
                    pass


# Re-export tasks so Flask app can call `.delay()`
send_ticket_notification = send_ticket_notification
send_assignment_notification = send_assignment_notification
