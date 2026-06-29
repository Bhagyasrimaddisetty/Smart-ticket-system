import pytest
from app import create_app, db
from app.models import User, Ticket, Comment, Role, Status, Priority, Category


@pytest.fixture(scope="session")
def app():
    _app = create_app("testing")
    ctx = _app.app_context()
    ctx.push()
    db.create_all()

    # Pre-seed admin and regular user
    admin = User(name="Admin User", email="admin@test.com", role=Role.ADMIN)
    admin.set_password("Admin@123456")
    user = User(name="Regular User", email="user@test.com", role=Role.USER)
    user.set_password("User@123456")
    db.session.add_all([admin, user])
    db.session.commit()

    yield _app
    db.drop_all()
    ctx.pop()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/login", json={"email": "admin@test.com", "password": "Admin@123456"})
    data = r.get_json()
    assert "token" in data, f"Admin login failed: {data}"
    return data["token"]


@pytest.fixture(scope="session")
def user_token(client):
    r = client.post("/api/login", json={"email": "user@test.com", "password": "User@123456"})
    data = r.get_json()
    assert "token" in data, f"User login failed: {data}"
    return data["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Auth Tests ──────────────────────────────────────────────────────────
class TestAuth:
    def test_register_new_user(self, client):
        r = client.post("/api/register", json={
            "name": "New User", "email": "newuser@test.com", "password": "pass123456"
        })
        assert r.status_code == 201
        assert "token" in r.get_json()

    def test_register_duplicate_email(self, client):
        r = client.post("/api/register", json={
            "name": "Dup", "email": "admin@test.com", "password": "whatever"
        })
        assert r.status_code == 409

    def test_login_success(self, client):
        r = client.post("/api/login", json={"email": "admin@test.com", "password": "Admin@123456"})
        assert r.status_code == 200
        assert "token" in r.get_json()

    def test_login_wrong_password(self, client):
        r = client.post("/api/login", json={"email": "admin@test.com", "password": "wrong"})
        assert r.status_code == 401

    def test_login_missing_fields(self, client):
        r = client.post("/api/login", json={"email": "admin@test.com"})
        assert r.status_code == 400

    def test_get_profile(self, client, admin_token):
        r = client.get("/api/profile", headers=auth(admin_token))
        assert r.status_code == 200
        assert r.get_json()["email"] == "admin@test.com"

    def test_update_profile(self, client, admin_token):
        r = client.put("/api/profile", headers=auth(admin_token),
                       json={"department": "Engineering"})
        assert r.status_code == 200
        assert r.get_json()["user"]["department"] == "Engineering"

    def test_list_users_admin(self, client, admin_token):
        r = client.get("/api/users", headers=auth(admin_token))
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_users_user_denied(self, client, user_token):
        r = client.get("/api/users", headers=auth(user_token))
        assert r.status_code == 403


# ── Ticket Tests ────────────────────────────────────────────────────────
class TestTickets:
    def test_create_ticket(self, client, user_token):
        r = client.post("/api/tickets", headers=auth(user_token), json={
            "title": "Server is down",
            "description": "Production server not responding",
            "priority": "critical",
            "category": "technical",
            "tags": ["production", "urgent"],
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["ticket"]["ticket_number"].startswith("TKT-")
        assert data["ticket"]["status"] == "open"
        assert data["ticket"]["priority"] == "critical"

    def test_create_ticket_missing_fields(self, client, user_token):
        r = client.post("/api/tickets", headers=auth(user_token), json={"title": "No desc"})
        assert r.status_code == 400

    def test_get_all_tickets_admin(self, client, admin_token):
        r = client.get("/api/tickets", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.get_json()
        assert "tickets" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_get_tickets_user_sees_own_only(self, client, user_token):
        r = client.get("/api/tickets", headers=auth(user_token))
        assert r.status_code == 200

    def test_get_ticket_by_id(self, client, admin_token):
        r = client.get("/api/tickets/1", headers=auth(admin_token))
        assert r.status_code == 200
        assert r.get_json()["id"] == 1

    def test_get_ticket_404(self, client, admin_token):
        r = client.get("/api/tickets/9999", headers=auth(admin_token))
        assert r.status_code == 404

    def test_update_ticket_status(self, client, admin_token):
        r = client.put("/api/tickets/1", headers=auth(admin_token), json={
            "status": "in_progress", "priority": "high"
        })
        assert r.status_code == 200
        assert r.get_json()["ticket"]["status"] == "in_progress"

    def test_filter_tickets_by_status(self, client, admin_token):
        r = client.get("/api/tickets?status=in_progress", headers=auth(admin_token))
        assert r.status_code == 200
        for t in r.get_json()["tickets"]:
            assert t["status"] == "in_progress"

    def test_filter_tickets_by_priority(self, client, admin_token):
        r = client.get("/api/tickets?priority=high", headers=auth(admin_token))
        assert r.status_code == 200

    def test_search_tickets(self, client, admin_token):
        r = client.get("/api/tickets?search=Server", headers=auth(admin_token))
        assert r.status_code == 200

    def test_pagination(self, client, admin_token):
        r = client.get("/api/tickets?page=1&per_page=5", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.get_json()
        assert "pages" in data

    def test_assign_ticket(self, client, admin_token):
        # Get admin user id
        profile = client.get("/api/profile", headers=auth(admin_token)).get_json()
        r = client.put("/api/tickets/1/assign", headers=auth(admin_token),
                       json={"agent_id": profile["id"]})
        assert r.status_code == 200

    def test_update_status_endpoint(self, client, admin_token):
        r = client.put("/api/tickets/1/status", headers=auth(admin_token),
                       json={"status": "resolved"})
        assert r.status_code == 200
        assert r.get_json()["ticket"]["status"] == "resolved"

    def test_delete_ticket_user_denied(self, client, user_token):
        r = client.delete("/api/tickets/1", headers=auth(user_token))
        assert r.status_code == 403

    def test_delete_ticket_admin(self, client, admin_token, user_token):
        r_create = client.post("/api/tickets", headers=auth(user_token), json={
            "title": "Delete me", "description": "Temp ticket"
        })
        ticket_id = r_create.get_json()["ticket"]["id"]
        r = client.delete(f"/api/tickets/{ticket_id}", headers=auth(admin_token))
        assert r.status_code == 200

    def test_unauthenticated_access_denied(self, client):
        r = client.get("/api/tickets")
        assert r.status_code == 401


# ── Comment Tests ───────────────────────────────────────────────────────
class TestComments:
    def test_add_comment(self, client, user_token):
        # Create a ticket first
        r_t = client.post("/api/tickets", headers=auth(user_token), json={
            "title": "Comment ticket", "description": "For testing comments"
        })
        ticket_id = r_t.get_json()["ticket"]["id"]

        r = client.post("/api/comments", headers=auth(user_token), json={
            "ticket_id": ticket_id, "content": "This is a comment"
        })
        assert r.status_code == 201
        assert r.get_json()["comment"]["content"] == "This is a comment"

    def test_get_comments(self, client, user_token):
        r = client.get("/api/tickets/2/comments", headers=auth(user_token))
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_internal_note_blocked_for_user(self, client, user_token):
        r = client.post("/api/comments", headers=auth(user_token), json={
            "ticket_id": 2, "content": "Internal note attempt", "is_internal": True
        })
        assert r.status_code == 201
        # is_internal should be overridden to False for regular users
        assert r.get_json()["comment"]["is_internal"] is False

    def test_internal_note_allowed_for_admin(self, client, admin_token):
        r = client.post("/api/comments", headers=auth(admin_token), json={
            "ticket_id": 2, "content": "Admin internal note", "is_internal": True
        })
        assert r.status_code == 201
        assert r.get_json()["comment"]["is_internal"] is True

    def test_add_comment_missing_fields(self, client, user_token):
        r = client.post("/api/comments", headers=auth(user_token), json={"ticket_id": 2})
        assert r.status_code == 400


# ── Dashboard Tests ─────────────────────────────────────────────────────
class TestDashboard:
    def test_dashboard_admin(self, client, admin_token):
        r = client.get("/api/dashboard", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.get_json()
        assert "overview" in data
        assert "by_priority" in data
        assert "by_category" in data
        assert "daily_trend" in data
        assert "top_agents" in data
        assert "avg_resolution_hours" in data
        assert "total" in data["overview"]
        assert "open" in data["overview"]

    def test_dashboard_user_denied(self, client, user_token):
        r = client.get("/api/dashboard", headers=auth(user_token))
        assert r.status_code == 403

    def test_agent_dashboard(self, client, admin_token):
        profile = client.get("/api/profile", headers=auth(admin_token)).get_json()
        r = client.get(f"/api/dashboard/agent/{profile['id']}", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.get_json()
        assert "stats" in data
        assert "recent_tickets" in data
