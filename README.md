# Smart Ticket Management System

A production-ready REST API for customer support ticket management built with **Flask**, **PostgreSQL**, **MongoDB**, **Celery**, and **Redis**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | Flask 3 + Flask-JWT-Extended |
| Primary DB | PostgreSQL (via SQLAlchemy) |
| Analytics DB | MongoDB (ticket event logs) |
| Task Queue | Celery 5 + Redis |
| Email | Flask-Mail (SMTP/Gmail) |
| File Storage | Local disk / AWS S3 (optional) |
| Containers | Docker + Docker Compose |
| Tests | pytest (33 tests, 100% pass) |

---

## Quick Start

### 1. Clone & configure
```bash
cp .env.example .env
# Edit .env with your DB credentials and email settings
```

### 2. Run with Docker (recommended)
```bash
docker-compose up --build
```

The API will be available at `http://localhost:5000`.

### 3. Run locally (dev)
```bash
# Start PostgreSQL, MongoDB, Redis first
pip install -r requirements.txt
python run.py

# In a separate terminal, start Celery worker
celery -A app.tasks.celery_app worker --loglevel=info
```

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | Register new user |
| POST | `/api/login` | Login → JWT token |
| POST | `/api/logout` | Invalidate token |
| GET | `/api/profile` | Get own profile |
| PUT | `/api/profile` | Update profile |
| GET | `/api/users` | List users (admin/agent) |

**Login request:**
```json
POST /api/login
{ "email": "user@example.com", "password": "secret" }
```
**Response:**
```json
{ "token": "<JWT>", "user": { "id": 1, "role": "admin", ... } }
```

All subsequent requests require:
```
Authorization: Bearer <JWT>
```

---

### Tickets

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/tickets` | Create ticket |
| GET | `/api/tickets` | List tickets (paginated, filtered) |
| GET | `/api/tickets/:id` | Get ticket + comments |
| PUT | `/api/tickets/:id` | Update ticket |
| DELETE | `/api/tickets/:id` | Delete ticket (admin only) |
| PUT | `/api/tickets/:id/assign` | Assign to agent |
| PUT | `/api/tickets/:id/status` | Update status only |
| POST | `/api/tickets/:id/upload` | Upload file attachment |

**Create ticket:**
```json
POST /api/tickets
{
  "title": "Cannot login",
  "description": "Getting 401 on /api/login",
  "priority": "high",      // low | medium | high | critical
  "category": "technical", // technical | billing | general | feature_request | bug
  "tags": ["auth", "login"],
  "due_date": "2024-12-31T23:59:00"  // optional ISO datetime
}
```

**Query filters:**
```
GET /api/tickets?status=open&priority=high&category=technical
GET /api/tickets?search=login&assigned_to=3
GET /api/tickets?sort_by=created_at&sort_order=desc&page=1&per_page=20
```

**Ticket statuses:** `open` → `in_progress` → `pending` → `resolved` → `closed`

---

### Comments

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/comments` | Add comment to ticket |
| GET | `/api/tickets/:id/comments` | Get all comments |
| PUT | `/api/comments/:id` | Edit own comment |
| DELETE | `/api/comments/:id` | Delete comment |

```json
POST /api/comments
{
  "ticket_id": 42,
  "content": "Working on it now.",
  "is_internal": true  // agents/admins only — hidden from end users
}
```

---

### Dashboard

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dashboard` | Admin overview (admin/agent) |
| GET | `/api/dashboard/agent/:id` | Per-agent stats |
| GET | `/api/dashboard/analytics` | MongoDB event log (admin) |

**Dashboard response includes:**
- Overview counts (total, open, in_progress, resolved, overdue)
- Tickets by priority and category
- Average resolution time (hours)
- 30-day daily ticket trend
- Top 5 agents by resolved tickets

---

## Role-Based Access

| Action | User | Agent | Admin |
|---|---|---|---|
| Create ticket | ✅ | ✅ | ✅ |
| View own tickets | ✅ | ✅ | ✅ |
| View all tickets | ❌ | ✅ | ✅ |
| Update ticket status | ❌ | ✅ | ✅ |
| Assign tickets | ❌ | ✅ | ✅ |
| Delete tickets | ❌ | ❌ | ✅ |
| Add internal notes | ❌ | ✅ | ✅ |
| View dashboard | ❌ | ✅ | ✅ |

---

## Background Jobs (Celery)

| Task | Trigger |
|---|---|
| `send_ticket_notification` | Ticket created/updated |
| `send_assignment_notification` | Ticket assigned to agent |
| `send_bulk_reminders` | Scheduled via Celery Beat |

To start the scheduler:
```bash
celery -A app.tasks.celery_app beat --loglevel=info
```

---

## Running Tests

```bash
python -m pytest tests/test_api.py -v
# 33 tests | 100% pass | uses SQLite in-memory
```

---

## AWS EC2 Deployment

```bash
# On EC2 (Ubuntu 22.04)
sudo apt update && sudo apt install -y docker.io docker-compose
git clone <repo> && cd smart-ticket-system
cp .env.example .env && nano .env   # set production secrets
docker-compose up -d

# Expose port 5000 in EC2 Security Group
# Use nginx as reverse proxy in production
```

---

## Environment Variables

See `.env.example` for full list. Key variables:

```env
DATABASE_URL=postgresql://user:pass@host:5432/tickets_db
MONGO_URI=mongodb://localhost:27017/
CELERY_BROKER_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-very-long-secret-key
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-app-password
```
